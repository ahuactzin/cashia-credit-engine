import pandas as pd
import numpy as np
from typing import List, Dict, Tuple

from cashia_credit_engine.config import *

def find_closest_date(unit_stats, real_amount, today):
    """
    Encuentra la fecha en la que el valor de 'Cupo Acumulado Requerido'  está más cercano a real_amount.
    Calcula los días de diferencia respecto a today y si la fecha más cercana es el final del mes Promocash.

    Args:
        unit_stats (DataFrame): DataFrame con los datos de la unidad como 'Cupo Acumulado Requerido' y 'Fecha'.
        real_amount (float): El monto real acumulado que debería tener la unidad.
        today (datetime.date): La fecha actual.

    Returns:
        tuple: (fecha más cercana, diferencia en días, is_end_of_month)
    """
    # Calcula la diferencia absoluta entre real_amount y 'Cupo Acumulado Requerido'
    unit_stats['Diferencia'] = np.abs(unit_stats['Cupo Acumulado Requerido'] - real_amount)
    
    # Encuentra el índice de la fila con la diferencia mínima
    closest_idx = unit_stats['Diferencia'].idxmin()
    
    # Obtén la fecha más cercana
    closest_date = unit_stats.loc[closest_idx, 'Fecha']
    
    # Calcula la diferencia de días respecto a today
    days_difference = (closest_date - today).days
    
    # Determina si es la última fila del DataFrame
    is_end_of_month = closest_idx == len(unit_stats) - 1
    
    return closest_date, days_difference, is_end_of_month


def get_applications_status(applications:pd.DataFrame, ponderation_stats:pd.DataFrame):
    # Recuperamos únicamente los créditos otorgados por Cashia (Los que no fueron otorgados por cashia están marcados en modelo como "Manual")
    models_applications = applications[applications["Modelo"].isin(MODELS_LIST)]
    
    status = {}

    # Si ya hay estadísticas previas de cambios de ponderacion
    if not ponderation_stats.empty:

        status["nv_previous_amount_error"] = ponderation_stats.loc[ponderation_stats['Date'].idxmax(), 'NV_error']
        status["rnv_previous_amount_error"] = ponderation_stats.loc[ponderation_stats['Date'].idxmax(), 'RNV_error']
        status["previous_amount_error"] = ponderation_stats.loc[ponderation_stats['Date'].idxmax(), 'Error']

        status["last_update_date"] = ponderation_stats.loc[ponderation_stats['Date'].idxmax(), 'Date']
        # Recuperamos el id de la última demanda de crédito proesada
        last_processed_id = ponderation_stats.loc[ponderation_stats['Date'].idxmax(), "Last_id"]
        status["last_processed_id"] = last_processed_id
        # Obtenemos el indice del id de la última solicitud procesada
        index_of_last_processed_id = models_applications[models_applications["IdSolicitud"] == last_processed_id].index

        # Filtramos las solicitudes recibidas despues de la fecha de la última actualización
        try:
            status["new_models_applications"] = models_applications[models_applications.index > index_of_last_processed_id[0]]
        except:
            # Se entrará a la excepción si el último registro procesado se ha borrado de la 
            # base de datos, es decir es una solicitud cancelada
            print(f"\tPonderation Warning: IdSolicitid number {last_processed_id} not found in registers")
            print("\tUsing alternative selection for new registers")
            status["new_models_applications"] = models_applications[models_applications["IdSolicitud"] > last_processed_id]

    # Si no hay aún estadísticas de cambios de ponderación
    else:
        status["nv_previous_amount_error"] = 0
        status["rnv_previous_amount_error"] = 0
        status["previous_amount_error"] = 0
        status["last_update_date"] = None
        status["last_processed_id"]  = None
        status["new_models_applications"] = models_applications

    return status

def compute_demand_metrics(new_models_applications:pd.DataFrame, 
                           cashia_parameters:pd.DataFrame,
                           unit:str)->Tuple[List[float], List[int], Dict[str, Dict]]:
    """Para la lista de modelos, calcula el montos promedio y numero de demandas (para cada modelo), 
    al mismo tiempo, crea un diccionario con los parámetros actuales de cada modelo.

    Args:
        new_models_applications (pd.DataFrame): lista de nuevas demandas
        cashia_parameters (pd.DataFrame): parametros de Cashia para cada modelo
        unit (str): Unidad

    Returns:
        Tuple[List[float], List[int], Dict[str, Dict]]: - lista de montos promedio
                                                        - lista de numero de demandas
                                                        - parámetros de Cashia para cada modelo
    """    

    average_amounts_list = []
    number_of_demands_list = []
    parameters_dic = {}

    # Obtenemos los promedios por modelo y recuperamos los parámetros del modelo
    for model in MODELS_LIST:
        # Recuperamos todas las solicitudes al modelo
        models_applications = new_models_applications[new_models_applications['Modelo'] == model]
        if not models_applications.empty:
            average_amount = models_applications["Monto"].mean()
            number_of_demands = len(models_applications)
        else:
            average_amount = 0
            number_of_demands = 0

        average_amounts_list.append(average_amount)
        number_of_demands_list.append(number_of_demands)
        # print(f"\n\t{model}: {number_of_demands}")

        # Filtrar para obtener los datos del modelo
        filtered_row = cashia_parameters.loc[(cashia_parameters['unit'] == unit) & 
                                            (cashia_parameters['model'] == model)]

        # Extraer los valores y agregarlos a las listas

        parameters = {'ponderation':filtered_row['ponderation'].iloc[0], 
                      'threshold':filtered_row['threshold'].iloc[0],
                      'base amount':filtered_row['base_amount'].iloc[0],
                      'max amount':filtered_row['max_amount'].iloc[0],
                      'average amount':average_amount}
        
        parameters_dic[model] = parameters

    return average_amounts_list, number_of_demands_list, parameters_dic



def fill_models_update_data(unit, models_update, parameters_dic, new_ponderations, new_cashia_parameters):
    
    # Llenar los datos de la actualización que será registrado (models_update) y 
    # los nuevos parámetros (new_cashia_parameters)
    for model in MODELS_LIST:
        models_update["Previous_ponderation_"+model] = parameters_dic[model]["ponderation"]
        if model in new_ponderations:
            # Agregamos la nueva poderación en el dataframe de parámetros de chashia
            new_cashia_parameters.loc[(new_cashia_parameters['unit'] == unit) & 
                                    (new_cashia_parameters['model'] == model),
                                    'ponderation'] = new_ponderations[model]
            
            # Agregamos la ponderación actual con el nuevo valor
            models_update["Ponderation_"+model] = new_ponderations[model]
        else:
            models_update["Ponderation_"+model] = parameters_dic[model]["ponderation"]

    return models_update, new_cashia_parameters

    

class CumulatedAmountMetrics():
    """Extrae las metricas del monto acumulado real y requerido de una unidad a partir del data frame que contiene la información
    """
    def __init__(self, stats:pd.DataFrame, unit:str):

        self.real_amount = stats.loc[stats['Unidad']==unit, 'Monto Acumulado Real'].iloc[0]
        self.required_amount = stats.loc[stats['Unidad']==unit, 'Cupo Acumulado Requerido'].iloc[0]
        self.amount_error = stats.loc[stats['Unidad']==unit, 'Error en monto'].iloc[0]
        self.percentage_amount_error = stats.loc[stats['Unidad']==unit, 'Porcentaje'].iloc[0]
