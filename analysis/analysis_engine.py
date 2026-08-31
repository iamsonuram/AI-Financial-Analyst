import sqlite3
import pandas as pd

from config import DATABASE_PATH


class AnalysisEngine:

    def __init__(self):
        self.conn = sqlite3.connect(DATABASE_PATH)

    def get_dashboard(self, region, market_unit):

        query = """
        SELECT *
        FROM dashboard_metrics
        WHERE Region = ?
        AND Market_Unit = ?
        """

        df = pd.read_sql(
            query,
            self.conn,
            params=[region, market_unit]
        )

        if df.empty:
            return None

        return df.iloc[0].to_dict()

    def close(self):
        self.conn.close()