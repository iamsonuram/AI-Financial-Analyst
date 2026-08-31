from config import DATABASE_PATH

from agents.sql_executor import SQLExecutor

executor = SQLExecutor(DATABASE_PATH)

sql = """
SELECT
    Cedent_Name,
    SUM(Premium) AS Total_Premium
FROM finance_data
WHERE Accounting_Year = 2025
GROUP BY Cedent_Name
ORDER BY Total_Premium DESC
LIMIT 10;
"""

result = executor.execute(sql)

print("\nExecution Status:", result["success"])
print("Message:", result["message"])
print("Execution Time:", result["execution_time"], "seconds")
print("Rows Returned:", result["row_count"])

print("\nResult:\n")

print(result["data"])