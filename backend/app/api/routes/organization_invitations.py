import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.security import hash_access_token
from app.db.session import get_db
from app.models.organization import Organization
from app.models.organization_invitation import OrganizationInvitation
from app.models.organization_member import OrganizationMember
from app.models.user import User
from app.schemas.organization_invitation import (
    OrganizationInvitationCreate,
    OrganizationInvitationResponse,
    OrganizationInvitationToken,
)
from app.services.email_service import (
    EmailDeliveryError,
    build_invitation_url,
    send_invitation_email,
)

router = APIRouter(
    tags=["Organization invitations"],
)


def normalize_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def normalize_email(value: str) -> str:
    return value.strip().casefold()


def get_manageable_organization(
    db: Session,
    organization_id: int,
    user_id: int,
    *,
    lock: bool = False,
) -> Organization:
    organization_query = select(Organization).where(
        Organization.id == organization_id
    )
    membership_query = select(OrganizationMember).where(
        OrganizationMember.organization_id == organization_id,
        OrganizationMember.user_id == user_id,
    )
    if lock:
        organization_query = organization_query.execution_options(
            populate_existing=True
        ).with_for_update()
        membership_query = membership_query.execution_options(
            populate_existing=True
        ).with_for_update()

    organization = db.scalar(organization_query)
    if organization is None or organization.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organización no encontrada.",
        )

    membership = db.scalar(membership_query)
    if membership is None or membership.role not in ("owner", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para gestionar invitaciones.",
        )

    return organization


def get_invitation_for_update(
    db: Session,
    invitation_id: int,
) -> OrganizationInvitation | None:
    return db.scalar(
        select(OrganizationInvitation)
        .where(OrganizationInvitation.id == invitation_id)
        .execution_options(populate_existing=True)
        .with_for_update()
    )


def get_organization_member_for_update(
    db: Session,
    organization_id: int,
    user_id: int,
) -> OrganizationMember | None:
    return db.scalar(
        select(OrganizationMember)
        .where(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.user_id == user_id,
        )
        .execution_options(populate_existing=True)
        .with_for_update()
    )


def require_pending_invitation(
    invitation: OrganizationInvitation,
    *,
    expired_status: int = status.HTTP_400_BAD_REQUEST,
    expired_detail: str = "La invitación ha caducado.",
) -> None:
    if invitation.accepted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La invitación ya fue aceptada.",
        )
    if invitation.rejected_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La invitación ya fue rechazada.",
        )
    if invitation.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La invitación fue revocada.",
        )
    if normalize_utc(invitation.expires_at) <= datetime.now(timezone.utc):
        raise HTTPException(
            status_code=expired_status,
            detail=expired_detail,
        )


def validate_invitation_recipient_and_token(
    invitation: OrganizationInvitation,
    current_user: User,
    token: str,
) -> None:
    if normalize_email(invitation.email) != normalize_email(current_user.email):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitación no encontrada.",
        )

    if not secrets.compare_digest(
        invitation.token_hash,
        hash_access_token(token),
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitación no encontrada.",
        )


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
        db,
        organization_id,
        current_user.id,
        lock=True,
    )
    if data.role == "admin" and organization.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo el propietario puede invitar administradores.",
        )

    normalized_email = normalize_email(str(data.email))
    invited_user = db.scalar(
        select(User).where(func.lower(User.email) == normalized_email)
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
    if (
        get_organization_member_for_update(
            db,
            organization.id,
            invited_user.id,
        )
        is not None
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El usuario ya pertenece a la organización.",
        )

    now = datetime.now(timezone.utc)
    expiry = now + timedelta(days=7)
    pending_query = (
        select(OrganizationInvitation)
        .where(
            OrganizationInvitation.organization_id == organization.id,
            func.lower(OrganizationInvitation.email) == normalized_email,
            OrganizationInvitation.accepted_at.is_(None),
            OrganizationInvitation.rejected_at.is_(None),
            OrganizationInvitation.revoked_at.is_(None),
            OrganizationInvitation.expires_at > now,
        )
        .order_by(
            OrganizationInvitation.created_at.desc(),
            OrganizationInvitation.id.desc(),
        )
        .execution_options(populate_existing=True)
        .with_for_update()
    )
    pending_invitations = list(db.scalars(pending_query).all())
    invitation = pending_invitations[0] if pending_invitations else None

    token = secrets.token_urlsafe(32)
    token_hash = hash_access_token(token)
    if invitation is None:
        invitation = OrganizationInvitation(
            organization_id=organization.id,
            invited_by_id=current_user.id,
            email=normalized_email,
            role=data.role,
            token_hash=token_hash,
            expires_at=expiry,
        )
        db.add(invitation)
    else:
        for duplicate in pending_invitations[1:]:
            duplicate.revoked_at = now
        invitation.invited_by_id = current_user.id
        invitation.role = data.role
        invitation.token_hash = token_hash
        invitation.expires_at = expiry

    try:
        db.flush()
        db.refresh(invitation)
        response = OrganizationInvitationResponse.model_validate(invitation)
        invitation_id = invitation.id
        invitation_role = invitation.role
        invitation_expiry = normalize_utc(invitation.expires_at).isoformat()
        organization_name = organization.name
        invitation_url = build_invitation_url(invitation_id, token)
    except EmailDeliveryError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No se pudo preparar el enlace de invitación.",
        ) from None
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No se pudo crear o renovar la invitación.",
        ) from exc
    except Exception:
        db.rollback()
        raise

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No se pudo crear o renovar la invitación.",
        ) from exc
    except Exception:
        db.rollback()
        raise

    try:
        send_invitation_email(
            recipient=normalized_email,
            organization_name=organization_name,
            role=invitation_role,
            expires_at=invitation_expiry,
            invitation_url=invitation_url,
        )
    except EmailDeliveryError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "La invitación quedó guardada, pero no se pudo enviar el "
                "correo. Reintenta la creación para emitir un token nuevo."
            ),
        ) from None

    return response


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
    now = datetime.now(timezone.utc)
    query = (
        select(OrganizationInvitation)
        .where(
            func.lower(OrganizationInvitation.email)
            == normalize_email(current_user.email),
            OrganizationInvitation.accepted_at.is_(None),
            OrganizationInvitation.rejected_at.is_(None),
            OrganizationInvitation.revoked_at.is_(None),
            OrganizationInvitation.expires_at > now,
        )
        .order_by(OrganizationInvitation.created_at.desc())
    )
    return db.scalars(query).all()


