from cashia_core.common_tools.configuration.cashiaconstants import *
from pathlib import Path
import tempfile

HOST = "promok.mx"  # Host
DATABASE = "promokmx_promocashprod"  # Nombre de la base de datos
USER = "promokmx_consultas"  # Usuario de la base de datos
PASSWORD = "pr.24QPC#"  # Contraseña del usuario

PROMOK_TABLE_COLUMNS = [
    "IdSolicitud",
    "Producto",
    "Plazo",
    "Categoria",
    "Unidad",
    "Zona",
    "Agencia",
    "Fecha",
    "CP",
    "Monto",
    "Score",
    "Score_CC",
    "Score_agt",
    "Dictamen",
    "Modelo",
    "monto_cliente",
    "monto_max_cashia",
    "monto_agente",
]

PROCEDURE_NAME = "sp_sol_unidad"

# Unidades que serán monitoreadas y actualizadas por el CCE
UNITS_TO_UPGRADE = [
    BOCA_DEL_RIO,
    CORDOBA,
    CUAUTLA,
    OAXACA,
    ORIZABA,
    PACHUCA,
    PUEBLA_NORTE,
    PUEBLA_ORIENTE,
    PUEBLA_PONIENTE
]

# Modelos agrupados
NEW_CREDITS_MODELS = [NV_AGT, NV_CC]
RENEWAL_CREDITS_MODELS = [RNV_AGT, RNV_CC]

OPINIONS_LIST = ["AC", "AM", "RC", "RM"]

AMOUNT_SELECTION_COLUMNS = ["sel_cashia", "sel_agente", "sel_cliente"]

# Constantes de tipo de ponderación
CUMULATIVE_AMOUNT = "Cumulative amount"
AVERAGE_TICKET = "Average Tiket"

# Poner en minutos cada que tiempo queremos que el CCE realize actualizaciones
cce_time_frecuency = 60 * 3

# Valores máximos y mímimos para la ponderación
MIN_ALLOWED_PONDERATION = 1

# Lista de todos los modelos
# MODELS_LIST = [NV_AGT, NV_CC, RNV_AGT, RNV_CC]

# Basados en una población promedio de 665 creditos mensuales con un margen de error de 10%
# y un nivel de comfianza del 95% tenemos que para las actualizaciones se requieres
# 84 muestras
MIN_SAMPLES_TO_UPDATE_PONDERATION = {
    BOCA_DEL_RIO: 20,
    CORDOBA: 44,
    CUAUTLA: 39,
    OAXACA: 36,
    ORIZABA: 44,
    PACHUCA: 20,
    PUEBLA_NORTE: 42,
    PUEBLA_ORIENTE: 42,
    PUEBLA_PONIENTE: 41,
}

MIN_MODEL_SAMPLES_TO_UPDATE_THRESHOLD = {
    BOCA_DEL_RIO: {NV_AGT: 10, NV_CC: 10, RNV_AGT: 10, RNV_CC: 10},
    CORDOBA: {NV_AGT: 10, NV_CC: 10, RNV_AGT: 10, RNV_CC: 10},
    CUAUTLA: {NV_AGT: 10, NV_CC: 10, RNV_AGT: 10, RNV_CC: 10},
    OAXACA: {NV_AGT: 10, NV_CC: 10, RNV_AGT: 10, RNV_CC: 10},
    ORIZABA: {NV_AGT: 10, NV_CC: 10, RNV_AGT: 10, RNV_CC: 10},
    PACHUCA: {NV_AGT: 10, NV_CC: 10, RNV_AGT: 10, RNV_CC: 10},
    PUEBLA_NORTE: {NV_AGT: 10, NV_CC: 10, RNV_AGT: 10, RNV_CC: 10},
    PUEBLA_ORIENTE: {NV_AGT: 10, NV_CC: 10, RNV_AGT: 10, RNV_CC: 10},
    PUEBLA_PONIENTE: {NV_AGT: 10, NV_CC: 10, RNV_AGT: 10, RNV_CC: 10},
}

