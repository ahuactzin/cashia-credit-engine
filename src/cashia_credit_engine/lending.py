import mysql.connector
import pandas as pd
import numpy as np

from datetime import timedelta

from cashia_credit_engine.utils import *
from cashia_credit_engine.config import *

from cashia_core.common_tools.storage import get_storage

storage = get_storage()

def add_amount_selection_columns(df):
    # Initialize columna to 0
    df["sel_cliente"] = 0
    df["sel_cashia"] = 0
    df["sel_agente"] = 0

    # Condition 1: If monto_max_cashia == 0 → sel_cashia = 1
    cond1 = df["monto_max_cashia"] == 0
    df.loc[cond1, "sel_cashia"] = 1


    # Condition 2: If abs(Monto - monto_max_cashia) <= abs(Monto - monto_cliente) and
    #                 abs(Monto - monto_max_cashia) <= abs(Monto - monto_agente)
    cond2 = (
        ~cond1
        & (
            (df["Monto"] - df["monto_max_cashia"]).abs()
            <= (df["Monto"] - df["monto_cliente"]).abs()
        )
        & (
            (df["Monto"] - df["monto_max_cashia"]).abs()
            <= (df["Monto"] - df["monto_agente"]).abs()
        )
    )
    df.loc[cond2, "sel_cashia"] = 1

    # Condition 3: If abs(Monto - monto_agente) <= abs(Monto - monto_cliente) → sel_agente = 1
    cond3 = ~(cond1 | cond2) & (
        (df["Monto"] - df["monto_agente"]).abs()
        <= (df["Monto"] - df["monto_cliente"]).abs()
    )
    df.loc[cond3, "sel_agente"] = 1

    # Condition 4: Otherwise → sel_cliente = 1
    cond4 = ~(cond1 | cond2 | cond3)
    df.loc[cond4, "sel_cliente"] = 1

    return df


def read_previous_applications(first_day, end_date):
    file_key = APPLICATIONS_FILE_KEY

    # Diferencia en días
    days_elapsed = (end_date - first_day).days

    # Cargar el DataFrame si los dias transcurridos son mayor a 2 y el archivo existe, si no crear uno vacío
    if days_elapsed > 2 and storage.exists(file_key):
        df = storage.read_csv(file_key)
        df["Fecha"] = pd.to_datetime(df["Fecha"])

        # Calcular un día antes de la fecha máxima en el data frame
        max_date = df["Fecha"].max()
        limit_date = max_date - timedelta(days=1)

        if limit_date >= pd.to_datetime(first_day) and limit_date <= pd.to_datetime(end_date):
            # Filtrar el DataFrame dejando solo las filas con fecha menor o igual a limit_date
            df = df[df["Fecha"] <= limit_date]
            first_day = max_date
            print("File uploaded successfully.")
        else:
            # No hay datos previos para el rango de fechas especificado no se usarán los datos previos
            # por lo que pueden ignorarse
            print("No hay datos previos para el rango de fechas especificado.")
            df = pd.DataFrame()
    else:
        df = pd.DataFrame()
        print("Archivo no encontrado. Se creó un DataFrame vacío.")

    return df, first_day


