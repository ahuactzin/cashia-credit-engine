import schedule
import time
from art import text2art
import traceback

from cashia_credit_engine.config import RISK_FILE_KEY
from cashia_credit_engine.lending import *
from cashia_credit_engine.db_manager import *
from cashia_credit_engine.ponderation_inverser import *
from cashia_credit_engine.tools import *

from cashia_core.common_tools.configuration.cashiaconstants import *
from cashia_core.common_tools.storage import get_storage
from cashia_core.common_tools.configuration.resource_keys import get_resource_path


num_intervals = 100
storage = get_storage()
CONFIG_FILE_KEY = get_resource_path("configuration")

# Parámetros
Kp = 0.25  # Ganancia proporcional
Ki = 0.025  # Ganancia integral
Kd = 0.125  # Ganancia derivativa

# Parámetros
PKp = 0.3  # Ganancia proporcional
PKi = 0.03  # Ganancia integral
PKd = 0.15  # Ganancia derivativa


def update_ponderations(epsilons, parameters, PKp):

    new_ponderation = {}
    for model in MODELS_LIST:

        print(f"\n\tModel_ {model}")

        # Calculamos una nueva ponderación sólo si es necesario
        if parameters[model]["average amount"] != 0:

            # Construimos el ponderador con los parámetros del modelo
            ponderator = PonderationInverser(
                parameters[model]["threshold"],
                parameters[model]["base amount"],
                parameters[model]["max amount"],
            )

            # Obtenemos las ponderaciones teóricas del monto actual y el deseado
            current_theoretical_ponderation = ponderator.ponderation_from_mean_amount(
                parameters[model]["average amount"]
            )
            objective_theoretical_ponderation = ponderator.ponderation_from_mean_amount(
                parameters[model]["average amount"] + epsilons[model]
            )

            # Calculamos el error de ponderación
            p_error = (
                objective_theoretical_ponderation - current_theoretical_ponderation
            )

            print(
                f"\tCurrent ponderation: {parameters[model]['ponderation']:<10.2f} Current amount: {parameters[model]['average amount']:<10,.2f} Objective amount:{parameters[model]['average amount']+epsilons[model]:<10,.2f}"
            )
            print(
                f"\tCurrent theoretical ponderation: {current_theoretical_ponderation:<10.2f} Objective theoretical ponderation:{objective_theoretical_ponderation:<10.2f}"
            )
            print(f"\tp_error = {p_error:<10.2f}  ponderated p_error = {p_error*PKp:<10.2f}")

            # La nueva ponderación se calcula en función del error

            # Calculamos la nueva ponderación sin permitir salir del minimo y máximo de la ponderación
            new_model_ponderaration = max(
                MIN_ALLOWED_PONDERATION,
                min(
                    parameters[model]["ponderation"] + PKp * p_error,
                    ponderator.max_ponderation,
                ),
            )

            new_ponderation[model] = new_model_ponderaration

            print(f"\tNew ponderation: {new_ponderation[model]:<10.2f}")

        else:
            print("\tNo new ponderation needed")

    return new_ponderation


def update_threshold(
    error, threshold, Kp, Ki, Kd, integral, previous_error, unit, model
):

    # Calcular término derivativo
    derivative = error - previous_error

    # Ajustar el threshold
    new_threshold = threshold + Kp * error + Ki * integral + Kd * derivative

    # print(f"Error: {error} | Integral: {integral} | Previous error: {previous_error}")
    # print(f"KP*Error: {Kp*error} | Ki*Integral: {Ki*integral} | Kd*derivative: {Kd*derivative}")
    # No dejamos que el threshold salga de sus límites
    if new_threshold < MIN_ALLOWED_THRESHOLD[unit][model]:
        new_threshold = MIN_ALLOWED_THRESHOLD[unit][model]
    if new_threshold > MAX_ALLOWED_THRESHOLD[unit][model]:
        new_threshold = MAX_ALLOWED_THRESHOLD[unit][model]

    return new_threshold


