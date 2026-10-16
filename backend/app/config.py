import os
from pathlib import Path

from dotenv import load_dotenv

from app.db.integration_database import (
    get_database_mode,
    load_integration_database_settings,
)

BACKEND_DIR = Path(__file__).resolve().parents[1]
ENV_FILE = BACKEND_DIR / ".env"

DB_MODE = get_database_mode(os.environ)
INTEGRATION_DATABASE_SETTINGS = None
if DB_MODE == "integration":
    INTEGRATION_DATABASE_SETTINGS = load_integration_database_settings(os.environ)
    DB_HOST = INTEGRATION_DATABASE_SETTINGS.host
    DB_PORT = INTEGRATION_DATABASE_SETTINGS.port
    DB_NAME = INTEGRATION_DATABASE_SETTINGS.database
    DB_USER = INTEGRATION_DATABASE_SETTINGS.username
    DB_PASSWORD = INTEGRATION_DATABASE_SETTINGS.password
else:
    load_dotenv(ENV_FILE)
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT", "3306"))
    DB_NAME = os.getenv("DB_NAME", "devtrack")
    DB_USER = os.getenv("DB_USER")
    DB_PASSWORD = os.getenv("DB_PASSWORD")

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
APP_ENV = os.getenv("APP_ENV", "production").strip().lower()

EMAIL_PROVIDER = os.getenv("EMAIL_PROVIDER", "smtp").strip().lower()
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM = os.getenv("SMTP_FROM")
SMTP_STARTTLS = os.getenv("SMTP_STARTTLS", "true").strip().lower() in {
    "1",
    "true",
    "yes",
}
APP_BASE_URL = os.getenv("APP_BASE_URL")

if not JWT_SECRET_KEY or len(JWT_SECRET_KEY) < 32:
    raise RuntimeError(
        "JWT_SECRET_KEY must contain at least 32 characters. "
        "Configure it in backend/.env."
    )
