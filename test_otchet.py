
import subprocess
import streamlit as st
import pandas as pd
import numpy as np
import re

@st.cache_data
def load_excel_with_custom_header(file, identifier_value):
    """
    Загружает Excel-файл, ищет первую строку, в которой встречается identifier_value (в любой ячейке),
    и использует эту строку как заголовок.
    Если identifier_value не найден, возбуждает ошибку.
    """
    file.seek(0)  # сброс указателя файла
    df = pd.read_excel(file, header=None)
    
    header_index = None
    # Перебираем строки и ищем нужное значение во всех ячейках строки
    for i, row in df.iterrows():
        if row.astype(str).str.contains(identifier_value, case=False, na=False).any():
            header_index = i
            break
    if header_index is None:
        raise ValueError(f"Идентификатор '{identifier_value}' не найден в файле.")
    
    file.seek(0)
    df = pd.read_excel(file, header=header_index)
    return df

@st.cache_data
def load_excel_without_header(file):
    file.seek(0)
    return pd.read_excel(file, header=None)

def extract_report_period(file):
    """
    Извлекает отчетный период из первой строки файла с метками.
    Ожидается, что в ячейке A1 содержится строка вида:
    "Отчет за период с YYYY-MM-DD по YYYY-MM-DD" или "Отчет за период с DD.MM.YYYY по DD.MM.YYYY"
    """
    df = load_excel_without_header(file)
    header_str = str(df.iloc[0, 0])
    # Регулярное выражение для поиска дат
    match = re.search(r'Отчет за период с\s*([\d\.\-]+)\s*по\s*([\d\.\-]+)', header_str)
    if match:
        # Определяем формат даты: если в строке есть тире, то используем формат ISO, иначе – формат с точками.
        date_format = "%Y-%m-%d" if "-" in match.group(1) else "%d.%m.%Y"
        report_start = pd.to_datetime(match.group(1), format=date_format)
        report_end = pd.to_datetime(match.group(2), format=date_format)
        return report_start, report_end
    else:
        st.error("Не удалось извлечь отчетный период из первой строки файла с метками.")
        return pd.NaT, pd.NaT

# Интерфейс загрузки файлов в Streamlit
st.title("Генератор еженедельных отчётов")

mp_file = st.file_uploader("Загрузите файл с медиапланом", type=["xlsx"])
metki_file = st.file_uploader("Загрузите файл с метками UTM", type=["xlsx"])

# Создаём две колонки, чтобы сделать поля ввода компактнее
col1, col2 = st.columns([1, 1])  # Две равные колонки

with col1:
    tp_primary_calls = st.number_input("Тематика: первичные звонки", min_value=0, step=1)
    oh_primary_calls = st.number_input("Охват: первичные звонки", min_value=0, step=1)

with col2:
    tp_target_calls = st.number_input("Тематика: ЦО", min_value=0, step=1)
    oh_target_calls = st.number_input("Охват: ЦО", min_value=0, step=1)

if mp_file and metki_file:
    # Загружаем медиаплан с поиском заголовка, содержащего '№'
    df_mp = load_excel_with_custom_header(mp_file, '№')
    # Если первый столбец медиаплана полностью пустой, удаляем его
    if df_mp.iloc[:, 0].isna().all():
        df_mp = df_mp.iloc[:, 1:]
    
    # Извлекаем отчетный период из файла с метками (из первой строки)
    report_start, report_end = extract_report_period(metki_file)
    
    # Загружаем файл с метками с поиском заголовка, содержащего 'UTM Source'
    df_metki = load_excel_with_custom_header(metki_file, 'UTM Source')

    # Обрабатываем медиаплан
    df = df_mp[['№', 'Название сайта', 'Период', 'Общая стоимость с учетом НДС', 'KPI прогноз']].copy()
    df = df.replace('-', '0')
    def determine_category(row):
        if pd.isna(row['№']):
        # Если значение отсутствует, используем значение из "Название сайта"
            return row['Название сайта']
        elif isinstance(row['№'], str):
        # Если значение есть и это строка, используем его как категорию
            return row['№']
        else:
        # Если значение присутствует, но не является строкой (например, число), оставляем пустым
            return pd.NA

    df['Категория'] = df.apply(determine_category, axis=1).ffill()
    
    df = df[~df['Период'].isna()]

    # Функция для извлечения начальной и конечной даты
    def extract_dates(period):
        try:
            # Проверка, что период имеет формат 'DD.MM.YYYY - DD.MM.YYYY'
            start_date, end_date = period.split('-')
            start_date = pd.to_datetime(start_date.strip(), format='%d.%m.%Y')
            end_date = pd.to_datetime(end_date.strip(), format='%d.%m.%Y')
            return start_date, end_date
        except Exception as e:
            st.error(f"Ошибка в данных периода: {period}. Ошибка: {str(e)}")
            return pd.NaT, pd.NaT
            
