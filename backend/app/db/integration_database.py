import ipaddress
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping

from sqlalchemy import create_engine
from sqlalchemy.exc import DisconnectionError
from sqlalchemy.engine import Engine, URL


INTEGRATION_DATABASE_NAME = "devtrack_integration_test"
INTEGRATION_DB_MODE = "integration"


@dataclass(frozen=True)
class IntegrationDatabaseSettings:
    host: str
    port: int
    database: str
    username: str
    password: str = field(repr=False)
    ssl_ca: str | None = None


def get_database_mode(environ: Mapping[str, str]) -> str:
    mode = environ.get("DEVTRACK_DB_MODE", "development").strip().lower()
    if mode not in {"development", INTEGRATION_DB_MODE}:
        raise RuntimeError(
            "DEVTRACK_DB_MODE must be 'development' or 'integration'."
        )
    return mode


def load_integration_database_settings(
    environ: Mapping[str, str],
) -> IntegrationDatabaseSettings:
    if get_database_mode(environ) != INTEGRATION_DB_MODE:
        raise RuntimeError(
            "Integration database settings require "
            "DEVTRACK_DB_MODE=integration."
        )

    names = {
        "host": "INTEGRATION_DB_HOST",
        "port": "INTEGRATION_DB_PORT",
        "database": "INTEGRATION_DB_NAME",
        "username": "INTEGRATION_DB_USER",
        "password": "INTEGRATION_DB_PASSWORD",
    }
    missing = [
        name
        for name in names.values()
        if not environ.get(name, "").strip()
    ]
    if missing:
        raise RuntimeError(
            "Integration database configuration is incomplete; set "
            + ", ".join(missing)
            + "."
        )

    database = environ[names["database"]].strip()
    if database != INTEGRATION_DATABASE_NAME:
        raise RuntimeError(
            f"Integration database must be named "
            f"'{INTEGRATION_DATABASE_NAME}'."
        )

    username = environ[names["username"]].strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", username):
        raise RuntimeError(
            "INTEGRATION_DB_USER must contain only letters, digits, "
            "periods, underscores, or hyphens."
        )

    try:
        port = int(environ[names["port"]])
    except ValueError:
        raise RuntimeError("INTEGRATION_DB_PORT must be an integer.") from None
    if not 1 <= port <= 65535:
        raise RuntimeError("INTEGRATION_DB_PORT must be between 1 and 65535.")

    host = environ[names["host"]].strip()
    if not host:
        raise RuntimeError("INTEGRATION_DB_HOST must not be empty.")

    ssl_ca = environ.get("INTEGRATION_DB_SSL_CA", "").strip() or None
    is_local = is_loopback_host(host)
    if not is_local and ssl_ca is None:
        raise RuntimeError(
            "INTEGRATION_DB_SSL_CA is required for remote database hosts."
        )
    if ssl_ca is not None and not Path(ssl_ca).is_file():
        raise RuntimeError(
            "INTEGRATION_DB_SSL_CA must point to an existing CA certificate file."
        )

    return IntegrationDatabaseSettings(
        host=host,
        port=port,
        database=database,
        username=username,
        password=environ[names["password"]],
        ssl_ca=ssl_ca,
    )


def is_loopback_host(host: str) -> bool:
    normalized = host.strip().lower().strip("[]")
    if normalized == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def create_integration_engine(
    settings: IntegrationDatabaseSettings,
    *,
    engine_factory: Callable[..., Engine] | None = None,
) -> Engine:
    if engine_factory is None:
        engine_factory = create_engine
    url = URL.create(
        drivername="mysql+pymysql",
        username=settings.username,
        password=settings.password,
        host=settings.host,
        port=settings.port,
        database=settings.database,
    )
    connect_args = {}
    if settings.ssl_ca:
        connect_args = {
            "ssl_ca": settings.ssl_ca,
            "ssl_verify_cert": True,
            "ssl_verify_identity": True,
        }
    return engine_factory(url, pool_pre_ping=True, connect_args=connect_args)


def verify_integration_connection(
    dbapi_connection,
    _connection_record,
    *,
    expected_database: str = INTEGRATION_DATABASE_NAME,
    expected_user: str,
) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("SELECT DATABASE(), CURRENT_USER()")
        identity = cursor.fetchone()
        if not identity or identity[0] != expected_database:
            raise RuntimeError(
                "Integration connection is not using the expected database."
            )

        active_user = (
            identity[1].rsplit("@", 1)[0].strip("`'") if identity[1] else ""
        )
        if active_user != expected_user:
            raise RuntimeError(
                "Integration connection is not using the expected database user."
            )

        cursor.execute("SHOW GRANTS")
        grants = cursor.fetchall()
        if not grants:
            raise RuntimeError(
                "Integration database user has no verifiable grants."
            )
        for row in grants:
            grant = row[0]
            if isinstance(grant, bytes):
                grant = grant.decode("utf-8", errors="replace")
            _validate_integration_grant(str(grant), expected_database)
    except RuntimeError:
        raise
    except Exception:
        raise RuntimeError(
            "Could not verify the integration database connection and grants."
        ) from None
    finally:
        try:
            cursor.close()
        finally:
            dbapi_connection.rollback()


def verify_integration_checkout(
    dbapi_connection,
    connection_record,
    connection_proxy,
    *,
    expected_user: str,
) -> None:
    try:
        verify_integration_connection(
            dbapi_connection,
            connection_record,
            expected_user=expected_user,
        )
    except Exception:
        raise DisconnectionError(
            "Integration database connection failed its safety check."
        ) from None


def _validate_integration_grant(grant: str, expected_database: str) -> None:
    normalized = grant.strip().replace("`", "").lower()
    if "with grant option" in normalized:
        raise RuntimeError(
            "Integration database user must not be able to grant privileges."
        )
    if re.match(r"^grant\s+usage\s+on\s+\*\.\*\s+to\s+", normalized):
        return

    match = re.match(r"^grant\s+.+\s+on\s+(.+?)\s+to\s+", normalized)
    if match and match.group(1) == f"{expected_database.lower()}.*":
        return

    raise RuntimeError(
        "Integration database user has privileges outside the dedicated "
        "integration database."
    )
