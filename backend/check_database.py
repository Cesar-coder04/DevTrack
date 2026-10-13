
from sqlalchemy import text

from app.db.session import engine

try:
    with engine.connect() as connection:
        result = connection.execute(text("SELECT DATABASE()"))
        database_name = result.scalar()

        print(f"Connected to database: {database_name}")
finally:
    engine.dispose()