# Применение функции и создание новых столбцов с начальной и конечной датой
    if 'Период' in df.columns:
        df[['Start Date', 'End Date']] = df['Период'].apply(extract_dates).apply(pd.Series)
    else:
        st.error("Столбец 'Период' не найден в данных.")

# Бюджет по неделям
    def calculate_budget_per_week(row):
        start_date = row['Start Date']
        end_date = row['End Date']

    # Определяем границы периода с учетом полных недель
        first_monday = start_date - pd.Timedelta(days=start_date.weekday())  # Понедельник первой недели
        last_sunday = end_date + pd.Timedelta(days=(6 - end_date.weekday()))  # Воскресенье последней недели

        weeks = []
        week_start = first_monday

        while week_start <= last_sunday:
            week_end = week_start + pd.Timedelta(days=6)  # Воскресенье

        # Определяем активный период в рамках недели
            active_start = max(week_start, start_date)  # Либо понедельник, либо старт кампании
            active_end = min(week_end, end_date)  # Либо воскресенье, либо конец кампании

            active_days = (active_end - active_start).days + 1  # Количество активных дней кампании в неделе
            total_days = (end_date - start_date).days + 1  # Все активные дни кампании

        # Если в неделе нет активных дней кампании, бюджет = 0
            week_budget = row['Общая стоимость с учетом НДС'] * (active_days / total_days) if active_days > 0 else 0

        # Добавляем данные
            weeks.append((week_start, week_end, week_budget))

        # Переход к следующей неделе
            week_start += pd.Timedelta(days=7)

        return weeks

# Применение функции для всех строк
    week_budget_data = []
    for idx, row in df.iterrows():
        week_budget_data.extend(calculate_budget_per_week(row))

# Создаём DataFrame для распределённых бюджетов по неделям
    df_week_budget = pd.DataFrame(week_budget_data, columns=['Неделя с', 'Неделя по', 'Бюджет на неделю'])

# Добавляем информацию о сайте и периоде для каждой недели
    df_week_budget['Название сайта'] = np.repeat(df['Название сайта'].values, [len(calculate_budget_per_week(row)) for _, row in df.iterrows()])
    df_week_budget['Категория'] = np.repeat(df['Категория'].values, [len(calculate_budget_per_week(row)) for _, row in df.iterrows()])

# Группировка по категории и неделе, суммирование бюджета
    df_weekly_category_budget = df_week_budget.groupby(['Категория', 'Неделя с', 'Неделя по'], as_index=False)['Бюджет на неделю'].sum()

