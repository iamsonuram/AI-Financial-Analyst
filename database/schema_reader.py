import sqlite3
from database.metadata import COLUMN_DESCRIPTIONS


class SchemaReader:
    """Reads database schema information."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def get_schema(self) -> str:
        """Return database schema with business descriptions."""

        connection = sqlite3.connect(self.db_path)
        cursor = connection.cursor()

        cursor.execute("""
            SELECT name
            FROM sqlite_master
            WHERE type='table';
        """)

        tables = cursor.fetchall()
        schema = []

        for table in tables:
            table_name = table[0]
            schema.append(f"Table: {table_name}")

            cursor.execute(f"PRAGMA table_info({table_name});")
            columns = cursor.fetchall()

            for column in columns:
                column_name = column[1]
                column_type = column[2]
                description = COLUMN_DESCRIPTIONS.get(column_name, "No description available.")

                schema.append(f"  • {column_name} ({column_type})")
                schema.append(f"    Description: {description}")

            schema.append("")

        connection.close()

        return "\n".join(schema)