def get_all_applications(first_day, end_date, units):
    connection = None

    try:
        connection = mysql.connector.connect(
            host=HOST, # Host
            database=DATABASE, # Nombre de la base de datos
            user=USER, # Usuario de la base de datos
            password=PASSWORD, # Contraseña del usuario
        )
        # Leemos las solicitudes que ya hemos cargado de la base de datos con anterioridad
        promok_all_units_df, first_day = read_previous_applications(first_day, end_date)

        if connection.is_connected():
            cursor = connection.cursor()

            print("Connected")

            # Convertir ambas fechas al formato "YYYY-MM-DD"
            end_date_str = end_date.strftime("%Y-%m-%d")
            first_day_str = first_day.strftime("%Y-%m-%d")

            print(f"Requiring First day: {first_day_str} End date: {end_date_str}")

            for unit in units:
                print("Processing: ", unit)
                args = (first_day_str, end_date_str, unit)

                cursor.callproc(PROCEDURE_NAME, args)

                # Si el procedimiento devuelve resultados
                results = list(cursor.stored_results())
                rows = results[0].fetchall() # Obtener todas las filas
                num_rows = len(rows)
                print(f"Number of registers: {num_rows}")

                if num_rows != 0:
                    df = pd.DataFrame(rows, columns=PROMOK_TABLE_COLUMNS)

                    # 🔧 Convertimos inmediatamente la fecha del nuevo DataFrame
                    df["Fecha"] = pd.to_datetime(df["Fecha"])

                    promok_all_units_df = pd.concat(
                        [promok_all_units_df, df], ignore_index=True
                    )

            cursor.close()

            if not promok_all_units_df.empty:
                # Necesitamos convertir la columna 'Fecha' a tipo datetime para una futura lectura correcta
                promok_all_units_df["Fecha"] = pd.to_datetime(
                    promok_all_units_df["Fecha"]
                )

                promok_all_units_df[["Score", "Score_agt"]] = (
                    promok_all_units_df[["Score", "Score_agt"]]
                    .apply(pd.to_numeric, errors="coerce") # convierte a float, errores → NaN
                    .fillna(0.0) # rellena NaN (reales) con 0.0
                )

                # Escribimos el archivo actualizado de las solicitudes que hemos recuperado de la base de datos
                storage.write_csv(
                    APPLICATIONS_FILE_KEY,
                    promok_all_units_df,
                    index=False
                )

                # Si Modelo no está llenado es que fue de forma manual
                promok_all_units_df["Modelo"] = promok_all_units_df["Modelo"].fillna(
                    "Manual"
                )
                promok_all_units_df["Modelo"] = promok_all_units_df["Modelo"].replace(
                    "N/A", "Manual"
                )

    except mysql.connector.Error as e:
        print(f"Error connecting or executing the procedure: {e}")
        promok_all_units_df = pd.DataFrame()

    finally:
        if connection and connection.is_connected():
            connection.close()
            print("Connection closed")

    # Add columns that indicates which of the amouts has been chosen (Cashia, Agent or Client)
    if not promok_all_units_df.empty:
        promok_all_units_df = add_amount_selection_columns(promok_all_units_df)

    return promok_all_units_df


def get_quotas(first_day, units):
        # Obtenemos la semana, mes y año de la fecha
    _, month, year = get_week_month_year_from_file(first_day)

    quotas = storage.read_excel(RISK_FILE_KEY)

    quotas = quotas[
        quotas["Unidad"].isin(units)
        & (quotas["Mes"] == month)
        & (quotas["Año"] == year)
    ]

    return quotas


def get_theoretical_daily_lendings(first_day, end_of_the_month, units):

    # Get the cuotas of the month
    quotas = get_quotas(first_day, units)

    # If no configuration for the current month return empty dataframe
    if quotas.empty:
        return pd.DataFrame()

    dates = pd.date_range(first_day, end_of_the_month)
    num_days = (end_of_the_month - first_day).days + 1

    # Lista vacia para almacenar los datos
    data = []

    # iterar cada fila del archivo de configuración
    for _, row in quotas.iterrows():
        unit = row["Unidad"]
        quota = row["Monto Total Esperado"]
        quota_cupo = row["Cupo"]
        prospecting = row["Prospección"]
        daily_amount = int(quota / num_days) # Calcular la cuota diaria de cada unidad
        daily_amount_limit = int(quota_cupo / num_days)
        daily_prospecting = int(prospecting / num_days)

        # Iterar sobre cada fecha
        for day in dates:
            day = day.date()
            days_passed = (day - first_day).days + 1 # Calcular el número de dias que han pasado
            cumulative_amount = daily_amount * days_passed # Calcular el monto acumulado
            cumulative_credit_limit = daily_amount_limit * days_passed
            cumulative_prospecting = daily_prospecting * days_passed

            data.append(
                {
                    "Unidad": unit,
                    "Fecha": day,
                    "Monto Acumulado Requerido": cumulative_amount,
                    "Cupo Acumulado Requerido": cumulative_credit_limit,
                    "Solicitudes Acumuladas Requeridas": cumulative_prospecting,
                }
            )
        # El último díe debe tener las cifras del archivo de configuración, 
        # como las divisiones pueden provocar que no se llegue al total capturado
        # en el archivo de configuración, nos aseguramos de que el último día tenga 
        # las cifras totales del archivo de configuración

        data[-1]["Monto Acumulado Requerido"] = quota
        data[-1]["Cupo Acumulado Requerido"] = quota_cupo
        data[-1]["Solicitudes Acumuladas Requeridas"] = prospecting

    # Crear el dataframe
    df = pd.DataFrame(data)
    df["Fecha"] = pd.to_datetime(df["Fecha"])

    return df