# Очистка данных в KPI прогноз
    df['KPI прогноз'] = df['KPI прогноз'].replace("-", np.nan)  # Заменяем "-" на NaN
    df['KPI прогноз'] = pd.to_numeric(df['KPI прогноз'], errors='coerce').fillna(0)  # Конвертируем в числа, заменяем NaN на 0

    def calculate_kpi_per_week(row):
        start_date = row['Start Date']
        end_date = row['End Date']

    # Определяем понедельник перед стартом и воскресенье после окончания
        first_monday = start_date - pd.Timedelta(days=start_date.weekday())  # Понедельник недели старта
        last_sunday = end_date + pd.Timedelta(days=(6 - end_date.weekday()))  # Воскресенье недели окончания

        weeks = []
        week_start = first_monday

        while week_start <= last_sunday:
            week_end = week_start + pd.Timedelta(days=6)  # Воскресенье

        # Определяем, какие дни из недели входят в период кампании
            active_start = max(week_start, start_date)  # Либо понедельник, либо старт кампании
            active_end = min(week_end, end_date)  # Либо воскресенье, либо конец кампании

            active_days = (active_end - active_start).days + 1  # Дни кампании в этой неделе
            total_days = (end_date - start_date).days + 1  # Все активные дни кампании

        # Если в неделе нет активных дней кампании, KPI = 0
            week_kpi = round(row['KPI прогноз'] * (active_days / total_days)) if active_days > 0 else 0

        # Добавляем неделю в список
            weeks.append((week_start, week_end, week_kpi))

        # Переход к следующей неделе
            week_start += pd.Timedelta(days=7)

        return weeks

# Применяем к каждому ряду в df
    week_kpi_data = []
    for idx, row in df.iterrows():
        week_kpi_data.extend(calculate_kpi_per_week(row))

# Создаем DataFrame для KPI
    df_week_kpi = pd.DataFrame(week_kpi_data, columns=['Неделя с', 'Неделя по', 'KPI на неделю'])
    
# Добавляем категорию и сайт
    df_week_kpi['Категория'] = np.repeat(df['Категория'].values, [len(calculate_kpi_per_week(row)) for _, row in df.iterrows()])
    df_week_kpi['Название сайта'] = np.repeat(df['Название сайта'].values, [len(calculate_kpi_per_week(row)) for _, row in df.iterrows()])

# Группировка KPI по категориям и неделям
    df_weekly_category_kpi = df_week_kpi.groupby(['Категория', 'Неделя с', 'Неделя по'], as_index=False)['KPI на неделю'].sum()
    
# Фильтрация меток
    df_filtered = df_metki[df_metki['UTM Campaign'].astype(str).str.contains('arwm', na=False, case=False)]
    df_filtered = df_filtered[~df_filtered['UTM Source'].astype(str).isin(['yandex_maps', 'navigator'])]
    
# Вычисления
    df_filtered['Время на сайте'] = pd.to_timedelta(df_filtered['Время на сайте'])
    total_visits = df_filtered['Визиты'].sum()
    total_visitors = df_filtered['Посетители'].sum()
    
    weighted_avg_otkazy = (df_filtered['Отказы'] * df_filtered['Визиты']).sum() / total_visits
    weighted_avg_glubina = (df_filtered['Глубина просмотра'] * df_filtered['Визиты']).sum() / total_visits
    weighted_avg_robotnost = (df_filtered['Роботность'] * df_filtered['Визиты']).sum() / total_visits
    weighted_avg_time_sec = (df_filtered['Время на сайте'].dt.total_seconds() * df_filtered['Визиты']).sum() / total_visits

    def format_seconds(total_seconds):
        total_seconds = int(total_seconds)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return f"{hours}:{minutes:02d}:{seconds:02d}"

    weighted_avg_time_str = format_seconds(weighted_avg_time_sec)
 
# Приводим даты к нужному формату
    df_week_budget['Неделя с'] = pd.to_datetime(df_week_budget['Неделя с'])
    df_week_budget['Неделя по'] = pd.to_datetime(df_week_budget['Неделя по'])
    
    # Группировка данных по UTM Source с расчётом взвешенных средних
    utm_summary = df_filtered.groupby("UTM Source").agg({
        "Визиты": "sum",
        "Посетители": "sum"
    }).reset_index()

