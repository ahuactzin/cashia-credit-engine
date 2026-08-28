"""
Author: Juan Manuel Ahuactzin Larios
Date Created: 20/12/2024
File Name: db_manager.py

Database manager for the CashIA Credit Engine.
Supports SQLite and MySQL, selected through environment variables.
"""

import os
import re
import sqlite3
from contextlib import contextmanager

import pandas as pd

from cashia_credit_engine.config import *
from cashia_core.common_tools.storage import get_storage


THRESHOLD_CHANGE = 1
PONDERATION_CHANGE = 2

SUPPORTED_DB_BACKENDS = {"sqlite", "mysql"}
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _get_setting(*names, default=None, required=False):
    """Read a setting from the environment or from config.py globals.

    The CCE_* name is preferred. CEE_* is accepted as a compatibility alias
    in case those names are already being used in the current .env file.
    Empty strings are considered valid values (important for empty passwords).
    """
    for name in names:
        if name in os.environ:
            return os.environ[name]

        if name in globals() and globals()[name] is not None:
            return globals()[name]

    if required:
        raise RuntimeError(
            "Missing required database configuration. Expected one of: "
            + ", ".join(names)
        )

    return default


def get_cce_db_backend():
    """Return the selected database backend: 'sqlite' or 'mysql'."""
    backend = str(
        _get_setting(
            "CCE_DB_BACKEND",
            "CEE_DB_BACKEND",
            default="sqlite",
        )
    ).strip().lower()

    # Accept sqlite3 as a friendly alias, but normalize internally to sqlite.
    if backend == "sqlite3":
        backend = "sqlite"

    if backend not in SUPPORTED_DB_BACKENDS:
        raise ValueError(
            f"Invalid database backend '{backend}'. "
            "Use CCE_DB_BACKEND=sqlite or CCE_DB_BACKEND=mysql."
        )

    return backend


def get_cce_database_path():
    """Return the SQLite database path, creating its directory if needed."""
    CCE_DATABASE_DIR.mkdir(parents=True, exist_ok=True)
    return CCE_DATABASE_PATH


def _get_mysql_connection_parameters():
    """Build the MySQL Connector/Python connection arguments."""
    port = _get_setting("CCE_DB_PORT", "CEE_DB_PORT", default=3306)

    try:
        port = int(port)
    except (TypeError, ValueError) as exc:
        raise ValueError("CCE_DB_PORT/CEE_DB_PORT must be an integer") from exc

    return {
        "host": _get_setting("CCE_DB_HOST", "CEE_DB_HOST", required=True),
        "database": _get_setting("CCE_DB_NAME", "CEE_DB_NAME", required=True),
        "user": _get_setting("CCE_DB_USER", "CEE_DB_USER", required=True),
        "password": _get_setting(
            "CCE_DB_PASSWORD",
            "CEE_DB_PASSWORD",
            default="",
        ),
        "port": port,
    }


def _open_cce_connection():
    """Open a raw connection without trying to initialize the schema."""
    backend = get_cce_db_backend()

    if backend == "sqlite":
        return sqlite3.connect(get_cce_database_path())

    # Import only when MySQL is selected, so SQLite installations do not
    # require mysql-connector-python just to run the application.
    try:
        import mysql.connector
    except ImportError as exc:
        raise RuntimeError(
            "MySQL backend selected, but mysql-connector-python is not installed. "
            "Install it with: python -m pip install mysql-connector-python"
        ) from exc

    return mysql.connector.connect(**_get_mysql_connection_parameters())


def get_cce_connection():
    """Return a connection to the configured database backend.

    Kept with the same public name as the original implementation so callers
    do not need to change. The caller is responsible for closing the returned
    connection.
    """
    ensure_cce_database()
    return _open_cce_connection()


@contextmanager
def cce_connection():
    """Context manager with portable commit/rollback/close behavior."""
    connection = get_cce_connection()

    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _sql_real_type():
    """Return the floating-point SQL type used by the selected backend."""
    return "DOUBLE" if get_cce_db_backend() == "mysql" else "REAL"


def _parameter_marker():
    """Return the DB-API parameter marker for the selected backend."""
    return "%s" if get_cce_db_backend() == "mysql" else "?"


def _validate_identifier(identifier):
    """Validate table identifiers before interpolating them into SQL."""
    if not isinstance(identifier, str) or not _IDENTIFIER_RE.fullmatch(identifier):
        raise ValueError(f"Invalid SQL identifier: {identifier!r}")
    return identifier