def get_changes_stats(month, year, table_name):
    # Leer la base de datos donde llevamos el control de los camios
    stats_df = read_from_data_base(table_name)

    # Obtener el último IdProcesado
    if not stats_df.empty:

        # Seleccionamos las estadísticas para el mes promocash y año actuales
        stats_df = stats_df[(stats_df["Month"] == month) & (stats_df["Year"] == year)]

    return stats_df


def update_thresholds_for_unit(
    unit,
    unit_stats,
    unit_applications,
    new_cashia_parameters,
    required_unit_acceptance_rate,
    month,
    year,
    end_date,
):

    updates = []

    for model in MODELS_LIST:

        # Recuperamos todas las solicitudes con el modelo
        unit_model_applications = unit_applications[
            unit_applications["Modelo"] == model
        ]

        # Obtenemos las estadísticas de la base de datos para el modelo
        unit_model_stats = unit_stats[unit_stats["Model"] == model]

        # Si ya hay actualizacones anteriores al modelo recuperamos sólo las solicitudes despues
        # de la fecha de la última actualización
        if not unit_model_stats.empty:
            previous_acceptance_error = unit_model_stats.loc[
                unit_model_stats["Date"].idxmax(), "Error"
            ]
            integral_of_error = unit_model_stats["Error"].sum()
            last_uptade_date = unit_model_stats.loc[
                unit_model_stats["Date"].idxmax(), "Date"
            ]
            last_processed_id = unit_model_stats.loc[
                unit_model_stats["Date"].idxmax(), "Last_id"
            ]

            # Obtenemos el indice del id de la última solicitud procesada
            index_of_last_processed_id = unit_model_applications[
                unit_model_applications["IdSolicitud"] == last_processed_id
            ].index

            # Filtramos las solicitudes recibidas despues de la fecha de la última actualización
            try:
                new_unit_model_applications = unit_model_applications[
                    unit_model_applications.index > index_of_last_processed_id[0]
                ]
            except:
                # Se entrará a la excepción si el último registro procesado se ha borrado de la
                # base de datos, es decir es una solicitud cancelada
                print(
                    f"\t***** WARNING: IdSolicitid number {last_processed_id} not found in registers"
                )
                print("\tUsing alternative delection for new registers")
                new_unit_model_applications = unit_model_applications[
                    unit_model_applications["IdSolicitud"] > last_processed_id
                ]

        else:
            previous_acceptance_error = 0
            integral_of_error = 0
            last_uptade_date = None
            last_processed_id = None
            new_unit_model_applications = unit_model_applications

        num_applications = len(new_unit_model_applications)

        print(
            f"\n\tModel: {model} | Last Update: {last_uptade_date} | Previous Last Application Id: {last_processed_id} | Number of applications: {num_applications}"
        )

        # Si no hay solicitudes en este modelo pasamos al siguiente
        if num_applications < MIN_MODEL_SAMPLES_TO_UPDATE_THRESHOLD[unit][model]:
            print("\tNot enough applications for threshold update, skipping update")
            continue

        new_last_processed_id = int(new_unit_model_applications.iloc[-1]["IdSolicitud"])
        num_accepted_applications = len(
            new_unit_model_applications[
                new_unit_model_applications["Dictamen"].isin(["AC", "RM"])
            ]
        )
        acceptance_rate = num_accepted_applications / num_applications

        apceptance_error = required_unit_acceptance_rate - acceptance_rate

        print(
            f"\tNew last application id {new_last_processed_id} | Number of accepted applications {num_accepted_applications} "
        )
        print(
            f"\tAcceptance rate: {acceptance_rate:.2} | Required acceptance rate: {required_unit_acceptance_rate:.2} | Acceptance error: {apceptance_error:.2}"
        )

        threshold = new_cashia_parameters.loc[
            (new_cashia_parameters["unit"] == unit)
            & (new_cashia_parameters["model"] == model),
            "threshold",
        ].iloc[0]

        new_threshold = update_threshold(
            apceptance_error,
            threshold,
            Kp,
            Ki,
            Kd,
            integral_of_error,
            previous_acceptance_error,
            unit,
            model,
        )

        new_cashia_parameters.loc[
            (new_cashia_parameters["unit"] == unit)
            & (new_cashia_parameters["model"] == model),
            "threshold",
        ] = new_threshold

        print(f"\tThreshold: {threshold:<6.2f} | New threshold: {new_threshold:<6.2f}")
        # print(f"\tponderation: {ponderation}, \tnew ponderation: {new_ponderation}\n")

        time_of_update = datetime.now().strftime("%H:%M:%S")

        model_update = {
            "Date": end_date,
            "Time": time_of_update,
            "Month": str(month),
            "Year": year,
            "Last_id": new_last_processed_id,
            "Unit": unit,
            "Model": model,
            "Previous_error": previous_acceptance_error,
            "Error": apceptance_error,
            "Previous_threshold": threshold,
            "Threshold": new_threshold,
        }

        updates.append(model_update)

    number_of_manuel_applications = len(
        unit_applications[unit_applications["Modelo"] == "Manual"]
    )
    print(f"\n\tNumber of Manual applications: {number_of_manuel_applications}")

    return updates, new_cashia_parameters


