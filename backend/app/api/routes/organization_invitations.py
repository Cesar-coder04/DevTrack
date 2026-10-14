
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.organization import Organization
from app.models.organization_invitation import OrganizationInvitation
from app.models.organization_member import OrganizationMember
from app.models.user import User
from app.schemas.organization_invitation import (
    OrganizationInvitationCreate,
    OrganizationInvitationResponse,
)


router = APIRouter(
    tags=["Organization invitations"],
)

def normalize_utc(value: datetime) -> datetime:
    """Interpreta como UTC las fechas sin zona horaria."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)

def get_manageable_organization(
    db: Session,
    organization_id: int,
    user_id: int,
) -> Organization:
    organization = db.get(Organization, organization_id)

    if organization is None or organization.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organización no encontrada.",
        )

    membership = db.get(
        OrganizationMember,
        (organization_id, user_id),
    )

    if membership is None or membership.role not in ("owner", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para gestionar invitaciones.",
        )

    return organization


@router.post(
    "/organizations/{organization_id}/invitations",
    response_model=OrganizationInvitationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_invitation(
    organization_id: int,
    data: OrganizationInvitationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    organization = get_manageable_organization(
        db, organization_id, current_user.id
    )

    invited_user = db.scalar(
        select(User).where(User.email == str(data.email))
    )

    if invited_user is None or not invited_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No existe un usuario activo con ese correo.",
        )

    if invited_user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes invitarte a ti mismo.",
        )

    existing_member = db.get(
        OrganizationMember,
        (organization.id, invited_user.id),
    )

    if existing_member is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El usuario ya pertenece a la organización.",
        )

    existing_invitation = db.scalar(
        select(OrganizationInvitation).where(
            OrganizationInvitation.organization_id == organization.id,
            OrganizationInvitation.email == str(data.email),
            OrganizationInvitation.status == "pending",
        )
    )

    if existing_invitation is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una invitación pendiente para ese correo.",
        )

    invitation = OrganizationInvitation(
        organization_id=organization.id,
        invited_by=current_user.id,
        email=str(data.email),
        role=data.role,
        token=uuid4().hex,
        status="pending",
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )

    try:
        db.add(invitation)
        db.commit()
        db.refresh(invitation)
    except Exception:
        db.rollback()
        raise

    return invitation


@router.get(
    "/organizations/{organization_id}/invitations",
    response_model=list[OrganizationInvitationResponse],
)
def list_organization_invitations(
    organization_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    get_manageable_organization(db, organization_id, current_user.id)

    query = (
        select(OrganizationInvitation)
        .where(OrganizationInvitation.organization_id == organization_id)
        .order_by(OrganizationInvitation.created_at.desc())
    )

    return db.scalars(query).all()


@router.get(
    "/users/me/invitations",
    response_model=list[OrganizationInvitationResponse],
)
def list_my_invitations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = (
        select(OrganizationInvitation)
        .where(
            OrganizationInvitation.email == current_user.email,
            OrganizationInvitation.status == "pending",
        )
        .order_by(OrganizationInvitation.created_at.desc())
    )

    return db.scalars(query).all()


@router.post("/users/me/invitations/{invitation_id}/accept")
def accept_invitation(
    invitation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    invitation = db.scalar(
        select(OrganizationInvitation).where(
            OrganizationInvitation.id == invitation_id,
            OrganizationInvitation.email == current_user.email,
            OrganizationInvitation.status == "pending",
        )
    )

    if invitation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitación pendiente no encontrada.",
        )

    organization = db.get(Organization, invitation.organization_id)

    if organization is None or organization.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="La organización no existe o ha sido eliminada.",
        )

    if normalize_utc(invitation.expires_at) <= datetime.now(timezone.utc):
        invitation.status = "expired"

        try:
            db.commit()
        except Exception:
            db.rollback()
            raise

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La invitación ha caducado.",
        )

    membership = db.get(
        OrganizationMember,
        (invitation.organization_id, current_user.id),
    )

    try:
        if membership is None:
            db.add(
                OrganizationMember(
                    organization_id=invitation.organization_id,
                    user_id=current_user.id,
                    role=invitation.role,
                )
            )

        invitation.status = "accepted"

        db.commit()
    except Exception:
        db.rollback()
        raise

    return {"message": "Invitación aceptada correctamente."}


@router.post("/users/me/invitations/{invitation_id}/reject")
def reject_invitation(
    invitation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    invitation = db.scalar(
        select(OrganizationInvitation).where(
            OrganizationInvitation.id == invitation_id,
            OrganizationInvitation.email == current_user.email,
            OrganizationInvitation.status == "pending",
        )
    )

    if invitation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitación pendiente no encontrada.",
        )

    invitation.status = "rejected"

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {"message": "Invitación rechazada correctamente."}