def add_cumulated_value(data, column):
    cum_name = "Cum " + column
    new_data = data.sort_values(by=["Unidad", "Fecha"])
    new_data[cum_name] = new_data.groupby("Unidad")[column].cumsum()
    return new_data


def get_count_and_amount(real_lendings, count_name, amount_name=None):


    # Agrupamos y sumamos según sea necesario
    if amount_name is not None:
        real_lendings_grp = (
            real_lendings.groupby(["Unidad", "Fecha"])["Monto"]
            .agg(["count", "sum"])
            .reset_index()
        )
        real_lendings_grp.rename(
            columns={"count": count_name, "sum": amount_name}, inplace=True
        )
    else:
        real_lendings_grp = (
            real_lendings.groupby(["Unidad", "Fecha"])["Monto"]
            .agg(["count"])
            .reset_index()
        )
        real_lendings_grp.rename(columns={"count": count_name}, inplace=True)

    return real_lendings_grp


def add_count_and_amount(
    lendings_cashia_model, original_df, credits_name, amount_name=None
):
    lendings_cashia_model_grp = get_count_and_amount(
        lendings_cashia_model, credits_name, amount_name
    )

    # Unir los dataframes
    original_df = original_df.merge(
        lendings_cashia_model_grp, on=["Unidad", "Fecha"], how="outer"
    )

    # Rellenamos los NaN en 'count_cashia' y 'total_cashia' con 0
    if amount_name is not None:
        original_df[[credits_name, amount_name]] = original_df[
            [credits_name, amount_name]
        ].fillna(0)
    else:
        original_df[credits_name] = original_df[credits_name].fillna(0)

    return original_df


def get_real_daily_lendings(all_applications):

    # Seleccionamos las solicitudes aprobadas ya sea por Cashia o de forma "Manual"
    real_lendings = all_applications[
        (all_applications["Dictamen"] == "AC") | (all_applications["Dictamen"] == "AM")
    ]

    # Con las solicitudes aprobadas creamos otro data frame por unidad y fecha
    # con el número acumulado de creditos y el monto acumulado
    real_lendings_grp = get_count_and_amount(real_lendings, "Creditos", "Monto")

    approuveb_by_cashia = all_applications[
        all_applications["Dictamen"].isin(["AC", "RM"])
    ]

    # Con las solicitudes aprobadas por Cashia creamos otro data frame por unidad y fecha
    # con el múmero de solicitudes y el monto. Después lo unimos con el data frame de
    # solicitudes aprobadas.
    merged_df = add_count_and_amount(
        approuveb_by_cashia, real_lendings_grp, "Cashia Creditos", "Cashia Monto"
    )

    # En esta línea antes téniamos únicamente ['AC', 'RM', 'RC'] porque se penaba que los AM (Aprobados manualmente)
    # No eran solicitudes que pasaban por Cashia, pero si lo son. La línea se deja solo por si en el
    # Futuro se quiere combiar el concepto de "Cashia Solicitudes".
    cashia_demands = all_applications[
        all_applications["Dictamen"].isin(["AC", "RM", "RC", "AM"])
    ]
    merged_df = add_count_and_amount(cashia_demands, merged_df, "Cashia Solicitudes")

    for model in MODELS_LIST:
        # Obtenemos el número de créditos procesados por Cashia por unidad, fecha y modelo
        lendings_cashia_model = all_applications[(all_applications["Modelo"] == model)]
        merged_df = add_count_and_amount(lendings_cashia_model, merged_df, model, None)

        # Obtenemos los creditos aprobados por Cashia por Cashia
        lendings_cashia_model = all_applications[
            (
                (all_applications["Dictamen"] == "AC")
                | (all_applications["Dictamen"] == "RM")
            )
            & (all_applications["Modelo"] == model)
        ]
        # Calculamos el número 
        # de créditos por modelos y el monto y lo concatenamos con lo
        # que ya teníamos antes
        merged_df = add_count_and_amount(
            lendings_cashia_model, merged_df, "Creditos " + model, "Monto " + model
        )

    merged_df["Cashia Creditos Nuevos"] = (
        merged_df["Creditos NV_Agt"] + merged_df["Creditos NV_CC"]
    )
    merged_df["Cashia Creditos Renovaciones"] = (
        merged_df["Creditos RNV_Agt"] + merged_df["Creditos RNV_CC"]
    )

    merged_df["Monto Nuevos"] = merged_df["Monto NV_Agt"] + merged_df["Monto NV_CC"]
    merged_df["Monto Renovaciones"] = (
        merged_df["Monto RNV_Agt"] + merged_df["Monto RNV_CC"]
    )

    return merged_df


