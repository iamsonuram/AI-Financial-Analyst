import sqlite3


class SQLValidator:
    """Validates SQL queries before execution."""

    def __init__(self, db_path):
        self.db_path = db_path

    def validate(self, query: str):
        """
        Validate SQL syntax using SQLite.

        Returns:
            (True, "Valid SQL") if valid
            (False, error_message) if invalid
        """

        connection = sqlite3.connect(self.db_path)

        try:
            connection.execute(f"EXPLAIN QUERY PLAN {query}")
            return True, "Valid SQL"

        except Exception as error:
            return False, str(error)

        finally:
            connection.close()