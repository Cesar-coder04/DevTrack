from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api import projects as personal_projects
from app.api.routes import organization_projects
from app.models.project import Project
from app.schemas.organization_project import OrganizationProjectCreate
from app.schemas.project import ProjectCreate
from app.services.project_service import ensure_project_name_available


@pytest.fixture
def project_session():
    engine = create_engine("sqlite://")
    Project.__table__.create(engine)
    try:
        with Session(engine) as session:
            yield session
    finally:
        engine.dispose()


def test_personal_creation_rejects_duplicate_name_in_owner_scope():
    db = MagicMock()
    db.scalar.return_value = 12

    with pytest.raises(HTTPException) as error:
        personal_projects.create_project(
            ProjectCreate(name="DevTrack"),
            db=db,
            user=SimpleNamespace(id=4),
        )

    assert error.value.status_code == 409
    assert "proyecto" in error.value.detail
    assert "eliminado" in error.value.detail
    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_organization_creation_rejects_duplicate_name_in_same_organization():
    db = MagicMock()
    db.get.side_effect = [
        SimpleNamespace(deleted_at=None),
        SimpleNamespace(role="member"),
    ]
    db.scalar.return_value = 12

    with pytest.raises(HTTPException) as error:
        organization_projects.create_project(
            organization_id=8,
            project_data=OrganizationProjectCreate(name="DevTrack"),
            db=db,
            current_user=SimpleNamespace(id=4),
        )

    assert error.value.status_code == 409
    assert "proyecto" in error.value.detail
    assert "eliminado" in error.value.detail
    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_personal_creation_maps_unique_constraint_race_to_conflict():
    db = MagicMock()
    db.scalar.return_value = None
    db.add.side_effect = lambda project: setattr(project, "id", 12)
    db.commit.side_effect = IntegrityError(
        "insert",
        {},
        Exception(
            "Duplicate entry for key "
            "'uq_projects_active_personal_owner_name'"
        ),
    )

    with pytest.raises(HTTPException) as error:
        personal_projects.create_project(
            ProjectCreate(name="DevTrack"),
            db=db,
            user=SimpleNamespace(id=4),
        )

    assert error.value.status_code == 409
    db.rollback.assert_called_once()


def test_organization_creation_maps_unique_constraint_race_to_conflict():
    db = MagicMock()
    db.get.side_effect = [
        SimpleNamespace(deleted_at=None),
        SimpleNamespace(role="member"),
    ]
    db.scalar.return_value = None
    db.add.side_effect = lambda project: setattr(project, "id", 12)
    db.commit.side_effect = IntegrityError(
        "insert",
        {},
        Exception(
            "Duplicate entry for key "
            "'uq_projects_active_organization_name'"
        ),
    )

    with pytest.raises(HTTPException) as error:
        organization_projects.create_project(
            organization_id=8,
            project_data=OrganizationProjectCreate(name="DevTrack"),
            db=db,
            current_user=SimpleNamespace(id=4),
        )

    assert error.value.status_code == 409
    db.rollback.assert_called_once()


def test_different_organizations_can_use_the_same_project_name(project_session):
    project_session.add_all(
        [
            Project(name="DevTrack", organization_id=8, owner_id=4),
            Project(name="DevTrack", organization_id=9, owner_id=5),
        ]
    )
    project_session.commit()

    ensure_project_name_available(
        project_session,
        name="DevTrack",
        owner_id=6,
        organization_id=10,
    )


def test_database_constraints_reject_duplicate_active_names(project_session):
    project_session.add(
        Project(name="DevTrack", organization_id=8, owner_id=4)
    )
    project_session.commit()

    project_session.add(
        Project(name="DevTrack", organization_id=8, owner_id=5)
    )
    with pytest.raises(IntegrityError):
        project_session.commit()
    project_session.rollback()

    project_session.add(
        Project(name="DevTrack", organization_id=None, owner_id=4)
    )
    project_session.commit()
    project_session.add(
        Project(name="DevTrack", organization_id=None, owner_id=4)
    )
    with pytest.raises(IntegrityError):
        project_session.commit()
    project_session.rollback()


def test_personal_names_are_unique_per_owner_not_across_scopes(project_session):
    project_session.add_all(
        [
            Project(name="DevTrack", organization_id=None, owner_id=4),
            Project(name="DevTrack", organization_id=None, owner_id=5),
            Project(name="DevTrack", organization_id=8, owner_id=6),
        ]
    )
    project_session.commit()

    with pytest.raises(HTTPException) as error:
        ensure_project_name_available(
            project_session,
            name="DevTrack",
            owner_id=4,
            organization_id=None,
        )
    assert error.value.status_code == 409

    ensure_project_name_available(
        project_session,
        name="DevTrack",
        owner_id=7,
        organization_id=None,
    )


@pytest.mark.parametrize("inactive_field", ["archived_at", "deleted_at"])
def test_archived_or_deleted_project_does_not_block_name_reuse(
    project_session,
    inactive_field,
):
    project = Project(name="DevTrack", organization_id=8, owner_id=4)
    setattr(project, inactive_field, datetime.now())
    project_session.add(project)
    project_session.commit()

    ensure_project_name_available(
        project_session,
        name="DevTrack",
        owner_id=5,
        organization_id=8,
    )

    project_session.add(
        Project(name="DevTrack", organization_id=8, owner_id=5)
    )
    project_session.commit()


def test_non_archived_status_values_still_reserve_the_name(project_session):
    project_session.add(
        Project(
            name="DevTrack",
            organization_id=8,
            owner_id=4,
            status="closed",
        )
    )
    project_session.commit()

    with pytest.raises(HTTPException) as error:
        ensure_project_name_available(
            project_session,
            name="DevTrack",
            owner_id=5,
            organization_id=8,
        )
    assert error.value.status_code == 409