def merge_teoretical_and_real(teoretical_lendings, real_lendings):
    real_versus_teoretical = pd.merge(
        teoretical_lendings, real_lendings, on=["Fecha", "Unidad"], how="outer"
    )
    # Como las fechas de los montos teóricos pueden ir más allá que la de los montos
    # teóricos el merge llenará los valores con nan, asi que los cambiamos a 0
    real_versus_teoretical["Monto Nuevos"] = real_versus_teoretical[
        "Monto Nuevos"
    ].fillna(0)
    real_versus_teoretical["Monto Renovaciones"] = real_versus_teoretical[
        "Monto Renovaciones"
    ].fillna(0)
    real_versus_teoretical["Monto"] = real_versus_teoretical["Monto"].fillna(0)
    real_versus_teoretical["Creditos"] = real_versus_teoretical["Creditos"].fillna(0)

    real_versus_teoretical["Cashia Monto"] = real_versus_teoretical[
        "Cashia Monto"
    ].fillna(0)
    real_versus_teoretical["Cashia Creditos Nuevos"] = real_versus_teoretical[
        "Cashia Creditos Nuevos"
    ].fillna(0)
    real_versus_teoretical["Cashia Creditos Renovaciones"] = real_versus_teoretical[
        "Cashia Creditos Renovaciones"
    ].fillna(0)
    real_versus_teoretical["Cashia Creditos"] = real_versus_teoretical[
        "Cashia Creditos"
    ].fillna(0)
    real_versus_teoretical["Cashia Solicitudes"] = real_versus_teoretical[
        "Cashia Solicitudes"
    ].fillna(0)

    for model in MODELS_LIST:
        # Rellenamos los NaN en 'count_cashia' y 'total_cashia' con 0
        real_versus_teoretical[model] = real_versus_teoretical[model].fillna(0)
        real_versus_teoretical[["Creditos " + model, "Monto " + model]] = (
            real_versus_teoretical[["Creditos " + model, "Monto " + model]].fillna(0)
        )

    return real_versus_teoretical


def add_real_cumulated_amounts(real_versus_teoretical):
    real_versus_teoretical = real_versus_teoretical.sort_values(by=["Unidad", "Fecha"])
    real_versus_teoretical["Monto Acumulado Real"] = real_versus_teoretical.groupby(
        "Unidad"
    )["Monto"].cumsum()
    real_versus_teoretical["Creditos Acumulados"] = real_versus_teoretical.groupby(
        "Unidad"
    )["Creditos"].cumsum()

    return real_versus_teoretical


