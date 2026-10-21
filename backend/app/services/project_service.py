from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.project import Project


PROJECT_NAME_CONFLICT_DETAIL = (
    "Ya existe un proyecto no archivado ni eliminado con ese nombre "
    "en este ámbito."
)


def ensure_project_name_available(
    db: Session,
    *,
    name: str,
    owner_id: int,
    organization_id: int | None,
) -> None:
    conditions = [
        Project.name == name,
        Project.archived_at.is_(None),
        Project.deleted_at.is_(None),
    ]
    if organization_id is None:
        conditions.extend(
            [
                Project.organization_id.is_(None),
                Project.owner_id == owner_id,
            ]
        )
    else:
        conditions.append(Project.organization_id == organization_id)

    existing_project_id = db.scalar(
        select(Project.id).where(*conditions).limit(1)
    )
    if existing_project_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=PROJECT_NAME_CONFLICT_DETAIL,
        )


def is_project_name_unique_violation(error: IntegrityError) -> bool:
    message = str(error.orig).lower()
    return (
        "uq_projects_active_organization_name" in message
        or "uq_projects_active_personal_owner_name" in message
        or (
            "projects._active_organization_id" in message
            and "projects.name" in message
        )
        or (
            "projects._active_personal_owner_id" in message
            and "projects.name" in message
        )
    )
