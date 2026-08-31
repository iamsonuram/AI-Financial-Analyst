import sqlite3
import pandas as pd

from config import DATABASE_PATH


class DashboardBuilder:

    def __init__(self):
        self.conn = sqlite3.connect(DATABASE_PATH)

    def build_dashboard_table(self):

        df = pd.read_sql("SELECT * FROM finance_data", self.conn)

        dashboard_rows = []

        grouped = df.groupby(["Region", "Market_Unit"])

        for (region, market_unit), group in grouped:

            actual_tr = group["Technical_Result"].sum()
            actual_premium = group["Premium"].sum()

            nb_group = group[group["P_Zero_Flag"] == "Yes"]

            nb_tr = nb_group["Technical_Result"].sum()
            nb_premium = nb_group["Premium"].sum()

            tcr = group["Combined_Ratio"].mean()

            dashboard_rows.append({
                "Region": region,
                "Market_Unit": market_unit,
                "Actual_TR": round(float(actual_tr), 2),
                "Actual_Premium": round(float(actual_premium), 2),
                "NB_Expected_TR": round(float(nb_tr), 2),
                "NB_Expected_Premium": round(float(nb_premium), 2),
                "TCR": round(float(tcr), 4)
            })

        dashboard_df = pd.DataFrame(dashboard_rows)

        dashboard_df.to_sql(
            "dashboard_metrics",
            self.conn,
            if_exists="replace",
            index=False
        )

        self.conn.close()

        print("dashboard_metrics table created successfully.")