def add_cashia_cumulated_amounts(real_versus_teoretical):

    # Ordenamos el DataFrame por 'Unidad' y 'Fecha' (si no está ya ordenado)
    real_versus_teoretical = real_versus_teoretical.sort_values(by=["Unidad", "Fecha"])

    # Inicializamos las columnas con acumulación condicional
    real_versus_teoretical["Cashia Monto Acumulado"] = real_versus_teoretical.groupby(
        "Unidad"
    )["Cashia Monto"].cumsum()
    real_versus_teoretical["Cashia Creditos Acumulados"] = (
        real_versus_teoretical.groupby("Unidad")["Cashia Creditos"].cumsum()
    )
    real_versus_teoretical["Cashia Solicitudes Acumuladas"] = (
        real_versus_teoretical.groupby("Unidad")["Cashia Solicitudes"].cumsum()
    )

    for model in MODELS_LIST:
        real_versus_teoretical["Monto Acumulado " + model] = (
            real_versus_teoretical.groupby("Unidad")["Monto " + model].cumsum()
        )
        real_versus_teoretical["Acumulado " + model] = real_versus_teoretical.groupby(
            "Unidad"
        )[model].cumsum()
        real_versus_teoretical["Creditos Acumulados " + model] = (
            real_versus_teoretical.groupby("Unidad")["Creditos " + model].cumsum()
        )

    real_versus_teoretical["Acumulado Nuevos"] = (
        real_versus_teoretical["Acumulado NV_Agt"]
        + real_versus_teoretical["Acumulado NV_CC"]
    )
    real_versus_teoretical["Acumulado Renovaciones"] = (
        real_versus_teoretical["Acumulado RNV_Agt"]
        + real_versus_teoretical["Acumulado RNV_CC"]
    )

    real_versus_teoretical["Creditos Acumulados Nuevos"] = (
        real_versus_teoretical["Creditos Acumulados NV_Agt"]
        + real_versus_teoretical["Creditos Acumulados NV_CC"]
    )
    real_versus_teoretical["Creditos Acumulados Renovaciones"] = (
        real_versus_teoretical["Creditos Acumulados RNV_Agt"]
        + real_versus_teoretical["Creditos Acumulados RNV_CC"]
    )

    real_versus_teoretical["Monto Acumulado Nuevos"] = (
        real_versus_teoretical["Monto Acumulado NV_Agt"]
        + real_versus_teoretical["Monto Acumulado NV_CC"]
    )
    real_versus_teoretical["Monto Acumulado Renovaciones"] = (
        real_versus_teoretical["Monto Acumulado RNV_Agt"]
        + real_versus_teoretical["Monto Acumulado RNV_CC"]
    )

    return real_versus_teoretical


