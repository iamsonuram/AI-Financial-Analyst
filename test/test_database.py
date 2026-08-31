from database.database import SQLiteManager
from config import DATABASE_PATH

db = SQLiteManager(DATABASE_PATH)

print("Available Tables:")
print(db.list_tables())