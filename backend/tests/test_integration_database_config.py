import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import DisconnectionError

from app.db.integration_database import (
    INTEGRATION_DATABASE_NAME,
    create_integration_engine,
    get_database_mode,
    is_loopback_host,
    load_integration_database_settings,
    verify_integration_checkout,
    verify_integration_connection,
)

_conftest_spec = importlib.util.spec_from_file_location(
    "devtrack_test_conftest", Path(__file__).with_name("conftest.py")
)
_conftest = importlib.util.module_from_spec(_conftest_spec)
_conftest_spec.loader.exec_module(_conftest)
pytest_collection_modifyitems = _conftest.pytest_collection_modifyitems
pytest_configure = _conftest.pytest_configure


def valid_environment():
    return {
        "DEVTRACK_DB_MODE": "integration",
        "INTEGRATION_DB_HOST": "127.0.0.1",
        "INTEGRATION_DB_PORT": "3307",
        "INTEGRATION_DB_NAME": INTEGRATION_DATABASE_NAME,
        "INTEGRATION_DB_USER": "devtrack_test_runner",
        "INTEGRATION_DB_PASSWORD": "integration-password",
    }


def test_database_mode_defaults_to_development():
    assert get_database_mode({}) == "development"


def test_integration_settings_require_explicit_mode():
    environment = valid_environment()
    environment.pop("DEVTRACK_DB_MODE")

    with pytest.raises(RuntimeError, match="DEVTRACK_DB_MODE=integration"):
        load_integration_database_settings(environment)


def test_integration_settings_reject_development_database_name():
    environment = valid_environment()
    environment["INTEGRATION_DB_NAME"] = "devtrack"

    with pytest.raises(RuntimeError, match="must be named") as exc:
        load_integration_database_settings(environment)
    assert environment["INTEGRATION_DB_PASSWORD"] not in str(exc.value)


@pytest.mark.parametrize(
    "missing_variable",
    [
        "INTEGRATION_DB_HOST",
        "INTEGRATION_DB_PORT",
        "INTEGRATION_DB_NAME",
        "INTEGRATION_DB_USER",
        "INTEGRATION_DB_PASSWORD",
    ],
)
def test_integration_settings_reject_missing_required_variables(missing_variable):
    environment = valid_environment()
    environment.pop(missing_variable)

    with pytest.raises(RuntimeError, match=missing_variable):
        load_integration_database_settings(environment)


def test_valid_integration_settings_create_engine_without_connecting():
    settings = load_integration_database_settings(valid_environment())
    factory_calls = []

    def engine_factory(url, **kwargs):
        factory_calls.append((url, kwargs))
        return object()

    engine = create_integration_engine(settings, engine_factory=engine_factory)

    assert engine is not None
    assert len(factory_calls) == 1
    url, options = factory_calls[0]
    assert url.drivername == "mysql+pymysql"
    assert url.database == INTEGRATION_DATABASE_NAME
    assert url.host == "127.0.0.1"
    assert url.port == 3307
    assert options == {"pool_pre_ping": True, "connect_args": {}}


def test_remote_integration_host_requires_verified_ca_certificate(tmp_path):
    environment = valid_environment()
    environment["INTEGRATION_DB_HOST"] = "mysql.test.internal"

    with pytest.raises(RuntimeError, match="SSL_CA is required"):
        load_integration_database_settings(environment)

    ca_file = tmp_path / "test-ca.pem"
    ca_file.write_text("test CA only", encoding="ascii")
    environment["INTEGRATION_DB_SSL_CA"] = str(ca_file)
    settings = load_integration_database_settings(environment)
    calls = []
    create_integration_engine(
        settings,
        engine_factory=lambda url, **kwargs: calls.append(kwargs) or object(),
    )

    assert calls[0]["connect_args"] == {
        "ssl_ca": str(ca_file),
        "ssl_verify_cert": True,
        "ssl_verify_identity": True,
    }


def test_local_integration_host_does_not_require_tls_ca():
    settings = load_integration_database_settings(valid_environment())
    assert settings.ssl_ca is None
    assert is_loopback_host("localhost")
    assert is_loopback_host("127.0.0.1")
    assert is_loopback_host("::1")
    assert not is_loopback_host("mysql.test.internal")


def test_integration_settings_repr_does_not_reveal_password():
    settings = load_integration_database_settings(valid_environment())

    assert "integration-password" not in repr(settings)
    assert "devtrack_test_runner" in repr(settings)


def test_invalid_integration_settings_are_rejected_before_engine_creation():
    environment = valid_environment()
    environment["INTEGRATION_DB_NAME"] = "devtrack"
    factory_calls = []

    def engine_factory(*args, **kwargs):
        factory_calls.append((args, kwargs))

    with pytest.raises(RuntimeError, match="must be named"):
        settings = load_integration_database_settings(environment)
        create_integration_engine(settings, engine_factory=engine_factory)

    assert factory_calls == []


class FakeCursor:
    def __init__(self, identity, grants):
        self.identity = identity
        self.grants = grants
        self.executed = []
        self.result = None
        self.closed = False

    def execute(self, statement):
        self.executed.append(statement)
        self.result = self.identity if statement.startswith("SELECT") else self.grants

    def fetchone(self):
        return self.result

    def fetchall(self):
        return self.result

    def close(self):
        self.closed = True