def add_errors(real_versus_teoretical, date):
    required_values = storage.read_excel(RISK_FILE_KEY)
    required_values["Cashia %Aprobado Requerido"] = required_values[
        "Cashia %Aprobado Requerido"
    ].astype(float)

    # Get the las changes stats
    week, month, year = get_week_month_year_from_file(date)

    required_values = required_values[
        (required_values["Mes"] == month) & (required_values["Año"] == year)
    ]

    real_versus_teoretical["Error en monto"] = (
        real_versus_teoretical["Cupo Acumulado Requerido"]
        - real_versus_teoretical["Monto Acumulado Real"]
    )

    real_versus_teoretical["Porcentaje"] = (
        real_versus_teoretical["Monto Acumulado Real"]
        / real_versus_teoretical["Cupo Acumulado Requerido"]
        - 1
    )

    real_versus_teoretical["Ticket Promedio"] = (
        real_versus_teoretical["Monto Acumulado Real"]
        // real_versus_teoretical["Creditos Acumulados"]
    )

    real_versus_teoretical["Ticket Promedio Nuevos"] = real_versus_teoretical.apply(
        lambda row: (
            row["Monto Acumulado Nuevos"] // row["Creditos Acumulados Nuevos"]
            if row["Creditos Acumulados Nuevos"] != 0
            else 0
        ),
        axis=1,
    )

    real_versus_teoretical["Ticket Promedio Renovaciones"] = (
        real_versus_teoretical.apply(
            lambda row: (
                row["Monto Acumulado Renovaciones"]
                // row["Creditos Acumulados Renovaciones"]
                if row["Creditos Acumulados Renovaciones"] != 0
                else 0
            ),
            axis=1,
        )
    )

    real_versus_teoretical["Cashia Ticket Promedio"] = (
        real_versus_teoretical["Cashia Monto Acumulado"]
        // real_versus_teoretical["Cashia Creditos Acumulados"]
    )

    # Combina los DataFrames para obtener 'Monto promedio' junto a 'Ticket promedio'
    merged_df = real_versus_teoretical.merge(
        required_values[
            [
                "Unidad",
                "Cashia Ticket Promedio Requerido Nuevos",
                "Cashia Ticket Promedio Requerido Renovaciones",
                "Cashia Ticket Promedio Requerido",
                "Cashia %Aprobado Requerido",
            ]
        ],
        on="Unidad",
    )

    # Calcula la diferencia
    merged_df["Error en Ticket Nuevos"] = (
        merged_df["Cashia Ticket Promedio Requerido Nuevos"]
        - merged_df["Ticket Promedio Nuevos"]
    )
    merged_df["Error en Ticket Renovaciones"] = (
        merged_df["Cashia Ticket Promedio Requerido Renovaciones"]
        - merged_df["Ticket Promedio Renovaciones"]
    )
    merged_df["Error en Ticket"] = (
        merged_df["Cashia Ticket Promedio Requerido"]
        - merged_df["Cashia Ticket Promedio"]
    )

    # Calculamos el error de % de aprobación
    merged_df["Cashia Error %Aprobado"] = (
        merged_df["Cashia %Aprobado Requerido"] - merged_df["%Acum Aprobado por Cashia"]
    )

    # Calculamos el error de % del dia
    merged_df["Day Error %Aprobado"] = (
        merged_df["Cashia %Aprobado Requerido"] - merged_df["%Aprobado por Cashia"]
    )

    for model in MODELS_LIST:

        # Calculamos el error de % del dia
        merged_df["Day Error %Aprobado " + model] = np.where(
            merged_df["%Aprobado " + model] == -1,
            0, # Si no hay créditos aprobados no hay error (-1 indica que no hay créditos)
            merged_df["Cashia %Aprobado Requerido"] - merged_df["%Aprobado " + model],
        )


        merged_df["Ticket Promedio " + model] = merged_df.apply(
            lambda row: (
                row["Monto Acumulado " + model] // row["Creditos Acumulados " + model]
                if row["Creditos Acumulados " + model] != 0
                else 0
            ),
            axis=1,
        )

        merged_df["Error %Aprobado " + model] = np.where(
            merged_df["Acumulado " + model] == 0,
            0, # Si no hay créditos aprobados no hay error
            merged_df["Cashia %Aprobado Requerido"]
            - merged_df["%Acum Aprobado " + model],
        )

        merged_df["Error en Ticket " + model] = (
            merged_df["Cashia Ticket Promedio Requerido"]
            - merged_df["Ticket Promedio " + model]
        )

    return merged_df


def add_credit_application_opinion_columns(all_applications, real_versus_teoretical):
   # Agrupa por 'Unidad' y 'Fecha' y crea columnas para cada valor de  'Dictamen' por medio de unstack(fill_value=0)
    count_df = (
        all_applications.groupby(["Unidad", "Fecha", "Dictamen"])
        .size()
        .unstack(fill_value=0)
    )

    # Obtenemos las columnas de opinión presentes en las solicitudes
    opinion_columns = sorted(all_applications["Dictamen"].unique().tolist())

    # Para las opiniones que no han aparecido en los datos creamos la columna y la llenamos con 0
    for opinion in OPINIONS_LIST:
        if opinion not in opinion_columns:
            count_df[opinion] = 0

    # Une los conteos con el DataFrame original
    final_count = (
        all_applications[["Unidad", "Fecha"]]
        .drop_duplicates()
        .merge(count_df, on=["Unidad", "Fecha"], how="left")
    )

    # Unimos las nuevas estadísticas del conteo con lo que ya teníamos
    sales_stats = pd.merge(
        real_versus_teoretical, final_count, on=["Fecha", "Unidad"], how="outer"
    )

    # Llenamos las columnas nulas con 0 y cambiamos el tipo
    sales_stats[OPINIONS_LIST] = sales_stats[OPINIONS_LIST].fillna(0)
    sales_stats[OPINIONS_LIST] = sales_stats[OPINIONS_LIST].astype(int)

    # Agregamos los valores acumulados
    for opinion in OPINIONS_LIST:
        sales_stats = add_cumulated_value(sales_stats, opinion)

    return sales_stats


