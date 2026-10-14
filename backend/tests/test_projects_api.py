from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from main import app
from app.db.session import get_db


def test_list_projects_returns_empty_list():
    fake_db = MagicMock()
    fake_db.execute.return_value.scalars.return_value.all.return_value = []

    def override_get_db():
        yield fake_db

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as client:
            response = client.get("/projects/")

        assert response.status_code == 200
        assert response.json() == []

    finally:
        app.dependency_overrides.pop(get_db, None)