class FakeConnection:
    def __init__(self, identity, grants):
        self.fake_cursor = FakeCursor(identity, grants)
        self.rollbacks = 0

    def cursor(self):
        return self.fake_cursor

    def rollback(self):
        self.rollbacks += 1


def test_connection_guard_accepts_expected_database_and_schema_scoped_grants():
    connection = FakeConnection(
        (INTEGRATION_DATABASE_NAME, "devtrack_test_runner@localhost"),
        [
            ("GRANT USAGE ON *.* TO `devtrack_integration_test`@`localhost`",),
            (
                "GRANT ALL PRIVILEGES ON "
                "`devtrack_integration_test`.* "
                "TO `devtrack_test_runner`@`localhost`",
            ),
        ],
    )

    verify_integration_connection(
        connection, None, expected_user="devtrack_test_runner"
    )

    assert connection.fake_cursor.executed == [
        "SELECT DATABASE(), CURRENT_USER()",
        "SHOW GRANTS",
    ]
    assert connection.fake_cursor.closed
    assert connection.rollbacks == 1


@pytest.mark.parametrize(
    ("identity", "grants", "expected_message"),
    [
        (
            ("devtrack", "devtrack_test_runner@localhost"),
            [("GRANT USAGE ON *.* TO account",)],
            "expected database",
        ),
        (
            (INTEGRATION_DATABASE_NAME, "development_user@localhost"),
            [("GRANT USAGE ON *.* TO account",)],
            "expected database user",
        ),
        (
            (INTEGRATION_DATABASE_NAME, "devtrack_test_runner@localhost"),
            [
                (
                    "GRANT ALL PRIVILEGES ON *.* "
                    "TO `devtrack_integration_test`@`localhost`",
                )
            ],
            "outside the dedicated",
        ),
        (
            (INTEGRATION_DATABASE_NAME, "devtrack_test_runner@localhost"),
            [
                (
                    "GRANT ALL PRIVILEGES ON "
                    "`devtrack_integration_test`.* "
                    "TO `devtrack_test_runner`@`localhost` "
                    "WITH GRANT OPTION",
                )
            ],
            "must not be able to grant",
        ),
    ],
)
def test_connection_guard_rejects_wrong_database_user_or_global_grants(
    identity,
    grants,
    expected_message,
):
    connection = FakeConnection(identity, grants)

    with pytest.raises(RuntimeError, match=expected_message):
        verify_integration_connection(
            connection, None, expected_user="devtrack_test_runner"
        )

    assert connection.fake_cursor.closed
    assert connection.rollbacks == 1


def test_pytest_integration_mode_requires_exact_marker_expression(monkeypatch):
    monkeypatch.setenv("DEVTRACK_DB_MODE", "integration")
    config = SimpleNamespace(
        getoption=lambda option: True,
        option=SimpleNamespace(markexpr="integration or unit"),
    )

    with pytest.raises(pytest.UsageError, match="exact test selection"):
        pytest_configure(config)


def test_pytest_integration_option_rejects_unmarked_collected_items():
    config = SimpleNamespace(getoption=lambda option: True)
    marked = SimpleNamespace(
        nodeid="test_integration.py::test_db",
        get_closest_marker=lambda marker: object(),
    )
    unmarked = SimpleNamespace(
        nodeid="test_unit.py::test_unit",
        get_closest_marker=lambda marker: None,
    )

    with pytest.raises(pytest.UsageError, match="without"):
        pytest_collection_modifyitems(config, [marked, unmarked])


def test_pytest_integration_mode_without_option_fails_before_collection(monkeypatch):
    monkeypatch.setenv("DEVTRACK_DB_MODE", "integration")
    config = SimpleNamespace(
        getoption=lambda option: False,
        option=SimpleNamespace(markexpr=""),
    )

    with pytest.raises(pytest.UsageError, match="requires pytest --integration"):
        pytest_configure(config)


def test_checkout_guard_translates_failed_validation_to_pool_disconnect():
    connection = FakeConnection(
        ("devtrack", "devtrack_test_runner@localhost"),
        [("GRANT USAGE ON *.* TO account",)],
    )

    with pytest.raises(DisconnectionError):
        verify_integration_checkout(
            connection,
            None,
            None,
            expected_user="devtrack_test_runner",
        )

    assert connection.fake_cursor.closed


def test_checkout_guard_revalidates_reused_connections():
    connection = FakeConnection(
        (INTEGRATION_DATABASE_NAME, "devtrack_test_runner@localhost"),
        [("GRANT USAGE ON *.* TO `devtrack_test_runner`@`localhost`",)],
    )

    for _ in range(2):
        verify_integration_checkout(
            connection,
            None,
            None,
            expected_user="devtrack_test_runner",
        )

    assert connection.fake_cursor.executed == [
        "SELECT DATABASE(), CURRENT_USER()",
        "SHOW GRANTS",
        "SELECT DATABASE(), CURRENT_USER()",
        "SHOW GRANTS",
    ]
    assert connection.rollbacks == 2
