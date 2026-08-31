import sqlite3
import pandas as pd

from config import DATABASE_PATH


class FilterLoader:

    def __init__(self):
        self.conn = sqlite3.connect(DATABASE_PATH)

    def get_regions(self):

        query = """
        SELECT DISTINCT Region
        FROM finance_data
        ORDER BY Region
        """

        return pd.read_sql(query, self.conn)["Region"].tolist()

    def get_market_units(self, region):

        query = """
        SELECT DISTINCT Market_Unit
        FROM finance_data
        WHERE Region = ?
        ORDER BY Market_Unit
        """

        return pd.read_sql(
            query,
            self.conn,
            params=[region]
        )["Market_Unit"].tolist()

    def close(self):
        self.conn.close()