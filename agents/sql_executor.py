import time

from database.database import SQLiteManager
from agents.sql_validator import SQLValidator


class SQLExecutor:
    """Validates and executes SQL queries."""

    def __init__(self, database_path):
        self.database = SQLiteManager(database_path)
        self.validator = SQLValidator(database_path)

    def execute(self, query: str):
        """
        Validate and execute SQL.

        Returns:
            {
                "success": bool,
                "message": str,
                "execution_time": float,
                "row_count": int,
                "data": DataFrame | None
            }
        """

        valid, message = self.validator.validate(query)

        if not valid:
            return {
                "success": False,
                "message": message,
                "execution_time": 0,
                "row_count": 0,
                "data": None
            }

        start_time = time.time()

        dataframe = self.database.execute_query(query)

        execution_time = round(time.time() - start_time, 3)

        return {
            "success": True,
            "message": "Query executed successfully.",
            "execution_time": execution_time,
            "row_count": len(dataframe),
            "data": dataframe
        }