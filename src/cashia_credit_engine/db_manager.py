"""
Author: Juan Manuel Ahuactzin Larios
Date Created: 20/12/2024
File Name: db_manager.py

Database manager for MDC.

Supports SQLite and MySQL, selected through environment variables.
When MySQL is selected and the server is temporarily unavailable, write
operations are queued in a CSV resource and synchronized automatically the
next time a database read or write is requested and MySQL is available.
"""

import os
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime

import pandas as pd

from cashia_credit_engine.config import *
from cashia_core.common_tools.storage import get_storage


THRESHOLD_CHANGE = 1
PONDERATION_CHANGE = 2

SUPPORTED_DB_BACKENDS = {"sqlite", "mysql"}
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# MySQL client/network errors that mean the server cannot currently be reached
# or the connection was lost. Configuration/permission/data errors are NOT
# included, because those should be reported instead of silently queued.
MYSQL_CONNECTION_ERROR_CODES = {
    2002,  # Can't connect to local MySQL server
    2003,  # Can't connect to MySQL server on host
    2005,  # Unknown MySQL server host
    2006,  # MySQL server has gone away
    2013,  # Lost connection to MySQL server during query
    2055,  # Lost connection to MySQL server
}

COMMON_CHANGE_FIELDS = [
    "Date",
    "Time",
    "Month",
    "Year",
    "Last_id",
    "Unit",
    "Previous_error",
    "Error",
]

THRESHOLD_CHANGE_FIELDS = [
    "Date",
    "Time",
    "Month",
    "Year",
    "Last_id",
    "Unit",
    "Model",
    "Previous_error",
    "Error",
    "Previous_threshold",
    "Threshold",
]

PONDERATION_CHANGE_FIELDS = [
    "Date",
    "Time",
    "Month",
    "Year",
    "Last_id",
    "Unit",
    "Update_type",
    "Number_of_demands",
    "Avg_NV_amount",
    "Avg_NV_requested_amount",
    "NV_previous_error",
    "NV_error",
    "Avg_RNV_amount",
    "Avg_RNV_requested_amount",
    "RNV_previous_error",
    "RNV_error",
    "Avg_Amount",
    "Avg_Requested_Amount",
    "Previous_error",
    "Error",
    "Previous_ponderation_NV_Agt",
    "Ponderation_NV_Agt",
    "Previous_ponderation_NV_CC",
    "Ponderation_NV_CC",
    "Previous_ponderation_RNV_Agt",
    "Ponderation_RNV_Agt",
    "Previous_ponderation_RNV_CC",
    "Ponderation_RNV_CC",
]

PENDING_CHANGE_COLUMNS = [
    "Queue_id",
    "Queued_at",
    "Change_type",
    *dict.fromkeys(THRESHOLD_CHANGE_FIELDS + PONDERATION_CHANGE_FIELDS),
]

INTEGER_FIELDS = {
    "Month",
    "Year",
    "Last_id",
    "Number_of_demands",
}


class DatabaseUnavailableError(ConnectionError):
    """Raised when the configured MySQL server cannot currently be reached."""


# -----------------------------------------------------------------------------
# Configuration and connections
# -----------------------------------------------------------------------------

def _get_setting(name, default=None, required=False):
    """Read a setting from the environment or from config.py globals.

    Empty strings are considered valid values, which is important for an
    empty database password.
    """
    if name in os.environ:
        return os.environ[name]

    if name in globals() and globals()[name] is not None:
        return globals()[name]

    if required:
        raise RuntimeError(
            f"Missing required database configuration: {name}"
        )

    return default


def get_cce_db_backend():
    """Return the selected database backend: 'sqlite' or 'mysql'."""
    backend = str(
        _get_setting(
            "CCE_DB_BACKEND",
            default="sqlite",
        )
    ).strip().lower()

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

    port = _get_setting("CCE_DB_PORT", default=3306)

    try:
        port = int(port)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "CCE_DB_PORT must be an integer"
        ) from exc

    return {
        "host": _get_setting(
            "CCE_DB_HOST",
            required=True,
        ),
        "database": _get_setting(
            "CCE_DB_NAME",
            required=True,
        ),
        "user": _get_setting(
            "CCE_DB_USER",
            required=True,
        ),
        "password": _get_setting(
            "CCE_DB_PASSWORD",
            default="",
        ),
        "port": port,
    }

def _open_cce_connection():
    """Open a raw connection without initializing the schema."""
    backend = get_cce_db_backend()

    if backend == "sqlite":
        return sqlite3.connect(get_cce_database_path())

    try:
        import mysql.connector
    except ImportError as exc:
        raise RuntimeError(
            "MySQL backend selected, but mysql-connector-python is not installed. "
            "Install it with: python -m pip install mysql-connector-python"
        ) from exc

    return mysql.connector.connect(**_get_mysql_connection_parameters())