def add_chosen_amount_columns(all_applications, real_versus_teoretical):
    for selection in AMOUNT_SELECTION_COLUMNS:
        count_df = (
            all_applications.groupby(["Unidad", "Fecha"])[selection].sum().reset_index()
        )
        count_df.rename(columns={selection: selection}, inplace=True)

        if count_df.empty:
            count_df[selection] = 0

        real_versus_teoretical = pd.merge(
            real_versus_teoretical, count_df, on=["Unidad", "Fecha"], how="outer"
        )

    # Llenamos las columnas nulas con 0 y cambiamos el tipo
    real_versus_teoretical[AMOUNT_SELECTION_COLUMNS] = real_versus_teoretical[
        AMOUNT_SELECTION_COLUMNS
    ].fillna(0)
    real_versus_teoretical[AMOUNT_SELECTION_COLUMNS] = real_versus_teoretical[
        AMOUNT_SELECTION_COLUMNS
    ].astype(int)

    for selection in AMOUNT_SELECTION_COLUMNS:
        real_versus_teoretical = add_cumulated_value(real_versus_teoretical, selection)

    return real_versus_teoretical


def add_aprovals_rating(sales_stats):
    # Calculamos el porcentaje de aprobación
    sales_stats["%Aprobado por Cashia"] = (sales_stats["AC"] + sales_stats["RM"]) / (
        sales_stats["AC"] + sales_stats["RC"] + sales_stats["RM"]
    )
    sales_stats["%Aprobado final Cashia"] = sales_stats["AC"] / (
        sales_stats["AC"] + sales_stats["RC"] + sales_stats["RM"]
    )
    sales_stats["%Aprobado Manual"] = sales_stats["AM"] / (
        sales_stats["AC"] + sales_stats["RC"] + sales_stats["RM"]
    )
    sales_stats["%Aprobado"] = (sales_stats["AC"] + sales_stats["AM"]) / (
        sales_stats["AM"] + sales_stats["AC"] + sales_stats["RC"] + sales_stats["RM"]
    )

    # Para los valores donde aun no hay datos ponemos 0
    sales_stats["%Aprobado por Cashia"] = sales_stats["%Aprobado por Cashia"].fillna(0)
    sales_stats["%Aprobado final Cashia"] = sales_stats[
        "%Aprobado final Cashia"
    ].fillna(0)
    sales_stats["%Aprobado Manual"] = sales_stats["%Aprobado Manual"].fillna(0)
    sales_stats["%Aprobado"] = sales_stats["%Aprobado"].fillna(0)

  # Calculamos el porcentaje de aprobación acumulado
    sales_stats["%Acum Aprobado por Cashia"] = (
        sales_stats["Cum AC"] + sales_stats["Cum RM"]
    ) / (sales_stats["Cum AC"] + sales_stats["Cum RC"] + sales_stats["Cum RM"])
    sales_stats["%Acum Aprobado final Cashia"] = (sales_stats["Cum AC"]) / (
        sales_stats["Cum AC"] + sales_stats["Cum RC"] + sales_stats["Cum RM"]
    )
    sales_stats["%Acum Aprobado Manual"] = sales_stats["Cum AM"] / (
        sales_stats["Cum AM"] + sales_stats["Cum RM"]
    )
    sales_stats["%Acum Aprobado"] = (sales_stats["Cum AC"] + sales_stats["Cum AM"]) / (
        sales_stats["Cum AM"]
        + sales_stats["Cum RM"]
        + sales_stats["Cum AC"]
        + sales_stats["Cum RC"]
    )

    # Para los valores donde aun no hay datos ponemos 0
    sales_stats["%Acum Aprobado por Cashia"] = sales_stats[
        "%Acum Aprobado por Cashia"
    ].fillna(0)
    sales_stats["%Acum Aprobado final Cashia"] = sales_stats[
        "%Acum Aprobado final Cashia"
    ].fillna(0)
    sales_stats["%Acum Aprobado Manual"] = sales_stats["%Acum Aprobado Manual"].fillna(
        0
    )
    sales_stats["%Acum Aprobado"] = sales_stats["%Acum Aprobado"].fillna(0)

    for model in MODELS_LIST:
        # Calculamos el porcentaje de créditos aprobados por el modelo
        sales_stats["%Aprobado " + model] = np.where(
            sales_stats[model] == 0,
            -1,
            sales_stats["Creditos " + model] / sales_stats[model],
        )

        approved = "Creditos Acumulados " + model
        total = "Acumulado " + model
        cumulative_percentage = "%Acum Aprobado " + model

        sales_stats[cumulative_percentage] = sales_stats[approved] / sales_stats[total]
        sales_stats[cumulative_percentage] = sales_stats[cumulative_percentage].fillna(
            0
        )

    return sales_stats


