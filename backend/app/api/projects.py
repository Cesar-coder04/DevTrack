
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.user import User
from app.schemas.project import ProjectCreate, ProjectResponse
from app.services.project_service import (
    PROJECT_NAME_CONFLICT_DETAIL,
    ensure_project_name_available,
    is_project_name_unique_violation,
)


router = APIRouter(
    prefix="/projects",
    tags=["Projects"],
)


@router.get("/", response_model=list[ProjectResponse])
def list_projects(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = (
        select(Project)
        .join(ProjectMember, ProjectMember.project_id == Project.id)
        .where(
            ProjectMember.user_id == user.id,
            Project.organization_id.is_(None),
            Project.archived_at.is_(None),
            Project.deleted_at.is_(None),
        )
    )

    return db.scalars(query).all()


@router.post(
    "/",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_project(
    project: ProjectCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        ensure_project_name_available(
            db,
            name=project.name,
            owner_id=user.id,
            organization_id=None,
        )
        db_project = Project(
            **project.model_dump(),
            owner_id=user.id,
        )
        db.add(db_project)
        db.flush()

        membership = ProjectMember(
            project_id=db_project.id,
            user_id=user.id,
            role="owner",
        )
        db.add(membership)

        db.commit()
        db.refresh(db_project)

        return db_project

    except IntegrityError as exc:
        db.rollback()
        if is_project_name_unique_violation(exc):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=PROJECT_NAME_CONFLICT_DETAIL,
            ) from None
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ha ocurrido un error al crear el proyecto.",
        ) from None
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ha ocurrido un error al crear el proyecto.",
        ) from None