def _is_mysql_connection_error(exc):
    """Return True only for temporary MySQL connectivity failures."""
    if get_cce_db_backend() != "mysql":
        return False

    errno = getattr(exc, "errno", None)
    if errno in MYSQL_CONNECTION_ERROR_CODES:
        return True

    # Some connector/network errors may wrap an OSError without exposing errno
    # in the outer exception. Walk the exception chain conservatively.
    cause = getattr(exc, "__cause__", None) or getattr(exc, "__context__", None)
    if cause is not None and cause is not exc:
        cause_errno = getattr(cause, "errno", None)
        if cause_errno in MYSQL_CONNECTION_ERROR_CODES:
            return True

    return False


def _raise_database_unavailable(exc):
    """Convert temporary MySQL connection errors to one controlled exception."""
    if _is_mysql_connection_error(exc):
        raise DatabaseUnavailableError("The database is not up.") from exc
    raise exc


def get_cce_connection():
    """Return a connection to the configured database backend.

    SQLite keeps the original behavior: its file/tables are ensured before a
    connection is returned.

    MySQL does NOT execute CREATE TABLE on every connection. The MySQL schema
    is expected to have been created during installation/import, and the
    application user therefore only needs normal data permissions.
    """
    if get_cce_db_backend() == "sqlite":
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


# -----------------------------------------------------------------------------
# Schema initialization
# -----------------------------------------------------------------------------


def ensure_cce_database():
    """Create the CCE tables when they do not already exist.

    For MySQL this function is intended for installation/administration only.
    Normal application connections do not call it automatically.
    """
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

    try:
        connection = _open_cce_connection()
    except Exception as exc:
        _raise_database_unavailable(exc)

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


# -----------------------------------------------------------------------------
# Pending MySQL write queue
# -----------------------------------------------------------------------------


def _get_pending_changes_file_key():
    """Return the resource key used for the pending MySQL changes CSV."""
    if "CCE_PENDING_DB_CHANGES_FILE_KEY" not in globals():
        raise RuntimeError(
            "CCE_PENDING_DB_CHANGES_FILE_KEY is not defined in config.py."
        )
    return CCE_PENDING_DB_CHANGES_FILE_KEY


def _empty_pending_changes_df():
    return pd.DataFrame(columns=PENDING_CHANGE_COLUMNS)


def _read_pending_changes():
    """Read queued MySQL changes from the storage resource."""
    storage = get_storage()
    file_key = _get_pending_changes_file_key()

    if not storage.exists(file_key):
        return _empty_pending_changes_df()

    pending_df = storage.read_csv(file_key)

    # Keep the expected columns/order even if an old/empty queue file is read.
    for column in PENDING_CHANGE_COLUMNS:
        if column not in pending_df.columns:
            pending_df[column] = None

    return pending_df[PENDING_CHANGE_COLUMNS]


def _write_pending_changes(pending_df):
    """Write the complete pending queue back to storage."""
    storage = get_storage()
    storage.write_csv(
        _get_pending_changes_file_key(),
        pending_df[PENDING_CHANGE_COLUMNS],
        index=False,
    )


def _clear_pending_changes():
    """Leave an empty CSV with headers instead of requiring a delete API."""
    _write_pending_changes(_empty_pending_changes_df())


def _serialize_pending_value(value):
    """Convert common date/time objects to stable CSV values."""
    if value is None:
        return None

    if isinstance(value, pd.Timestamp):
        return value.isoformat(sep=" ")

    if isinstance(value, datetime):
        return value.isoformat(sep=" ")

    # datetime.date and datetime.time both provide isoformat(). Avoid applying
    # it to arbitrary objects that happen to define a method with that name.
    module_name = type(value).__module__
    if module_name == "datetime" and hasattr(value, "isoformat"):
        return value.isoformat()

    return value


def _append_pending_change(update, update_type):
    """Append one database change to the local/resource CSV queue."""
    pending_df = _read_pending_changes()

    record = {column: None for column in PENDING_CHANGE_COLUMNS}
    record["Queue_id"] = str(uuid.uuid4())
    record["Queued_at"] = datetime.now().isoformat(timespec="seconds")
    record["Change_type"] = update_type

    fields = (
        THRESHOLD_CHANGE_FIELDS
        if update_type == THRESHOLD_CHANGE
        else PONDERATION_CHANGE_FIELDS
    )

    for field in fields:
        record[field] = _serialize_pending_value(update[field])

    pending_df = pd.concat(
        [pending_df, pd.DataFrame([record], columns=PENDING_CHANGE_COLUMNS)],
        ignore_index=True,
    )

    _write_pending_changes(pending_df)


def _clean_pending_value(field, value):
    """Convert a value read from CSV back to a database-friendly value."""
    if pd.isna(value):
        return None

    if field in INTEGER_FIELDS:
        return int(float(value))

    return value


def _pending_row_to_update(row, update_type):
    fields = (
        THRESHOLD_CHANGE_FIELDS
        if update_type == THRESHOLD_CHANGE
        else PONDERATION_CHANGE_FIELDS
    )

    return {
        field: _clean_pending_value(field, row[field])
        for field in fields
    }


