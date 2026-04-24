"""
Author: Juan Manuel Ahuactzin Larios
Date Created: 20/12/2024
File Name: db_manager.py

Description: Insert description here.
"""

import sqlite3
import pandas as pd

from cashia_credit_engine.config import *
from cashia_core.common_tools.storage import get_storage


THRESHOLD_CHANGE = 1
PONDERATION_CHANGE = 2


def get_cce_database_path():
    CCE_DATABASE_DIR.mkdir(parents=True, exist_ok=True)
    return CCE_DATABASE_PATH

def get_cce_connection():
    ensure_cce_database()
    db_path = get_cce_database_path()
    return sqlite3.connect(db_path)


def ensure_cce_database():
    db_path = get_cce_database_path()

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()

        create_threshold_table_query = f"""
        CREATE TABLE IF NOT EXISTS {CCE_THRESHOLD_STATS_TABLE} (
            Date DATE NOT NULL,
            Time TIME NOT NULL,
            Month INTEGER NOT NULL,
            Year INTEGER NOT NULL,
            Last_id INTEGER NOT NULL,
            Unit VARCHAR(30),
            Model VARCHAR(20) NOT NULL,
            Previous_error NOT NULL,
            Error REAL NOT NULL,
            Previous_threshold REAL NOT NULL,
            Threshold REAL NOT NULL
        );
        """

        cursor.execute(create_threshold_table_query)

        create_ponderation_table_query = f"""
        CREATE TABLE IF NOT EXISTS {CCE_PONDERATION_STATS_TABLE} (
            Date DATE NOT NULL,
            Time TIME NOT NULL,
            Month INTEGER NOT NULL,
            Year INTEGER NOT NULL,
            Last_id INTEGER NOT NULL,
            Unit VARCHAR(30),
            Update_type VARCHAR(30),
            Number_of_demands INTEGER NOT NULL,
            Avg_NV_amount REAL NOT NULL,
            Avg_NV_requested_amount REAL NOT NULL,
            NV_previous_error REAL NOT NULL,
            NV_error REAL NOT NULL,
            Avg_RNV_amount REAL NOT NULL,
            Avg_RNV_requested_amount REAL NOT NULL,
            RNV_previous_error REAL NOT NULL,
            RNV_error REAL NOT NULL,
            Avg_Amount REAL NOT NULL,
            Avg_Requested_Amount REAL NOT NULL,
            Previous_error REAL NOT NULL,
            Error REAL NOT NULL,
            Previous_ponderation_NV_Agt REAL NOT NULL,
            Ponderation_NV_Agt REAL NOT NULL,
            Previous_ponderation_NV_CC REAL NOT NULL,
            Ponderation_NV_CC REAL NOT NULL,
            Previous_ponderation_RNV_Agt REAL NOT NULL,
            Ponderation_RNV_Agt REAL NOT NULL,
            Previous_ponderation_RNV_CC REAL NOT NULL,
            Ponderation_RNV_CC REAL NOT NULL
        );
        """

        cursor.execute(create_ponderation_table_query)

def create_cce_database():
    ensure_cce_database()
    print("Database initialized:", get_cce_database_path())


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

    with get_cce_connection() as conn:
        cursor = conn.cursor()

        if update_type == THRESHOLD_CHANGE:
            model = update["Model"]
            previous_threshold = update["Previous_threshold"]
            threshold = update["Threshold"]

            cursor.execute(
                f"""
                INSERT INTO {CCE_THRESHOLD_STATS_TABLE}
                (
                    Date, Time, Month, Year, Last_id, Unit, Model,
                    Previous_error, Error, Previous_threshold, Threshold
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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

            cursor.execute(
                f"""
                INSERT INTO {CCE_PONDERATION_STATS_TABLE}
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
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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

    return True


def read_from_data_base(table_name):
    with get_cce_connection() as conn:
        query = f"SELECT * FROM {table_name}"
        df = pd.read_sql_query(query, conn)

    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"])

    return df


def empty_data_base():
    with get_cce_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(f"DELETE FROM {CCE_THRESHOLD_STATS_TABLE};")
        cursor.execute(f"DELETE FROM {CCE_PONDERATION_STATS_TABLE};")

"""
===============================================================================
                                   MAIN PROGRAM                                                        
===============================================================================
"""

def main():

    storage = get_storage()

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
            index=False
        )

        print(f"Database written at: {THRESHOLD_DATABASE_FILE_KEY}")

        stats_df = read_from_data_base(CCE_PONDERATION_STATS_TABLE)

        storage.write_excel(
            PONDERATION_DATABASE_FILE_KEY,
            stats_df,
            index=False
        )

        print(f"Database written at: {PONDERATION_DATABASE_FILE_KEY}")

    elif option == 3:

        response = input("Are you sure Y/N: ").strip().upper()

        if response == "Y":
            empty_data_base()
            print("Database is empty")


if __name__ == "__main__":
    main()
