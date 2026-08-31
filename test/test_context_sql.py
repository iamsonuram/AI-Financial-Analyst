from config import DATABASE_PATH
from agents.sql_agent import SQLAgent

agent = SQLAgent(DATABASE_PATH)

sql = agent.generate_sql(
    question="Generate Executive Commentary",
    region="Asia",
    market_unit="Japan",
    driver1="Main_Line_of_Business",
    driver2="Cedent_Name"
)

print(sql)