def _synchronize_pending_changes(connection):
    """Write all queued changes to MySQL before the requested operation.

    The queue is only cleared after every pending row has been inserted and the
    MySQL transaction has committed successfully. If insertion/commit fails,
    the queue remains unchanged so it can be retried later.
    """
    if get_cce_db_backend() != "mysql":
        return 0

    pending_df = _read_pending_changes()
    if pending_df.empty:
        return 0

    cursor = connection.cursor()

    try:
        for _, row in pending_df.iterrows():
            update_type = int(row["Change_type"])

            if update_type not in [THRESHOLD_CHANGE, PONDERATION_CHANGE]:
                raise ValueError(
                    f"Invalid pending Change_type: {row['Change_type']!r}"
                )

            update = _pending_row_to_update(row, update_type)
            _execute_insert(cursor, update, update_type)

        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()

    _clear_pending_changes()

    number_of_changes = len(pending_df)
    print(f"Synchronized {number_of_changes} pending database change(s).")
    return number_of_changes


# -----------------------------------------------------------------------------
# Database CRUD
# -----------------------------------------------------------------------------


def _execute_insert(cursor, update, update_type):
    """Execute one INSERT using an already-open cursor. Does not commit."""
    marker = _parameter_marker()

    if update_type == THRESHOLD_CHANGE:
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
            tuple(update[field] for field in THRESHOLD_CHANGE_FIELDS),
        )

    else:
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
            tuple(update[field] for field in PONDERATION_CHANGE_FIELDS),
        )


def insert_into_cce_database(update, update_type=THRESHOLD_CHANGE):
    """Insert one change into SQLite/MySQL.

    With MySQL, pending queued changes are synchronized first. If MySQL cannot
    be reached, the new change is appended to the pending CSV and the function
    returns True because the write request has been safely accepted locally.

    SQL/data/permission errors are intentionally NOT queued: they are raised so
    a configuration or data problem cannot be mistaken for a temporary outage.
    """
    if update_type not in [THRESHOLD_CHANGE, PONDERATION_CHANGE]:
        print(f"Invalid option: {update_type} to update database")
        return False

    backend = get_cce_db_backend()

    if backend == "sqlite":
        with cce_connection() as connection:
            cursor = connection.cursor()
            try:
                _execute_insert(cursor, update, update_type)
            finally:
                cursor.close()
        return True

    connection = None

    try:
        connection = get_cce_connection()

        # Requirement: before a new write, replay any changes accumulated while
        # MySQL was unavailable.
        _synchronize_pending_changes(connection)

        cursor = connection.cursor()
        try:
            _execute_insert(cursor, update, update_type)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()

        return True

    except Exception as exc:
        if _is_mysql_connection_error(exc):
            _append_pending_change(update, update_type)
            print(
                "The MySQL database is not up. "
                "The change was saved locally and will be synchronized later."
            )
            return True

        raise

    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass


def read_from_data_base(table_name):
    """Read a database table into a pandas DataFrame.

    With MySQL, queued writes are synchronized before executing the SELECT.
    If MySQL is still unavailable, a controlled DatabaseUnavailableError is
    raised because there is no authoritative database from which to read.
    """
    table_name = _validate_identifier(table_name)
    connection = None

    try:
        connection = get_cce_connection()

        if get_cce_db_backend() == "mysql":
            _synchronize_pending_changes(connection)

        cursor = connection.cursor()

        try:
            cursor.execute(f"SELECT * FROM {table_name}")
            rows = cursor.fetchall()
            columns = [column[0] for column in cursor.description]
        finally:
            cursor.close()

    except Exception as exc:
        _raise_database_unavailable(exc)

    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass

    df = pd.DataFrame(rows, columns=columns)

    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"])

    return df


def empty_data_base():
    """Delete all rows from the two statistics tables.

    A successful reset also clears locally queued writes. Otherwise old queued
    changes could be reinserted after the intentional reset.
    """
    threshold_table = _validate_identifier(CCE_THRESHOLD_STATS_TABLE)
    ponderation_table = _validate_identifier(CCE_PONDERATION_STATS_TABLE)
    connection = None

    try:
        connection = get_cce_connection()
        cursor = connection.cursor()

        try:
            cursor.execute(f"DELETE FROM {threshold_table};")
            cursor.execute(f"DELETE FROM {ponderation_table};")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()

        if get_cce_db_backend() == "mysql":
            _clear_pending_changes()

    except Exception as exc:
        _raise_database_unavailable(exc)

    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass


# -----------------------------------------------------------------------------
# Main program
# -----------------------------------------------------------------------------


def main():
    storage = get_storage()

    print(f"Database backend: {get_cce_db_backend()}")
    print("What do you want to do?")
    print("\t1.- Generate the database.")
    print("\t2.- Write the database into an excel file.")
    print("\t3.- Restart the database.")

    option = int(input("OPTION: "))

    try:
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

    except DatabaseUnavailableError:
        print("The database is not up.")


if __name__ == "__main__":
    main()
