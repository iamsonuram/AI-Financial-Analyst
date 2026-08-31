from config import DATABASE_PATH
from database.schema_reader import SchemaReader

schema_reader = SchemaReader(DATABASE_PATH)

print(schema_reader.get_schema())