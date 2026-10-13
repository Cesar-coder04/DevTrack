
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv("backend/.env")

database_url = (
    f"mysql+pymysql://{os.getenv('DB_USER')}:"
    f"{os.getenv('DB_PASSWORD')}@"
    f"{os.getenv('DB_HOST')}:"
    f"{os.getenv('DB_PORT')}/"
    f"{os.getenv('DB_NAME')}"
)

engine = create_engine(database_url)

try:
    with engine.connect() as connection:
        result = connection.execute(text("SELECT DATABASE()"))
        print(f"Connected to database: {result.scalar()}")
finally:
    engine.dispose()