# Добавляем расчёт взвешенных средних для показателей
    utm_summary["Отказы"] = utm_summary["UTM Source"].apply(
        lambda source: (df_filtered.loc[df_filtered["UTM Source"] == source, "Отказы"] * 
                        df_filtered.loc[df_filtered["UTM Source"] == source, "Визиты"]).sum() / 
                        df_filtered.loc[df_filtered["UTM Source"] == source, "Визиты"].sum()
    )

    utm_summary["Глубина просмотра"] = utm_summary["UTM Source"].apply(
        lambda source: (df_filtered.loc[df_filtered["UTM Source"] == source, "Глубина просмотра"] * 
                        df_filtered.loc[df_filtered["UTM Source"] == source, "Визиты"]).sum() / 
                        df_filtered.loc[df_filtered["UTM Source"] == source, "Визиты"].sum()
    )

    utm_summary["Роботность"] = utm_summary["UTM Source"].apply(
        lambda source: (df_filtered.loc[df_filtered["UTM Source"] == source, "Роботность"] * 
                        df_filtered.loc[df_filtered["UTM Source"] == source, "Визиты"]).sum() / 
                        df_filtered.loc[df_filtered["UTM Source"] == source, "Визиты"].sum()
    )

    utm_summary["Время на сайте (сек)"] = utm_summary["UTM Source"].apply(
        lambda source: (df_filtered.loc[df_filtered["UTM Source"] == source, "Время на сайте"].dt.total_seconds() * 
                        df_filtered.loc[df_filtered["UTM Source"] == source, "Визиты"]).sum() / 
                        df_filtered.loc[df_filtered["UTM Source"] == source, "Визиты"].sum()
    )

# Преобразуем среднее время в ЧЧ:ММ:СС
    utm_summary["Время на сайте"] = utm_summary["Время на сайте (сек)"].apply(format_seconds)
    utm_summary.drop(columns=["Время на сайте (сек)"], inplace=True)

    # Проверяем условия и формируем предупреждения
    warnings = []
    for _, row in utm_summary.iterrows():
        if row["Отказы"] > 0.35:
            warnings.append(f"⚠ Высокий процент отказов ({row['Отказы']*100:.2f}%) для источника {row['UTM Source']}")
        if row["Роботность"] > 0.10:
            warnings.append(f"⚠ Высокая роботность ({row['Роботность']*100:.2f}%) для источника {row['UTM Source']}")
        if pd.to_timedelta(row["Время на сайте"]) < pd.Timedelta(minutes=1):
            warnings.append(f"⚠ Низкое время на сайте ({row['Время на сайте']}) для источника {row['UTM Source']}")
    
    # Проверяем диапазон дат
    report_week_df = df_weekly_category_budget[
        (df_weekly_category_budget['Неделя с'] <= report_end) & (df_weekly_category_budget['Неделя по'] >= report_start)
    ]

        # Проверяем диапазон дат
    report_week_df_kpi = df_weekly_category_kpi[
        (df_weekly_category_kpi['Неделя с'] <= report_end) & (df_weekly_category_kpi['Неделя по'] >= report_start)
    ]

# Вычисляем общие суммы
    total_plan_kpi = report_week_df_kpi["KPI на неделю"].sum()
    total_fact_calls = tp_target_calls + oh_target_calls
    
