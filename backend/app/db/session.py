
from functools import partial

from sqlalchemy import create_engine, event
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker

from app.config import (
    DB_MODE,
    DB_HOST,
    DB_NAME,
    DB_PASSWORD,
    DB_PORT,
    DB_USER,
    INTEGRATION_DATABASE_SETTINGS,
)
from app.db.integration_database import (
    create_integration_engine,
    verify_integration_checkout,
)

if not DB_USER or not DB_PASSWORD:
    raise RuntimeError(
        "Database credentials are missing. Check the backend/.env file."
    )

if DB_MODE == "integration":
    engine = create_integration_engine(INTEGRATION_DATABASE_SETTINGS)
    event.listen(
        engine,
        "checkout",
        partial(
            verify_integration_checkout,
            expected_user=INTEGRATION_DATABASE_SETTINGS.username,
        ),
    )
else:
    DATABASE_URL = URL.create(
        drivername="mysql+pymysql",
        username=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
    )
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
    )

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
