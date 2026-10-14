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

        
def test_create_project_returns_created_project():
    fake_db = MagicMock()
    fake_db_project = MagicMock()
    fake_db_project.id = 1
    fake_db_project.name = "Proyecto de prueba"
    fake_db_project.description = "Descripción de prueba"
    fake_db_project.status = "active"
    from datetime import datetime, timezone
    fake_db_project.created_at = datetime.now(timezone.utc)

    fake_db.add.side_effect = lambda project: setattr(
        project, "id", 1
    )
    fake_db.refresh.side_effect = lambda project: (
        setattr(project, "created_at", fake_db_project.created_at),
        setattr(project, "status", "active"),
    )

    def override_get_db():
        yield fake_db

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as client:
            response = client.post(
                "/projects/",
                json={
                    "name": "Proyecto de prueba",
                    "description": "Descripción de prueba",
                },
            )

        assert response.status_code == 201
        assert response.json()["name"] == "Proyecto de prueba"
        assert response.json()["id"] == 1

    finally:
        app.dependency_overrides.pop(get_db, None)
