import sqlite3
import pandas as pd


class SQLiteManager:
    """Handles all SQLite database operations."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def execute_query(self, query: str) -> pd.DataFrame:
        """Execute a SQL query and return the result as a DataFrame."""

        connection = sqlite3.connect(self.db_path)

        try:
            dataframe = pd.read_sql_query(query, connection)
        finally:
            connection.close()

        return dataframe

    def list_tables(self) -> list:
        """Return all table names in the database."""

        connection = sqlite3.connect(self.db_path)
        cursor = connection.cursor()

        cursor.execute("""
            SELECT name
            FROM sqlite_master
            WHERE type='table';
        """)

        tables = [table[0] for table in cursor.fetchall()]
        connection.close()

        return tables