MIN_ALLOWED_THRESHOLD = {
    BOCA_DEL_RIO: {NV_AGT: 0.20, NV_CC: 0.20, RNV_AGT: 0.20, RNV_CC: 0.20},
    CORDOBA: {NV_AGT: 0.20, NV_CC: 0.28, RNV_AGT: 0.24, RNV_CC: 0.28},
    CUAUTLA: {NV_AGT: 0.29, NV_CC: 0.20, RNV_AGT: 0.25, RNV_CC: 0.23},
    OAXACA: {NV_AGT: 0.34, NV_CC: 0.20, RNV_AGT: 0.31, RNV_CC: 0.23},
    ORIZABA: {NV_AGT: 0.38, NV_CC: 0.20, RNV_AGT: 0.24, RNV_CC: 0.23},
    PACHUCA: {NV_AGT: 0.20, NV_CC: 0.20, RNV_AGT: 0.20, RNV_CC: 0.20},
    PUEBLA_NORTE: {NV_AGT: 0.20, NV_CC: 0.20, RNV_AGT: 0.23, RNV_CC: 0.23},
    PUEBLA_ORIENTE: {NV_AGT: 0.23, NV_CC: 0.20, RNV_AGT: 0.23, RNV_CC: 0.23},
    PUEBLA_PONIENTE: {NV_AGT: 0.21, NV_CC: 0.20, RNV_AGT: 0.22, RNV_CC: 0.23},
}

MAX_ALLOWED_THRESHOLD = {
   BOCA_DEL_RIO: {NV_AGT: 0.99, NV_CC: 0.99, RNV_AGT: 0.99, RNV_CC: 0.99},
    CORDOBA: {NV_AGT: 0.99, NV_CC: 0.99, RNV_AGT: 0.99, RNV_CC: 0.99},
    CUAUTLA: {NV_AGT: 0.99, NV_CC: 0.99, RNV_AGT: 0.99, RNV_CC: 0.99},
    OAXACA: {NV_AGT: 0.99, NV_CC: 0.99, RNV_AGT: 0.99, RNV_CC: 0.99},
    ORIZABA: {NV_AGT: 0.99, NV_CC: 0.99, RNV_AGT: 0.99, RNV_CC: 0.99},
    PACHUCA: {NV_AGT: 0.99, NV_CC: 0.99, RNV_AGT: 0.99, RNV_CC: 0.99},
    PUEBLA_NORTE: {NV_AGT: 0.99, NV_CC: 0.99, RNV_AGT: 0.99, RNV_CC: 0.99},
    PUEBLA_ORIENTE: {NV_AGT: 0.99, NV_CC: 0.99, RNV_AGT: 0.99, RNV_CC: 0.99},
    PUEBLA_PONIENTE: {NV_AGT: 0.99, NV_CC: 0.99, RNV_AGT: 0.99, RNV_CC: 0.99},
}

# Número máximo de dias que podemos estar adelantados en el monto acumulado
MAX_DAYS_AHEAD = 2

# Tablas del cashia-credit-engine
CCE_THRESHOLD_STATS_TABLE = "stats_threshold_cce"
CCE_PONDERATION_STATS_TABLE = "stats_ponderation_cce"

# Base SQLite local del CCE
CCE_DATABASE_DIR = Path(tempfile.gettempdir()) / "cashia-credit-engine"
CCE_DATABASE_FILE = "cashia-credit-engine_db.db"
CCE_DATABASE_PATH = CCE_DATABASE_DIR / CCE_DATABASE_FILE

# Recursos lógicos que sí pueden vivir en storage local/S3
CCE_RESOURCE_KEYS = {
    "pk_calendar": "cashia-credit-engine/inputs/calendario_pk.xlsx",
    "risk": "cashia-credit-engine/config/config_risk.xlsx",
    "applications": "cashia-credit-engine/storage/applications.csv",
    "threshold_database_excel": "cashia-credit-engine/outputs/threshold_database.xlsx",
    "ponderation_database_excel": "cashia-credit-engine/outputs/ponderation_database.xlsx",
}


def get_cce_resource_key(name: str) -> str:
    try:
        return CCE_RESOURCE_KEYS[name]
    except KeyError as e:
        available = ", ".join(sorted(CCE_RESOURCE_KEYS.keys()))
        raise KeyError(
            f"Unknown cashia-credit-engine resource: '{name}'. Available: {available}"
        ) from e


PK_CALENDAR_FILE_KEY = get_cce_resource_key("pk_calendar")
RISK_FILE_KEY = get_cce_resource_key("risk")
APPLICATIONS_FILE_KEY = get_cce_resource_key("applications")
THRESHOLD_DATABASE_FILE_KEY = get_cce_resource_key("threshold_database_excel")
PONDERATION_DATABASE_FILE_KEY = get_cce_resource_key("ponderation_database_excel")


