
import os

from dotenv import load_dotenv

load_dotenv("backend/.env")

database_host = os.getenv("DB_HOST")
database_name = os.getenv("DB_NAME")
database_user = os.getenv("DB_USER")

print(f"Database host: {database_host}")
print(f"Database name: {database_name}")
print(f"Database user: {database_user}")
