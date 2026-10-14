
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.organization_member import OrganizationMember
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.user import User
from app.schemas.project_member import (
    ProjectMemberCreate,
    ProjectMemberResponse,
    ProjectMemberRoleUpdate,
)

router = APIRouter(
    prefix="/projects/{project_id}/members",
    tags=["Project Members"],
)


def get_project_and_access(
    project_id: int,
    current_user: User,
    db: Session,
):
    project = db.get(Project, project_id)

    if project is None or project.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proyecto no encontrado.",
        )

    organization_membership = db.get(
        OrganizationMember,
        (project.organization_id, current_user.id),
    )

    if organization_membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No perteneces a la organización de este proyecto.",
        )

    project_membership = db.get(
        ProjectMember,
        (project_id, current_user.id),
    )

    return project, organization_membership, project_membership


def require_project_manager(
    organization_role: str,
    project_role: str | None,
):
    if organization_role not in ("owner", "admin") and project_role not in (
        "owner",
        "admin",
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para gestionar los miembros.",
        )


@router.get("/", response_model=list[ProjectMemberResponse])
def list_project_members(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    get_project_and_access(project_id, current_user, db)

    statement = (
        select(ProjectMember, User)
        .join(User, User.id == ProjectMember.user_id)
        .where(ProjectMember.project_id == project_id)
        .order_by(ProjectMember.user_id)
    )

    results = db.execute(statement).all()

    return [
        ProjectMemberResponse(
            project_id=project_id,
            user_id=user.id,
            username=user.username,
            display_name=user.display_name,
            role=membership.role,
        )
        for membership, user in results
    ]


@router.post(
    "/",
    response_model=ProjectMemberResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_project_member(
    project_id: int,
    member_data: ProjectMemberCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project, organization_membership, current_project_membership = (
        get_project_and_access(project_id, current_user, db)
    )

    require_project_manager(
        organization_membership.role,
        current_project_membership.role if current_project_membership else None,
    )

    if project.archived_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No se pueden añadir miembros a un proyecto archivado.",
        )

    target_user = db.scalar(
        select(User).where(User.username == member_data.username)
    )

    if target_user is None or not target_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado o inactivo.",
        )

    target_organization_membership = db.get(
        OrganizationMember,
        (project.organization_id, target_user.id),
    )

    if target_organization_membership is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El usuario debe pertenecer primero a la organización.",
        )

    existing_membership = db.get(
        ProjectMember,
        (project_id, target_user.id),
    )

    if existing_membership is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El usuario ya pertenece al proyecto.",
        )

    if target_user.id == project.owner_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El propietario ya pertenece al proyecto.",
        )

    membership = ProjectMember(
        project_id=project_id,
        user_id=target_user.id,
        role=member_data.role,
    )

    try:
        db.add(membership)
        db.commit()
        db.refresh(membership)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No se pudo añadir al usuario al proyecto.",
        )

    return ProjectMemberResponse(
        project_id=project_id,
        user_id=target_user.id,
        username=target_user.username,
        display_name=target_user.display_name,
        role=membership.role,
    )


@router.patch("/{user_id}", response_model=ProjectMemberResponse)
def update_project_member_role(
    project_id: int,
    user_id: int,
    role_data: ProjectMemberRoleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project, organization_membership, current_project_membership = (
        get_project_and_access(project_id, current_user, db)
    )

    require_project_manager(
        organization_membership.role,
        current_project_membership.role if current_project_membership else None,
    )

    if project.archived_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No se pueden modificar miembros de un proyecto archivado.",
        )

    if user_id == project.owner_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No se puede cambiar el rol del propietario.",
        )

    target_membership = db.get(ProjectMember, (project_id, user_id))

    if target_membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El usuario no pertenece al proyecto.",
        )

    if (
        organization_membership.role == "admin"
        and target_membership.role == "admin"
        and current_project_membership is None
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No puedes modificar a este administrador.",
        )

    target_user = db.get(User, user_id)

    if target_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado.",
        )

    target_membership.role = role_data.role

    try:
        db.commit()
        db.refresh(target_membership)
    except Exception:
        db.rollback()
        raise

    db.commit()
    db.refresh(target_membership)

    return ProjectMemberResponse(
        project_id=project_id,
        user_id=target_user.id,
        username=target_user.username,
        display_name=target_user.display_name,
        role=target_membership.role,
    )


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_project_member(
    project_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project, organization_membership, current_project_membership = (
        get_project_and_access(project_id, current_user, db)
    )

    require_project_manager(
        organization_membership.role,
        current_project_membership.role if current_project_membership else None,
    )

    if project.archived_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No se pueden eliminar miembros de un proyecto archivado.",
        )

    if user_id == project.owner_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No se puede eliminar al propietario del proyecto.",
        )

    target_membership = db.get(ProjectMember, (project_id, user_id))

    if target_membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El usuario no pertenece al proyecto.",
        )

    if (
        organization_membership.role == "admin"
        and target_membership.role == "admin"
        and current_project_membership is None
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No puedes eliminar a este administrador.",
        )

    try:
        db.delete(target_membership)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return None