def ensure_cce_database():
    """Create the CCE tables when they do not already exist."""
    real_type = _sql_real_type()
    threshold_table = _validate_identifier(CCE_THRESHOLD_STATS_TABLE)
    ponderation_table = _validate_identifier(CCE_PONDERATION_STATS_TABLE)

    create_threshold_table_query = f"""
    CREATE TABLE IF NOT EXISTS {threshold_table} (
        Date DATE NOT NULL,
        Time TIME NOT NULL,
        Month INTEGER NOT NULL,
        Year INTEGER NOT NULL,
        Last_id INTEGER NOT NULL,
        Unit VARCHAR(30),
        Model VARCHAR(20) NOT NULL,
        Previous_error {real_type} NOT NULL,
        Error {real_type} NOT NULL,
        Previous_threshold {real_type} NOT NULL,
        Threshold {real_type} NOT NULL
    );
    """

    create_ponderation_table_query = f"""
    CREATE TABLE IF NOT EXISTS {ponderation_table} (
        Date DATE NOT NULL,
        Time TIME NOT NULL,
        Month INTEGER NOT NULL,
        Year INTEGER NOT NULL,
        Last_id INTEGER NOT NULL,
        Unit VARCHAR(30),
        Update_type VARCHAR(30),
        Number_of_demands INTEGER NOT NULL,
        Avg_NV_amount {real_type} NOT NULL,
        Avg_NV_requested_amount {real_type} NOT NULL,
        NV_previous_error {real_type} NOT NULL,
        NV_error {real_type} NOT NULL,
        Avg_RNV_amount {real_type} NOT NULL,
        Avg_RNV_requested_amount {real_type} NOT NULL,
        RNV_previous_error {real_type} NOT NULL,
        RNV_error {real_type} NOT NULL,
        Avg_Amount {real_type} NOT NULL,
        Avg_Requested_Amount {real_type} NOT NULL,
        Previous_error {real_type} NOT NULL,
        Error {real_type} NOT NULL,
        Previous_ponderation_NV_Agt {real_type} NOT NULL,
        Ponderation_NV_Agt {real_type} NOT NULL,
        Previous_ponderation_NV_CC {real_type} NOT NULL,
        Ponderation_NV_CC {real_type} NOT NULL,
        Previous_ponderation_RNV_Agt {real_type} NOT NULL,
        Ponderation_RNV_Agt {real_type} NOT NULL,
        Previous_ponderation_RNV_CC {real_type} NOT NULL,
        Ponderation_RNV_CC {real_type} NOT NULL
    );
    """

    connection = _open_cce_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(create_threshold_table_query)
        cursor.execute(create_ponderation_table_query)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()


def create_cce_database():
    """Initialize the configured CCE database and its tables."""
    ensure_cce_database()

    if get_cce_db_backend() == "sqlite":
        print("SQLite database initialized:", get_cce_database_path())
    else:
        mysql_config = _get_mysql_connection_parameters()
        print(
            "MySQL database initialized: "
            f"{mysql_config['host']}:{mysql_config['port']}/"
            f"{mysql_config['database']}"
        )