@router.post("/users/me/invitations/{invitation_id}/accept")
def accept_invitation(
    invitation_id: int,
    data: OrganizationInvitationToken,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    invitation_reference = db.scalar(
        select(OrganizationInvitation).where(
            OrganizationInvitation.id == invitation_id
        )
    )
    if invitation_reference is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitación no encontrada.",
        )

    organization = db.scalar(
        select(Organization)
        .where(Organization.id == invitation_reference.organization_id)
        .execution_options(populate_existing=True)
        .with_for_update()
    )
    if organization is None or organization.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="La organización no existe o ha sido eliminada.",
        )

    existing_membership = get_organization_member_for_update(
        db,
        invitation_reference.organization_id,
        current_user.id,
    )
    invitation = db.scalar(
        select(OrganizationInvitation)
        .where(
            OrganizationInvitation.id == invitation_id,
            OrganizationInvitation.organization_id
            == invitation_reference.organization_id,
        )
        .execution_options(populate_existing=True)
        .with_for_update()
    )
    if invitation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitación no encontrada.",
        )
    validate_invitation_recipient_and_token(invitation, current_user, data.token)
    require_pending_invitation(invitation)

    if existing_membership is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El usuario ya pertenece a la organización.",
        )

    try:
        db.add(
            OrganizationMember(
                organization_id=invitation.organization_id,
                user_id=current_user.id,
                role=invitation.role,
            )
        )
        invitation.accepted_at = datetime.now(timezone.utc)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La invitación ya fue procesada.",
        ) from exc
    except Exception:
        db.rollback()
        raise

    return {"message": "Invitación aceptada correctamente."}


@router.post("/users/me/invitations/{invitation_id}/reject")
def reject_invitation(
    invitation_id: int,
    data: OrganizationInvitationToken,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    invitation = get_invitation_for_update(db, invitation_id)
    if invitation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitación no encontrada.",
        )
    validate_invitation_recipient_and_token(invitation, current_user, data.token)
    require_pending_invitation(invitation)

    invitation.rejected_at = datetime.now(timezone.utc)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {"message": "Invitación rechazada correctamente."}


@router.post(
    "/organizations/{organization_id}/invitations/{invitation_id}/revoke",
)
def revoke_invitation(
    organization_id: int,
    invitation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    get_manageable_organization(
        db,
        organization_id,
        current_user.id,
        lock=True,
    )
    invitation = db.scalar(
        select(OrganizationInvitation)
        .where(
            OrganizationInvitation.id == invitation_id,
            OrganizationInvitation.organization_id == organization_id,
        )
        .execution_options(populate_existing=True)
        .with_for_update()
    )
    if invitation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitación no encontrada.",
        )
    require_pending_invitation(
        invitation,
        expired_status=status.HTTP_409_CONFLICT,
        expired_detail="No se puede revocar una invitación caducada.",
    )

    invitation.revoked_at = datetime.now(timezone.utc)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {"message": "Invitación revocada correctamente."}