# Определяем комментарий
    comments = []
    def get_comment(fact, plan):
        if fact == plan:
            return f"Реализация объемов ЦО идет согласно плановым"
        if fact < plan:
            return f"Реализация объемов ЦО меньше плановых. Выполняем усиления РК"
        else:
             return f"Реализация объемов ЦО превышает плановые"

    if total_plan_kpi > 0:
        if total_fact_calls == total_plan_kpi:
            comments.append ("Реализация объемов ЦО идет согласно плановым")
        elif total_fact_calls < total_plan_kpi:
            comments.append ("Реализация объемов ЦО меньше плановых. Выполняем усиления РК")
        else:
             comments.append ("Реализация объемов ЦО превышает плановые")
    
    # Извлекаем бюджет для категорий, содержащих слово "тема" для Тематических площадок
    tp_budget = report_week_df.loc[report_week_df['Категория'].str.strip().str.contains('тема', case=False, na=False), 'Бюджет на неделю'].sum()

    # Извлекаем бюджет для категорий, содержащих слово "охват" для Охватного размещения
    oh_budget = report_week_df.loc[report_week_df['Категория'].str.strip().str.contains('охват|программатик|бф', case=False, na=False), 'Бюджет на неделю'].sum()

    # Извлекаем KPI для "Тематических площадок" и "Охватного размещения"
    kpi_tp = report_week_df_kpi.loc[report_week_df_kpi['Категория'].str.strip().str.contains('тема', case=False, na=False), 'KPI на неделю'].sum()
    kpi_oh = report_week_df_kpi.loc[report_week_df_kpi['Категория'].str.strip().str.contains('охват', case=False, na=False), 'KPI на неделю'].sum()

    # Проверяем, что KPI прогноз не NaN
    if pd.notna(kpi_tp) and kpi_tp != 0:  # Проверка на NaN и 0
        tp_status = f"{((tp_target_calls - kpi_tp) / kpi_tp) * 100 + 100:.0f} %" if pd.notna(tp_target_calls) else "0 %"
    else:
        tp_status = "100 %"

    if pd.notna(kpi_oh) and kpi_oh != 0:  # Проверка на NaN и 0
        oh_status = f"{((oh_target_calls - kpi_oh) / kpi_oh) * 100 + 100:.0f} %" if pd.notna(oh_target_calls) else "0 %"
    else:
        oh_status = "100 %"

    # Рассчитываем CPL для первичных обращений
    tp_cpl = tp_budget / tp_primary_calls if tp_primary_calls > 0 else 0
    oh_cpl = oh_budget / oh_primary_calls if oh_primary_calls > 0 else 0

    # Приводим к строковому формату
    tp_budget_str = f"{tp_budget:,.2f}".replace(',', ' ') if tp_budget > 0 else "0"
    oh_budget_str = f"{oh_budget:,.2f}".replace(',', ' ') if oh_budget > 0 else "0"
    tp_cpl_str = f"{tp_cpl:,.2f}".replace(',', ' ') if tp_cpl > 0 else "0"
    oh_cpl_str = f"{oh_cpl:,.2f}".replace(',', ' ') if oh_cpl > 0 else "0"

    def get_work_done(report_start, report_end):
        work_done = set()

        # Проверка первой группы работ (до 10 числа)
        if report_start.day < 10:
            work_done.update([
                "Запустили РК",
                "Подготовили скрин-отчет с актуальными размещениями"
            ])

        # Проверка второй группы работ (с 14 по 16 число)
        if any(day in range(14, 17) for day in range(report_start.day, report_end.day + 1)):
            work_done.update([
                "Заменили рекламные материалы на актуальные",
                "Подготовили скрин-отчет с актуальными размещениями",
                "Подготовили МП-Факт предыдущего месяца",
                "Провели оптимизацию РК для улучшения поведенческих факторов",
                "Провели усиление РК для привлечения ЦО"
            ])

        # Проверка третьей группы работ (с 17 по 25 число)
        if any(day in range(17, 26) for day in range(report_start.day, report_end.day + 1)):
            work_done.update([
                "Провели оптимизацию РК для улучшения поведенческих факторов",
                "Провели усиление РК для привлечения ЦО",
                "Актуализировали Карту развития",
                "Подготовили медиапланирование на следующий месяц"
            ])

        # Проверка для четвертой группы работ (с 26 числа)
        if report_start.day >= 26 or report_end.day >= 26:
            work_done.update([
                "Провели оптимизацию РК для улучшения поведенческих факторов",
                "Провели усиление РК для привлечения ЦО",
                "Подготовили материалы на следующий месяц",
                "Подготовились к запуску РК"
            ])

        return sorted(work_done)  # Сортируем для удобства чтения

    work_done_list = get_work_done(report_start, report_end)
    work_done_str = "\n".join([f" - {task}" for task in work_done_list])

