from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from main import app
from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.project import Project
from app.models.project_member import ProjectMember


TEST_USER = SimpleNamespace(id=37)


def override_get_current_user():
    return TEST_USER


def test_list_projects_returns_empty_list():
    fake_db = MagicMock()
    fake_db.scalars.return_value.all.return_value = []

    def override_get_db():
        yield fake_db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    try:
        with TestClient(app) as client:
            response = client.get("/projects/")

        assert response.status_code == 200
        assert response.json() == []
        statement = fake_db.scalars.call_args.args[0]
        assert "project_members.user_id" in str(statement)
        assert "projects.organization_id IS NULL" in str(statement)
        assert "projects.archived_at IS NULL" in str(statement)
        assert "projects.deleted_at IS NULL" in str(statement)
        assert TEST_USER.id in statement.compile().params.values()

    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)


def test_list_projects_excludes_deleted_personal_project():
    deleted_project = SimpleNamespace(
        id=1,
        name="Proyecto eliminado",
        description=None,
        status="active",
        created_at=datetime.now(timezone.utc),
        organization_name=None,
        deleted_at=datetime.now(timezone.utc),
    )
    fake_db = MagicMock()

    def scalars(statement):
        result = MagicMock()
        if "projects.deleted_at IS NULL" in str(statement):
            result.all.return_value = []
        else:
            result.all.return_value = [deleted_project]
        return result

    fake_db.scalars.side_effect = scalars

    def override_get_db():
        yield fake_db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    try:
        with TestClient(app) as client:
            response = client.get("/projects/")

        assert response.status_code == 200
        assert response.json() == []
        statement = fake_db.scalars.call_args.args[0]
        assert "projects.deleted_at IS NULL" in str(statement)
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)


def test_list_projects_includes_null_organization_name_for_personal_project():
    project_created_at = datetime.now(timezone.utc)
    project = SimpleNamespace(
        id=1,
        name="Proyecto personal",
        description=None,
        status="active",
        created_at=project_created_at,
    )
    fake_db = MagicMock()
    fake_db.scalars.return_value.all.return_value = [project]

    def override_get_db():
        yield fake_db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    try:
        with TestClient(app) as client:
            response = client.get("/projects/")

        assert response.status_code == 200
        project_response = response.json()[0]
        assert project_response["id"] == 1
        assert project_response["name"] == "Proyecto personal"
        assert project_response["description"] is None
        assert project_response["status"] == "active"
        assert (
            datetime.fromisoformat(
                project_response["created_at"].replace("Z", "+00:00")
            )
            == project_created_at
        )
        assert project_response["organization_name"] is None
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)


def test_create_project_returns_created_project():
    fake_db = MagicMock()
    fake_db_project = MagicMock()
    fake_db_project.id = 1
    fake_db_project.name = "Proyecto de prueba"
    fake_db_project.description = "Descripción de prueba"
    fake_db_project.status = "active"
    fake_db_project.created_at = datetime.now(timezone.utc)
    added = []

    def add(instance):
        added.append(instance)
        if isinstance(instance, Project):
            instance.id = 1

    fake_db.add.side_effect = add
    fake_db.refresh.side_effect = lambda project: (
        setattr(project, "created_at", fake_db_project.created_at),
        setattr(project, "status", "active"),
    )

    def override_get_db():
        yield fake_db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

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
        project = added[0]
        membership = added[1]
        assert isinstance(project, Project)
        assert project.owner_id == TEST_USER.id
        assert isinstance(membership, ProjectMember)
        assert membership.user_id == TEST_USER.id
        assert membership.project_id == project.id
        assert membership.role == "owner"

    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
