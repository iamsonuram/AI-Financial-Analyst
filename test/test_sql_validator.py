from config import DATABASE_PATH
from agents.sql_validator import SQLValidator

validator = SQLValidator(DATABASE_PATH)

sql = """
SELECT Cedent_Name,
SUM(Premium)
FROM finance_data
GROUP BY Cedent_Name;
"""

valid, message = validator.validate(sql)

print(valid)
print(message)