import sqlite3

from config import DATABASE_PATH

conn = sqlite3.connect(DATABASE_PATH)
cursor = conn.cursor()

# ---------------------------------------------------
# Standardize Region
# ---------------------------------------------------

cursor.execute("""
UPDATE finance_data
SET Region = TRIM(Region)
""")

cursor.execute("""
UPDATE finance_data
SET Region =
CASE
    WHEN LOWER(Region)='asia' THEN 'Asia'
    WHEN LOWER(Region)='americas' THEN 'Americas'
    WHEN LOWER(Region)='emea' THEN 'EMEA'
    ELSE Region
END
""")

# ---------------------------------------------------
# Standardize Market Unit
# ---------------------------------------------------

cursor.execute("""
UPDATE finance_data
SET Market_Unit = TRIM(Market_Unit)
""")

cursor.execute("""
UPDATE finance_data
SET Market_Unit =
CASE

WHEN LOWER(Market_Unit)='anz' THEN 'ANZ'
WHEN LOWER(Market_Unit)='us' THEN 'US'

ELSE
UPPER(SUBSTR(Market_Unit,1,1)) ||
LOWER(SUBSTR(Market_Unit,2))

END
""")

conn.commit()

print("Database cleaned successfully.")

conn.close()