# Плановые работы
    def get_work_done_future(report_start, report_end):
        work_done_future = set()

        # Проверка первой группы работ (до 10 числа)
        if report_start.day < 10:
            work_done_future.update([
                "Следить за динамикой открута и выполнением по ЦО",
                "Оптимизация РК для улучшение поведенческих факторов",
                "Усиление РК для привлечения ЦО",
                "Замена рекламных материалов на актуальные",
                "Подготовка скрин-отчет с актуальными размещениями"
            ])

        # Проверка второй группы работ (с 14 по 16 число)
        if any(day in range(14, 17) for day in range(report_start.day, report_end.day + 1)):
            work_done_future.update([
                "Следить за динамикой открута и выполнением по ЦО",
                "Отпимизация РК для улучшение поведенческих факторов",
                "Усиление РК для привлечения ЦО",
                "Актуализация карты развития",
                "Подготовка МП на следующий месяц"
            ])

        # Проверка третьей группы работ (с 17 по 25 число)
        if any(day in range(17, 26) for day in range(report_start.day, report_end.day + 1)):
            work_done_future.update([
                "Следить за динамикой открута и выполнением по ЦО",
                "Оптимизация РК для улучшение поведенческих факторов",
                "Усиление РК для привлечения ЦО",
                "Подготовка материалов на следующий месяц"
            ])

        # Проверка для четвертой группы работ (с 26 числа)
        if report_start.day >= 26 or report_end.day >= 26:
            work_done_future.update([
                "Следить за динамикой открута и выполнением по ЦО",
                "Оптимизация РК для улучшение поведенческих факторов",
                "Усиление РК для привлечения ЦО",
                "Запуск РК",
                "Подготовка скрин-отчет с актуальными размещениями",
                "Подготовка МП-Факт",
                "Подготовка итогового отчета"
            ])

        return sorted(work_done_future)  # Сортируем для удобства чтения

    work_done_future_list = get_work_done_future(report_start, report_end)
    work_done_future_str = "\n".join([f" - {task}" for task in work_done_future_list])

    # Генерация отчёта
    report_text = f"""
Медийная реклама ({report_start.strftime('%d.%m.%y')}-{report_end.strftime('%d.%m.%y')})

ТЕМАТИЧЕСКИЕ ПЛОЩАДКИ:
Выполнение по бюджету плановое ({tp_budget_str} ₽ с НДС)
Первичные обращения — {tp_primary_calls}
CPL (первичных обращений) — {tp_cpl_str} ₽ с НДС
ЦО — {tp_target_calls}
Выполнение плана ЦО: {tp_status}

ОХВАТНЫЕ РАЗМЕЩЕНИЯ:
Выполнение по бюджету плановое ({oh_budget_str} ₽ с НДС)
Первичные обращения — {oh_primary_calls}
CPL (первичных обращений) — {oh_cpl_str} ₽ с НДС
Целевые обращения — {oh_target_calls}
Выполнение плана ЦО: {oh_status}

МЕТРИКИ:
- Выполнение плана по бюджету 100%
- Отказы: {weighted_avg_otkazy * 100:.2f}%
- Глубина просмотра: {weighted_avg_glubina:.2f}
- Время на сайте: {weighted_avg_time_str}
- Роботность: {weighted_avg_robotnost * 100:.2f}%

КОММЕНТАРИИ:
{chr(10).join(comments)}
    
ПРОДЕЛАННЫЕ РАБОТЫ:
{work_done_str}

ПЛАНОВЫЕ РАБОТЫ:
{work_done_future_str}
    """

    # Вывод предупреждений
    if warnings:
        st.subheader("⚠ Предупреждения")
        for warning in warnings:
            st.warning(warning)
    
        # Вывод данных в Streamlit
    st.subheader("Еженедельный отчет")
    st.text_area("", report_text, height=900)
    
        # Вывод таблицы с агрегированными данными
    st.subheader("Анализ по UTM Source")
    st.dataframe(utm_summary)

        # Проверяем, что строки найдены
    st.subheader("Данные МП за неделю")
    if report_week_df.empty:
        st.error("Ошибка: не найден бюджет для указанного периода!")
        st.write("Доступные даты:", df_week_budget[['Неделя с', 'Неделя по']].drop_duplicates())
    else:
        st.write("Найденные данные:", report_week_df)
       
    # Вывод таблицы с недельным бюджетом полная
    st.subheader("Недельный бюджет по всем площадкам")
    st.dataframe(df_week_budget)