def compute_weigthted_error(data):
    # Calcular el error ponderado
    total_weighted_error = sum(
        item["Error"] * item["Number_of_demands"] for item in data
    )
    total_credits = sum(item["Number_of_demands"] for item in data)

    weighted_error = total_weighted_error / total_credits if total_credits != 0 else 0

    return weighted_error

def safe_mean(series, default=0):
    value = series.mean()
    return default if pd.isna(value) else value

def update_ponderation_for_unit(
    unit,
    all_stats,
    ponderation_stats,
    applications,
    cashia_parameters,
    new_cashia_parameters,
    nv_required_average_ticket,
    rnv_required_average_ticket,
    required_average_ticket,
    month,
    year,
    end_date,
):

    today_stats = all_stats[all_stats["Fecha"] == end_date]

    # Recuperar la información necesaria para realizar la sigiente actualización
    status = get_applications_status(applications, ponderation_stats)
    nv_previous_amount_error = status["nv_previous_amount_error"]
    rnv_previous_amount_error = status["rnv_previous_amount_error"]
    previous_amount_error = status["previous_amount_error"]
    last_update_date = status["last_update_date"]
    last_processed_id = status["last_processed_id"]
    new_models_applications = status["new_models_applications"]

    current_number_of_demands = len(new_models_applications)

    print(
        f"\n\t**** Last Update: {last_update_date} | Previous Last Application Id: {last_processed_id} | Number of demands: {current_number_of_demands} ****"
    )

    if current_number_of_demands < MIN_SAMPLES_TO_UPDATE_PONDERATION[unit]:
        print("\tNot enough applications for ponderation update, skipping update")
        # No se agregan cambios a la lista de cambios de ahí que enviemos la lista vacia []
        return [], new_cashia_parameters

    # Obtener el id del último registro procesado
    new_last_processed_id = int(new_models_applications.iloc[-1]["IdSolicitud"])

    # Obtener las metricas del monto acumulado real y requerido de una unidad
    metrics = CumulatedAmountMetrics(today_stats, unit)

    # Obtenemos la fecha más próxima en que el monto acumulado debería estar, los dias edelantados
    # (o atrazados) y si es fin de mes o no. Hacemos un .copy() para evitar un warning dentro de
    # la función
    closest_date, days_ahead, is_end_of_month = find_closest_date(
        all_stats[all_stats["Unidad"] == unit].copy(), metrics.real_amount, end_date
    )
    # Obtenemos los tickets promedio
    nv_current_average_ticket = safe_mean(
        new_models_applications[
            new_models_applications["Modelo"].isin(NEW_CREDITS_MODELS)
        ]["Monto"],
        default=nv_required_average_ticket
    )

    rnv_current_average_ticket = safe_mean(
        new_models_applications[
            new_models_applications["Modelo"].isin(RENEWAL_CREDITS_MODELS)
        ]["Monto"],
        default=rnv_required_average_ticket
    )

    current_average_ticket = safe_mean(
        new_models_applications["Monto"],
        default=required_average_ticket
    )

    # Si e monto acumulado hasta el momento esta adelantado de tres o más días realizamos una
    # actualización de la ponderación regida por el monto acumulado
    if days_ahead >= MAX_DAYS_AHEAD:
        # Recalculamos el ticket promedio requerido (ignoramos el ticket promedio establecido en la configuración)
        required_average_ticket = (
            1.0 - metrics.percentage_amount_error
        ) * current_average_ticket
        ponderation_update_type = CUMULATIVE_AMOUNT
    else:
        ponderation_update_type = AVERAGE_TICKET

    print(f"******** Regulating ponderation by: {ponderation_update_type} ********")

    print(
        f"\n\tActual Accumulated Amount: {metrics.real_amount:,.0f} | Required Accumulated Amount: {metrics.required_amount:,.0f} | ",
        end="",
    )
    print(
        f"Accumulated Amount Error: {metrics.amount_error:,.0f} | Error in %: {metrics.percentage_amount_error*100:.1f}%"
    )
    print(
        f"\tClosest date {closest_date} | Gap in days: {days_ahead} | End of month: {is_end_of_month}"
    )

    nv_current_error = nv_required_average_ticket - nv_current_average_ticket
    rnv_current_error = rnv_required_average_ticket - rnv_current_average_ticket
    current_error = required_average_ticket - current_average_ticket

    print(
        f"\n\tCurrent average ticket: {current_average_ticket:,.0f} | required average ticket: {required_average_ticket:,.0f} | Error: {current_error}"
    )
    # print(f"\tNew last application id {new_last_processed_id}")

    # Obtener las metricas de los modelos y sus parámetros Cashia
    average_amounts_list, number_of_demands_list, parameters_dic = (
        compute_demand_metrics(new_models_applications, cashia_parameters, unit)
    )

    # print(f"\tAverage amount list {average_amounts_list}")
    # Los epsilos es la cantidad que debe cambiar cada moelo para llegar al promedio deseado
    epsilons = get_epsilons(
        required_average_ticket, average_amounts_list, number_of_demands_list
    )

    # Construimos el diccionario de epsilons
    model_epsilon_dict = dict(zip(MODELS_LIST, epsilons))

    # Obtenemos las nuevas ponderasiones
    new_ponderations = update_ponderations(model_epsilon_dict, parameters_dic, PKp)

    time_of_update = datetime.now().strftime("%H:%M:%S")

    # Preparamos el diccionario con los datos de la actualización
    models_update = {
        "Date": end_date,
        "Time": time_of_update,
        "Month": str(month),
        "Year": year,
        "Last_id": new_last_processed_id,
        "Unit": unit,
        "Update_type": ponderation_update_type,
        "Number_of_demands": current_number_of_demands,
        "Avg_NV_amount": nv_current_average_ticket,
        "Avg_NV_requested_amount": nv_required_average_ticket,
        "NV_previous_error":nv_previous_amount_error,
        "NV_error":nv_current_error,
        "Avg_RNV_amount": rnv_current_average_ticket,
        "Avg_RNV_requested_amount": rnv_required_average_ticket,
        "RNV_previous_error":rnv_previous_amount_error,
        "RNV_error":rnv_current_error,
        "Avg_Amount": current_average_ticket,
        "Avg_Requested_Amount": required_average_ticket,
        "Previous_error": previous_amount_error,
        "Error": current_error,
    }

    # Terminar de llenar los datos de la actualización que será registrado (models_update) y
    # los nuevos parámetros (new_cashia_parameters)
    models_update, new_cashia_parameters = fill_models_update_data(
        unit, models_update, parameters_dic, new_ponderations, new_cashia_parameters
    )

    return [models_update], new_cashia_parameters