def generate_cumulated_amounts(units, first_day, today, end_of_the_month):
    # 1 Obtenemos los montos efectivamente prestados por Unidad y Fecha
    all_applications = get_all_applications(first_day, today, units)
    # all_applications sera None si el metodo get_all_applications no se pudo conectar a la base de datos
    if all_applications.empty:
        return {}

    # Agregamos las columnas 'Cashia Creditos', 'Cashia Monto' y 'Cashia Solicitudes'
    real_lendings = get_real_daily_lendings(all_applications)

    # 2 Obtenemos los montos teóricos de colocación (ventas) diaria
    teoretical_lendings = get_theoretical_daily_lendings(
        first_day, end_of_the_month, units
    )

    if teoretical_lendings.empty:
        return {}
    # 3 Comobinamos los montos reales con los teóricos
    all_stats = merge_teoretical_and_real(teoretical_lendings, real_lendings)
    # 4 Calculamos los montos y créditos acumulados para cada fecha totales
    all_stats = add_real_cumulated_amounts(all_stats)
    # 5 Calculamos los montos y créditos acumulados para cada fecha de *cashia*
    all_stats = add_cashia_cumulated_amounts(all_stats)

    return {"stats": all_stats, "applications": all_applications}


def generate_cashia_daily_stats(units, first_day, today, end_of_the_month):
    # 1 Calcular los montos totales acumulados así com los montos acumulados por Cashia
    credits_data = generate_cumulated_amounts(units, first_day, today, end_of_the_month)
    if not credits_data:
        return {}

    all_stats = credits_data["stats"]
    all_applications = credits_data["applications"]

    # 2 Agregamos las columnas con el conteo de las recomendaciones de las solicitudes
    # Aceptado por Cashia (AC), Aceptado Manual (AM), Rechazado Cashia (RC), Rechazado Manual (RM)
    all_stats = add_credit_application_opinion_columns(all_applications, all_stats)
    all_stats = add_chosen_amount_columns(all_applications, all_stats)
    # 3 Calculamos los porcentajes de aprobación
    all_stats = add_aprovals_rating(all_stats)
    # 4 Calculamos la diferencia entre los acumulados teóricos y los montos reales
    all_stats = add_errors(all_stats, today)
    # 6 Reordenamos el dataframe
    all_stats = all_stats[REPORT_COLUMNS]
    # Convertir la Fecha a data, porque hasta ahora es datetime, esto evitará errores en comparaciones de fechas
    all_stats["Fecha"] = all_stats["Fecha"].dt.date

    return {"stats": all_stats, "applications": all_applications}
