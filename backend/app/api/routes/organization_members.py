
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.organization import Organization
from app.models.organization_member import OrganizationMember
from app.models.user import User
from app.schemas.organization_member import (
    OrganizationMemberCreate,
    OrganizationMemberResponse,
    OrganizationMemberRoleUpdate,
)

router = APIRouter(
    prefix="/organizations/{organization_id}/members",
    tags=["Organization Members"],
)


def get_organization_and_membership(
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


def require_manager(role: str):
    if role not in ("owner", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para gestionar miembros.",
        )


@router.get("/", response_model=list[OrganizationMemberResponse])
def list_members(
    organization_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    get_organization_and_membership(organization_id, current_user, db)

    statement = (
        select(OrganizationMember, User)
        .join(User, User.id == OrganizationMember.user_id)
        .where(OrganizationMember.organization_id == organization_id)
        .order_by(OrganizationMember.user_id)
    )

    results = db.execute(statement).all()

    return [
        OrganizationMemberResponse(
            user_id=user.id,
            username=user.username,
            display_name=user.display_name,
            role=membership.role,
            joined_at=getattr(membership, "created_at", None),
        )
        for membership, user in results
    ]


@router.post(
    "/",
    response_model=OrganizationMemberResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_member(
    organization_id: int,
    member_data: OrganizationMemberCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    organization, current_membership = get_organization_and_membership(
        organization_id, current_user, db
    )
    require_manager(current_membership.role)

    target_user = db.scalar(
        select(User).where(User.username == member_data.username)
    )

    if target_user is None or not target_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado o inactivo.",
        )

    existing_membership = db.get(
        OrganizationMember,
        (organization_id, target_user.id),
    )

    if existing_membership is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El usuario ya pertenece a esta organización.",
        )

    if target_user.id == organization.owner_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El propietario ya pertenece a la organización.",
        )

    membership = OrganizationMember(
        organization_id=organization_id,
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
            detail="No se pudo añadir al usuario; comprueba si ya pertenece a la organización.",
        )
    except Exception:
        db.rollback()
        raise

    return OrganizationMemberResponse(
        user_id=target_user.id,
        username=target_user.username,
        display_name=target_user.display_name,
        role=membership.role,
        joined_at=getattr(membership, "created_at", None),
    )


@router.patch("/{user_id}", response_model=OrganizationMemberResponse)
def update_member_role(
    organization_id: int,
    user_id: int,
    role_data: OrganizationMemberRoleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    organization, current_membership = get_organization_and_membership(
        organization_id, current_user, db
    )
    require_manager(current_membership.role)

    if user_id == organization.owner_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No se puede cambiar el rol del propietario.",
        )

    target_membership = db.get(
        OrganizationMember,
        (organization_id, user_id),
    )

    if target_membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El usuario no pertenece a esta organización.",
        )

    if current_membership.role == "admin" and role_data.role == "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Un administrador no puede asignar el rol de administrador.",
        )

    target_user = db.get(User, user_id)

    target_membership.role = role_data.role

    try:
        db.commit()
        db.refresh(target_membership)
    except Exception:
        db.rollback()
        raise

    return OrganizationMemberResponse(
        user_id=target_user.id,
        username=target_user.username,
        display_name=target_user.display_name,
        role=target_membership.role,
        joined_at=getattr(target_membership, "created_at", None),
    )


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    organization_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    organization, current_membership = get_organization_and_membership(
        organization_id, current_user, db
    )
    require_manager(current_membership.role)

    if user_id == organization.owner_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No se puede eliminar al propietario de la organización.",
        )

    target_membership = db.get(
        OrganizationMember,
        (organization_id, user_id),
    )

    if target_membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El usuario no pertenece a esta organización.",
        )

    if current_membership.role == "admin" and target_membership.role == "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Un administrador no puede eliminar a otro administrador.",
        )

    try:
        db.delete(target_membership)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return None