REPORT_COLUMNS = [
    "Unidad",
    "Fecha",
    "Monto",
    "Creditos",
    "Monto Acumulado Requerido",
    "Cupo Acumulado Requerido",
    "Monto Acumulado Real",
    "Creditos Acumulados",
    "Ticket Promedio",
    "AC",
    "AM",
    "RC",
    "RM",
    "Cum AC",
    "Cum AM",
    "Cum RC",
    "Cum RM",
    "%Aprobado por Cashia",
    "%Aprobado final Cashia",
    "%Aprobado Manual",
    "%Aprobado",
    "%Acum Aprobado Manual",
    "%Acum Aprobado",
    "sel_cashia",
    "sel_agente",
    "sel_cliente",
    "Cum sel_cashia",
    "Cum sel_agente",
    "Cum sel_cliente",
    # Solicitudes por modelo
    "NV_Agt",
    "NV_CC",
    "RNV_Agt",
    "RNV_CC",
    "Cashia Solicitudes",
    "Acumulado NV_Agt",
    "Acumulado NV_CC",
    "Acumulado RNV_Agt",
    "Acumulado RNV_CC",
    "Acumulado Nuevos",  # Nuevo
    "Acumulado Renovaciones",  # Nuevo
    "Cashia Solicitudes Acumuladas",
    "Solicitudes Acumuladas Requeridas",
    # Número de créditos por modelo y total
    "Creditos NV_Agt",
    "Creditos NV_CC",
    "Creditos RNV_Agt",
    "Creditos RNV_CC",
    "Cashia Creditos Nuevos",  # Nuevo
    "Cashia Creditos Renovaciones",  # Nuevo
    "Cashia Creditos",
    "Creditos Acumulados NV_Agt",
    "Creditos Acumulados NV_CC",
    "Creditos Acumulados RNV_Agt",
    "Creditos Acumulados RNV_CC",
    "Creditos Acumulados Nuevos",  # Nuevo
    "Creditos Acumulados Renovaciones",  # Nuevo
    "Cashia Creditos Acumulados",
    # Montos por modelo y total
    "Monto NV_Agt",
    "Monto NV_CC",
    "Monto RNV_Agt",
    "Monto RNV_CC",
    "Monto Nuevos",  # Nuevo
    "Monto Renovaciones",  # Nuevo
    "Cashia Monto",
    # Error en monto
    "Error en monto",
    "Porcentaje",
    # Monto acumulado por modelo y total
    "Monto Acumulado NV_Agt",
    "Monto Acumulado NV_CC",
    "Monto Acumulado RNV_Agt",
    "Monto Acumulado RNV_CC",
    "Monto Acumulado Nuevos",  # Nuevo
    "Monto Acumulado Renovaciones",  # Nuevo
    "Cashia Monto Acumulado",
    # Ticket promedio por modelo y total
    "Ticket Promedio NV_Agt",
    "Ticket Promedio NV_CC",
    "Ticket Promedio RNV_Agt",
    "Ticket Promedio RNV_CC",
    "Ticket Promedio Nuevos",  # Nuevo
    "Ticket Promedio Renovaciones",  # Nuevo
    "Cashia Ticket Promedio",
    "Cashia Ticket Promedio Requerido Nuevos",  # Nuevo
    "Cashia Ticket Promedio Requerido Renovaciones",  # Nuevo
    "Cashia Ticket Promedio Requerido",
    # Error en % de aprobación del día por modelo y total
    "Day Error %Aprobado NV_Agt",
    "Day Error %Aprobado NV_CC",
    "Day Error %Aprobado RNV_Agt",
    "Day Error %Aprobado RNV_CC",
    "Day Error %Aprobado",
    # Porcentaje acumulado de aceptación por modelo y total
    "%Acum Aprobado NV_Agt",
    "%Acum Aprobado NV_CC",
    "%Acum Aprobado RNV_Agt",
    "%Acum Aprobado RNV_CC",
    "%Acum Aprobado por Cashia",
    "%Acum Aprobado final Cashia",
    "Cashia %Aprobado Requerido",
    # Error en aprobación por modelo y total
    "Error %Aprobado NV_Agt",
    "Error %Aprobado NV_CC",
    "Error %Aprobado RNV_Agt",
    "Error %Aprobado RNV_CC",
    "Cashia Error %Aprobado",
    # Error en ticket por modelo y total
    "Error en Ticket NV_Agt",
    "Error en Ticket NV_CC",
    "Error en Ticket RNV_Agt",
    "Error en Ticket RNV_CC",
    "Error en Ticket Nuevos",  # Nuevo
    "Error en Ticket Renovaciones",  # Nuevo
    "Error en Ticket",
]
