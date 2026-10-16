import os

import pytest

from app.db.integration_database import (
    INTEGRATION_DB_MODE,
    load_integration_database_settings,
)


def pytest_addoption(parser):
    parser.addoption(
        "--integration",
        action="store_true",
        default=False,
        help="run tests with the explicitly validated integration database",
    )


def pytest_configure(config):
    integration_mode = (
        os.environ.get("DEVTRACK_DB_MODE", "").strip().lower()
        == INTEGRATION_DB_MODE
    )
    integration_option = config.getoption("--integration")

    if integration_mode and not integration_option:
        raise pytest.UsageError(
            "DEVTRACK_DB_MODE=integration requires pytest --integration."
        )
    if integration_option and not integration_mode:
        raise pytest.UsageError(
            "pytest --integration requires DEVTRACK_DB_MODE=integration."
        )
    if integration_mode and config.option.markexpr.strip() != "integration":
        raise pytest.UsageError(
            "Integration mode requires the exact test selection "
            "'-m integration'; only explicitly marked tests may run."
        )

    if integration_mode:
        try:
            load_integration_database_settings(os.environ)
        except RuntimeError as exc:
            raise pytest.UsageError(str(exc)) from None

    if config.option.markexpr.strip() == "integration" and not integration_mode:
        raise pytest.UsageError(
            "Integration tests require DEVTRACK_DB_MODE=integration "
            "and pytest --integration."
        )


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(config, items):
    if config.getoption("--integration"):
        unmarked_items = [
            item for item in items if not item.get_closest_marker("integration")
        ]
        if not unmarked_items:
            return
        names = ", ".join(item.nodeid for item in unmarked_items[:3])
        raise pytest.UsageError(
            "Integration mode selected tests without "
            f"@pytest.mark.integration: {names}"
        )
