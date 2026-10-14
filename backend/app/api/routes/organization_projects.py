
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.organization import Organization
from app.models.organization_member import OrganizationMember
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.user import User
from app.schemas.organization_project import (
    OrganizationProjectCreate,
    OrganizationProjectResponse,
    OrganizationProjectUpdate,
)

router = APIRouter(
    prefix="/organizations/{organization_id}/projects",
    tags=["Organization Projects"],
)


def get_organization_access(
    organization_id: int,
    current_user: User,
    db: Session,
):
    organization = db.get(Organization, organization_id)

    if organization is None or organization.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organización no encontrada.",
        )

    membership = db.get(
        OrganizationMember,
        (organization_id, current_user.id),
    )

    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No perteneces a esta organización.",
        )

    return organization, membership


def get_project_access(
    organization_id: int,
    project_id: int,
    current_user: User,
    db: Session,
):
    get_organization_access(organization_id, current_user, db)

    project = db.get(Project, project_id)

    if (
        project is None
        or project.organization_id != organization_id
        or project.deleted_at is not None
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proyecto no encontrado.",
        )

    return project


def require_project_manager(
    project: Project,
    organization_membership: OrganizationMember,
    current_user: User,
):
    if (
        current_user.id != project.owner_id
        and organization_membership.role not in ("owner", "admin")
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para modificar este proyecto.",
        )


@router.post(
    "/",
    response_model=OrganizationProjectResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_project(
    organization_id: int,
    project_data: OrganizationProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    get_organization_access(organization_id, current_user, db)

    project = Project(
        name=project_data.name,
        description=project_data.description,
        organization_id=organization_id,
        owner_id=current_user.id,
    )

    try:
        db.add(project)
        db.flush()

        project_membership = ProjectMember(
            project_id=project.id,
            user_id=current_user.id,
            role="owner",
        )
        db.add(project_membership)

        db.commit()
        db.refresh(project)
        return project

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No se pudo crear el proyecto.",
        )


@router.get(
    "/",
    response_model=list[OrganizationProjectResponse],
)
def list_projects(
    organization_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    get_organization_access(organization_id, current_user, db)

    statement = (
        select(Project)
        .where(
            Project.organization_id == organization_id,
            Project.deleted_at.is_(None),
        )
        .order_by(Project.created_at.desc())
    )

    return list(db.scalars(statement).all())


@router.get(
    "/{project_id}",
    response_model=OrganizationProjectResponse,
)
def get_project(
    organization_id: int,
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_project_access(
        organization_id, project_id, current_user, db
    )


@router.patch(
    "/{project_id}",
    response_model=OrganizationProjectResponse,
)
def update_project(
    organization_id: int,
    project_id: int,
    project_data: OrganizationProjectUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = get_project_access(
        organization_id, project_id, current_user, db
    )
    _, organization_membership = get_organization_access(
        organization_id, current_user, db
    )
    require_project_manager(
        project, organization_membership, current_user
    )

    if project.archived_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No se puede modificar un proyecto archivado.",
        )

    changes = project_data.model_dump(exclude_unset=True)

    if not changes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Debes indicar al menos un campo para actualizar.",
        )

    for field, value in changes.items():
        setattr(project, field, value)

    db.commit()
    db.refresh(project)
    return project


@router.post(
    "/{project_id}/archive",
    response_model=OrganizationProjectResponse,
)
def archive_project(
    organization_id: int,
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = get_project_access(
        organization_id, project_id, current_user, db
    )
    _, organization_membership = get_organization_access(
        organization_id, current_user, db
    )
    require_project_manager(
        project, organization_membership, current_user
    )

    if project.archived_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El proyecto ya está archivado.",
        )

    project.archived_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(project)
    return project
