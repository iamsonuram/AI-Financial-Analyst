from config import DATABASE_PATH
from agents.sql_agent import SQLAgent

agent = SQLAgent(DATABASE_PATH)

question = "Show the Top 10 Cedents having highest Premium in 2025."

sql = agent.generate_sql(question)

print("\nGenerated SQL:\n")
print(sql)