"""
===============================================================================
                    execute_parameters_correction                                                             
===============================================================================
"""


def execute_parameters_correction(units, start_date, today, end_of_the_month):
    print(
        f"\n===================================={today}============================================="
    )

    # Get the las changes stats
    week, month, year = get_week_month_year_from_file(today)

    # Leer el archivo de configuración del CCE
    # required_values = pd.read_excel(INPUT_DIR + RISK_FILE)
    required_values = storage.read_excel(RISK_FILE_KEY)

    # Nos aseguramos que la columna sea de tipo float.
    required_values["Cashia %Aprobado Requerido"] = required_values[
        "Cashia %Aprobado Requerido"
    ].astype(float)
    # Seleccionamos los datos para el mes y año
    required_values = required_values[
        (required_values["Mes"] == month) & (required_values["Año"] == year)
    ]

    if required_values.empty:
        print(
            f"****** WARNING: No configuration for month:{month} and year {year} ******"
        )
        return False

    credits_data = generate_cashia_daily_stats(
        units, start_date, today, end_of_the_month
    )
    # credits_data sera None si no se pudo conectar a la base de datos
    if not credits_data:
        print(
            f"****** WARNING: Failed to connect to the database, no transactions found or no configuration for current month ******"
        )
        return False

    all_stats = credits_data["stats"]
    all_applications = credits_data["applications"]

    today_stats = all_stats[all_stats["Fecha"] == today]

    # Recuperar todas las solicitudes de la fecha inicial a end_date
    # all_applications = get_all_applications(start_date, today, UNITS_TO_UPGRADE)

    # Leer el archivo de configuración de cashia
    try:
        cashia_parameters = storage.read_excel(CONFIG_FILE_KEY, index_col=0)
        new_cashia_parameters = cashia_parameters.copy()
    except Exception as e:
        print(f"File {CONFIG_FILE_KEY} could not be read")
        print(f"Error type: {type(e).__name__}")
        print(f"Error message: {e}")
        return False

    # Leer la base de datos donde llevamos el control de los camios para el mes y año actuales
    thresholds_stats_df = get_changes_stats(month, year, CCE_THRESHOLD_STATS_TABLE)
    ponderation_stats_df = get_changes_stats(month, year, CCE_PONDERATION_STATS_TABLE)

    all_units_threshold_updates = []
    all_units_ponderation_updates = []

    for unit in units:

        print("\nUnit:", unit)

        # Obtenemos las estadísticas para la unidad
        threshold_unit_stats = thresholds_stats_df[thresholds_stats_df["Unit"] == unit]
        ponderation_unit_stats = ponderation_stats_df[
            ponderation_stats_df["Unit"] == unit
        ]

        # Obtenemos las solicitudes para la unidad
        unit_applications = all_applications[all_applications["Unidad"] == unit]

        print(
            "\t+++++++++++++++++++++++++++++++++++  THRESHOLD UPDATE +++++++++++++++++++++++++++++++++++"
        )

        # result = required_values.loc[
        #     required_values["Unidad"] == unit, "Cashia %Aprobado Requerido"
        # ]

        # print(f"Result of required acceptance rate search: {result}")

        required_unit_acceptance_rate = required_values.loc[
            required_values["Unidad"] == unit, "Cashia %Aprobado Requerido"
        ].iloc[0]

        # Get the updates for all the models of the unit
        unit_threshold_updates, new_cashia_parameters = update_thresholds_for_unit(
            unit,
            threshold_unit_stats,
            unit_applications,
            new_cashia_parameters,
            required_unit_acceptance_rate,
            month,
            year,
            today,
        )

        all_units_threshold_updates = (
            all_units_threshold_updates + unit_threshold_updates
        )

        print(
            "\t+++++++++++++++++++++++++++++++++++  PONDERATION UPDATE +++++++++++++++++++++++++++++++++++"
        )


        required_average_ticket = get_requested_average_ticket(
            unit, required_values, "Cashia Ticket Promedio Requerido"
        )
        nv_required_average_ticket = get_requested_average_ticket(
            unit, required_values, "Cashia Ticket Promedio Requerido Nuevos"
        )
        rnv_required_average_ticket = get_requested_average_ticket(
            unit, required_values, "Cashia Ticket Promedio Requerido Renovaciones"
        )


        unit_ponderation_updates, new_cashia_parameters = update_ponderation_for_unit(
            unit,
            all_stats,
            ponderation_unit_stats,
            unit_applications,
            cashia_parameters,
            new_cashia_parameters,
            nv_required_average_ticket,
            rnv_required_average_ticket,
            required_average_ticket,
            month,
            year,
            today,
        )

        all_units_ponderation_updates = (
            all_units_ponderation_updates + unit_ponderation_updates
        )

    if all_units_threshold_updates or all_units_ponderation_updates:
        try:
            storage.write_excel(CONFIG_FILE_KEY, new_cashia_parameters)

        except Exception as e:
            print(f"\tCould not update file: {CONFIG_FILE_KEY}")
            print(f"\tError type: {type(e).__name__}")
            print(f"\tError message: {e}")
            print("\tTraceback:")
            traceback.print_exc()
            return False

    if all_units_threshold_updates:
        try:
            # Solo registramos los cambios si se logró modificar el archivo de configuración
            for update in all_units_threshold_updates:
                insert_into_cce_database(update, THRESHOLD_CHANGE)

        except Exception as e:
            # Imprimir un mensaje de error detallado
            print(f"\tCould not update data base")
            print(f"\tError type: {type(e).__name__}")
            print(f"\tError message: {e}")
            print("\tTraceback:")
            traceback.print_exc()  # Imprime el stack trace completo
            return False

        print("\n\tThresholds updated")
    else:
        print("\n\tNo thresholds update required")

    if all_units_ponderation_updates:
        try:
            for update in all_units_ponderation_updates:
                insert_into_cce_database(update, PONDERATION_CHANGE)

        except Exception as e:
            # Imprimir un mensaje de error detallado
            print(f"\tCould not update data base")
            print(f"\tError type: {type(e).__name__}")
            print(f"\tError message: {e}")
            print("\tTraceback:")
            traceback.print_exc()  # Imprime el stack trace completo
            return False

        print("\n\tPonderation updated")
    else:
        print("\n\tNo ponderation update required")

    return True


