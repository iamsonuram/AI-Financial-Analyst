from database.database import SQLiteManager
from config import DATABASE_PATH
from analysis.evidence_analyzer import EvidenceAnalyzer


database = SQLiteManager(DATABASE_PATH)

query = """
SELECT
    Main_Line_of_Business,
    SUM(
        CASE
            WHEN Accounting_Year = 2025
            THEN Technical_Result
            ELSE 0
        END
    )
    -
    SUM(
        CASE
            WHEN Accounting_Year = 2024
            THEN Technical_Result
            ELSE 0
        END
    ) AS Change_TR
FROM finance_data
WHERE Region = 'Americas'
  AND Market_Unit = 'Canada'
GROUP BY Main_Line_of_Business;
"""

df = database.execute_query(query)

analyzer = EvidenceAnalyzer()

evidence = analyzer.analyze(df)

print("\n================ EVIDENCE ================\n")

print("FACTS:")
for fact in evidence["facts"]:
    print("-", fact)

print("\nDRIVERS:")
for driver in evidence["drivers"]:
    print("-", driver)

print("\nDIMENSIONS:")
print(evidence["dimensions"])

print("\nWARNINGS:")
for warning in evidence["warnings"]:
    print("-", warning)