def insert_into_cce_database(update, update_type=THRESHOLD_CHANGE):
    if update_type not in [THRESHOLD_CHANGE, PONDERATION_CHANGE]:
        print(f"Invalid option: {update_type} to update database")
        return False

    date = update["Date"]
    time_of_update = update["Time"]
    month = update["Month"]
    year = update["Year"]
    last_id = update["Last_id"]
    unit = update["Unit"]
    previous_error = update["Previous_error"]
    error = update["Error"]

    marker = _parameter_marker()

    with cce_connection() as conn:
        cursor = conn.cursor()

        try:
            if update_type == THRESHOLD_CHANGE:
                model = update["Model"]
                previous_threshold = update["Previous_threshold"]
                threshold = update["Threshold"]

                values = ", ".join([marker] * 11)

                cursor.execute(
                    f"""
                    INSERT INTO {_validate_identifier(CCE_THRESHOLD_STATS_TABLE)}
                    (
                        Date, Time, Month, Year, Last_id, Unit, Model,
                        Previous_error, Error, Previous_threshold, Threshold
                    )
                    VALUES ({values})
                    """,
                    (
                        date,
                        time_of_update,
                        month,
                        year,
                        last_id,
                        unit,
                        model,
                        previous_error,
                        error,
                        previous_threshold,
                        threshold,
                    ),
                )

            else:
                update_type_value = update["Update_type"]
                number_of_demands = update["Number_of_demands"]

                avg_NV_amount = update["Avg_NV_amount"]
                avg_NV_requested_amount = update["Avg_NV_requested_amount"]
                NV_previous_error = update["NV_previous_error"]
                NV_error = update["NV_error"]

                avg_RNV_amount = update["Avg_RNV_amount"]
                avg_RNV_requested_amount = update["Avg_RNV_requested_amount"]
                RNV_previous_error = update["RNV_previous_error"]
                RNV_error = update["RNV_error"]

                avg_Amount = update["Avg_Amount"]
                avg_Requested_Amount = update["Avg_Requested_Amount"]

                previous_ponderation_NV_Agt = update["Previous_ponderation_NV_Agt"]
                ponderation_NV_Agt = update["Ponderation_NV_Agt"]

                previous_ponderation_NV_CC = update["Previous_ponderation_NV_CC"]
                ponderation_NV_CC = update["Ponderation_NV_CC"]

                previous_ponderation_RNV_Agt = update["Previous_ponderation_RNV_Agt"]
                ponderation_RNV_Agt = update["Ponderation_RNV_Agt"]

                previous_ponderation_RNV_CC = update["Previous_ponderation_RNV_CC"]
                ponderation_RNV_CC = update["Ponderation_RNV_CC"]

                values = ", ".join([marker] * 28)

                cursor.execute(
                    f"""
                    INSERT INTO {_validate_identifier(CCE_PONDERATION_STATS_TABLE)}
                    (
                        Date, Time, Month, Year, Last_id, Unit, Update_type,
                        Number_of_demands, Avg_NV_amount, Avg_NV_requested_amount,
                        NV_previous_error, NV_error,
                        Avg_RNV_amount, Avg_RNV_requested_amount,
                        RNV_previous_error, RNV_error,
                        Avg_Amount, Avg_Requested_Amount,
                        Previous_error, Error,
                        Previous_ponderation_NV_Agt, Ponderation_NV_Agt,
                        Previous_ponderation_NV_CC, Ponderation_NV_CC,
                        Previous_ponderation_RNV_Agt, Ponderation_RNV_Agt,
                        Previous_ponderation_RNV_CC, Ponderation_RNV_CC
                    )
                    VALUES ({values})
                    """,
                    (
                        date,
                        time_of_update,
                        month,
                        year,
                        last_id,
                        unit,
                        update_type_value,
                        number_of_demands,
                        avg_NV_amount,
                        avg_NV_requested_amount,
                        NV_previous_error,
                        NV_error,
                        avg_RNV_amount,
                        avg_RNV_requested_amount,
                        RNV_previous_error,
                        RNV_error,
                        avg_Amount,
                        avg_Requested_Amount,
                        previous_error,
                        error,
                        previous_ponderation_NV_Agt,
                        ponderation_NV_Agt,
                        previous_ponderation_NV_CC,
                        ponderation_NV_CC,
                        previous_ponderation_RNV_Agt,
                        ponderation_RNV_Agt,
                        previous_ponderation_RNV_CC,
                        ponderation_RNV_CC,
                    ),
                )
        finally:
            cursor.close()

    return True


def read_from_data_base(table_name):
    """Read a database table into a pandas DataFrame for either backend."""
    table_name = _validate_identifier(table_name)

    with cce_connection() as conn:
        cursor = conn.cursor()

        try:
            cursor.execute(f"SELECT * FROM {table_name}")
            rows = cursor.fetchall()
            columns = [column[0] for column in cursor.description]
        finally:
            cursor.close()

    df = pd.DataFrame(rows, columns=columns)

    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"])

    return df


def empty_data_base():
    """Delete all rows from the two CCE statistics tables."""
    threshold_table = _validate_identifier(CCE_THRESHOLD_STATS_TABLE)
    ponderation_table = _validate_identifier(CCE_PONDERATION_STATS_TABLE)

    with cce_connection() as connection:
        cursor = connection.cursor()

        try:
            cursor.execute(f"DELETE FROM {threshold_table};")
            cursor.execute(f"DELETE FROM {ponderation_table};")
        finally:
            cursor.close()


"""
===============================================================================
                                   MAIN PROGRAM
===============================================================================
"""


def main():
    storage = get_storage()

    print(f"Database backend: {get_cce_db_backend()}")
    print("What do you want to do?")
    print("\t1.- Generate the database.")
    print("\t2.- Write the database into an excel file.")
    print("\t3.- Restart the database.")

    option = int(input("OPTION: "))

    if option == 1:
        create_cce_database()

    elif option == 2:
        stats_df = read_from_data_base(CCE_THRESHOLD_STATS_TABLE)

        storage.write_excel(
            THRESHOLD_DATABASE_FILE_KEY,
            stats_df,
            index=False,
        )

        print(f"Database written at: {THRESHOLD_DATABASE_FILE_KEY}")

        stats_df = read_from_data_base(CCE_PONDERATION_STATS_TABLE)

        storage.write_excel(
            PONDERATION_DATABASE_FILE_KEY,
            stats_df,
            index=False,
        )

        print(f"Database written at: {PONDERATION_DATABASE_FILE_KEY}")

    elif option == 3:
        response = input("Are you sure Y/N: ").strip().upper()

        if response == "Y":
            empty_data_base()
            print("Database is empty")


if __name__ == "__main__":
    main()
