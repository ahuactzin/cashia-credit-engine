import pandas as pd
from datetime import date, datetime

from datetime import datetime, timedelta

from cashia_core.common_tools.storage import get_storage
from cce.config import PK_CALENDAR_FILE_KEY


def get_requested_average_ticket(unit: str, required_values, column_name) -> float:
    required_average_ticket = required_values.loc[
        required_values["Unidad"] == unit, column_name
    ].iloc[0]

    return float(required_average_ticket)

def get_interval_dates(
    today: date = None,
    file_key: str = PK_CALENDAR_FILE_KEY,
):
    if today is None:
        today = date.today()

    storage = get_storage()

    dates_df = storage.read_excel(file_key)

    # Asegúrate de que las columnas de fecha estén en formato de fecha
    dates_df["Inicio"] = pd.to_datetime(dates_df["Inicio"]).dt.date
    dates_df["Fin"] = pd.to_datetime(dates_df["Fin"]).dt.date

    date_row = dates_df[(dates_df["Inicio"] <= today) & (dates_df["Fin"] >= today)]

    month = date_row["Mes"].iloc[0]
    year = date_row["Año"].iloc[0]

    end_of_the_month = dates_df[
        (dates_df["Mes"] == month) & (dates_df["Año"] == year)
    ]["Fin"].max()

    first_day = dates_df[
        (dates_df["Mes"] == month) & (dates_df["Año"] == year)
    ]["Inicio"].min()

    return first_day, today, end_of_the_month


def get_week_month_year(date):
    # Asegúrate de que la fecha esté en formato datetime.date
    if isinstance(date, str):
        date = datetime.strptime(date, "%Y-%m-%d").date()
    elif isinstance(date, datetime):
        date = date.date()

    # Encontrar el primer jueves del año de la fecha
    current_year = date.year
    first_day_of_year = datetime(current_year, 1, 1).date()
    offset = (
        3 - first_day_of_year.weekday()
    ) % 7  # 3 = Jueves (0=Lunes, ..., 6=Domingo)
    first_thursday = first_day_of_year + timedelta(days=offset)

    # Si la fecha es antes del primer jueves, revisar si pertenece al año anterior
    if date < first_thursday:
        previous_year = current_year - 1
        first_day_of_previous_year = datetime(previous_year, 1, 1).date()
        previous_offset = (3 - first_day_of_previous_year.weekday()) % 7
        first_thursday_previous = first_day_of_previous_year + timedelta(
            days=previous_offset
        )
        total_weeks_previous = (first_thursday - first_thursday_previous).days // 7
        if (first_thursday - date).days <= 6:
            return total_weeks_previous, total_weeks_previous // 4 + 1, previous_year

    # Calcular el número de la semana
    days_since_first_thursday = (date - first_thursday).days
    week = days_since_first_thursday // 7 + 1
    month = (week - 1) // 4 + 1

    # Si estamos en la última semana del año, verificar si pertenece al próximo año
    first_day_of_next_year = datetime(current_year + 1, 1, 1).date()
    next_year_offset = (3 - first_day_of_next_year.weekday()) % 7
    first_thursday_next = first_day_of_next_year + timedelta(days=next_year_offset)
    if (first_thursday_next - date).days <= 6:
        return 1, 1, current_year + 1

    return week, month, current_year


def get_week_month_year2(date):
    # Asegúrate de que la fecha esté en formato datetime.date
    if isinstance(date, str):
        date = datetime.strptime(date, "%Y-%m-%d").date()
    elif isinstance(date, datetime):
        date = date.date()

    # Encontrar el último jueves del año anterior o el 1 de enero si es jueves
    current_year = date.year
    first_day_of_year = datetime(current_year, 1, 1).date()
    if first_day_of_year.weekday() == 3:  # 3 = Jueves (0=Lunes, ..., 6=Domingo)
        start_of_year = first_day_of_year
    else:
        last_day_of_previous_year = datetime(current_year - 1, 12, 31).date()
        offset = (
            last_day_of_previous_year.weekday() - 3
        ) % 7  # Ajustar al último jueves
        start_of_year = last_day_of_previous_year - timedelta(days=offset)

    # Calcular el número de la semana desde el inicio del año
    days_since_start = (date - start_of_year).days
    week = days_since_start // 7 + 1
    month = (week - 1) // 4 + 1

    # Verificar si la fecha pertenece al siguiente año
    first_day_of_next_year = datetime(current_year + 1, 1, 1).date()
    if first_day_of_next_year.weekday() == 3:
        start_of_next_year = first_day_of_next_year
    else:
        last_day_of_current_year = datetime(current_year, 12, 31).date()
        next_offset = (last_day_of_current_year.weekday() - 3) % 7
        start_of_next_year = last_day_of_current_year - timedelta(days=next_offset)
    if date >= start_of_next_year:
        return 1, 1, current_year + 1

    return week, month, current_year


def get_week_month_year_from_file(my_date: date):

    # Asegúrate de que la fecha esté en formato datetime.date
    if isinstance(my_date, str):
        my_date = datetime.strptime(my_date, "%Y-%m-%d").date()
    elif isinstance(my_date, datetime):
        my_date = my_date.date()

    dates_df = get_storage().read_excel(PK_CALENDAR_FILE_KEY)

    # Asegúrate de que las columnas de fecha estén en formato de fecha
    dates_df["Inicio"] = dates_df["Inicio"].dt.date
    dates_df["Fin"] = dates_df["Fin"].dt.date

    week_month_row = dates_df[
        (dates_df["Inicio"] <= my_date) & (dates_df["Fin"] >= my_date)
    ]

    month = week_month_row["Mes"].iloc[0]
    week = week_month_row["Semana"].iloc[0]
    year = my_date.year

    return week, month, year


# Verificar si el archivo se ejecuta directamente
if __name__ == "__main__":
    while True:
        my_date = input("Dame una una fecha:")
        # week, month, year = get_week_month_year2(my_date)
        week, month, year = get_week_month_year_from_file(my_date)
        print(f"La fecha {date} pertenece a la semana {week}, mes {month}, año {year}")