def udpate_cashia_parameters():

    start_date, today, end_of_the_month = get_interval_dates()

    print(
        f"\n First day {start_date} today: {today} End of the month: {end_of_the_month}"
    )

    execute_parameters_correction(UNITS_TO_UPGRADE, start_date, today, end_of_the_month)


def safe_update_cashia_parameters():
    try:
        print("\nRunning udpate_cashia_parameters()...")
        udpate_cashia_parameters()
        print("Update finished successfully.")
    except Exception as e:
        print("Error while running udpate_cashia_parameters()")
        print(f"Error type: {type(e).__name__}")
        print(f"Error message: {e}")
        traceback.print_exc()

"""
===============================================================================
                                   MAIN PROGRAM                                                        
===============================================================================
"""

def main():
    art_text = text2art("MDC V0.7")
    print(art_text)

    # Ejecución inicial protegida
    safe_update_cashia_parameters()

    # Programación protegida
    schedule.every().day.at("01:00").do(safe_update_cashia_parameters)
    schedule.every().day.at("13:00").do(safe_update_cashia_parameters)

    while True:
        try:
            schedule.run_pending()
            print(".", end="", flush=True)
            time.sleep(10 * 60)
        except Exception as e:
            print("\nUnexpected error in main loop")
            print(f"Error type: {type(e).__name__}")
            print(f"Error message: {e}")
            traceback.print_exc()
            time.sleep(60)


if __name__ == "__main__":
    main()

