import sqlite3
import pandas as pd
from config import DATABASE_PATH

conn = sqlite3.connect(DATABASE_PATH)

print("dashboard_metrics")
print(pd.read_sql("""
SELECT Region, Market_Unit
FROM dashboard_metrics
ORDER BY Region, Market_Unit
""", conn))

conn.close()