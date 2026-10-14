
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.organization import Organization
from app.models.organization_member import OrganizationMember
from app.models.user import User
from app.schemas.organization import (
    OrganizationCreate,
    OrganizationResponse,
)

router = APIRouter(
    prefix="/organizations",
    tags=["Organizations"],
)


@router.post(
    "/",
    response_model=OrganizationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_organization(
    organization_data: OrganizationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    organization = Organization(
        name=organization_data.name,
        slug=organization_data.slug,
        description=organization_data.description,
        owner_id=current_user.id,
    )

    try:
        db.add(organization)
        db.flush()

        membership = OrganizationMember(
            organization_id=organization.id,
            user_id=current_user.id,
            role="owner",
        )
        db.add(membership)
        db.commit()
        db.refresh(organization)

        return organization

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No se pudo crear la organización por un conflicto de datos."
        )
    except Exception:
        db.rollback()
        raise


@router.get(
    "/",
    response_model=list[OrganizationResponse],
)
def list_organizations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    statement = (
        select(Organization)
        .join(
            OrganizationMember,
            OrganizationMember.organization_id == Organization.id,
        )
        .where(
            OrganizationMember.user_id == current_user.id,
            Organization.deleted_at.is_(None),
        )
        .order_by(Organization.created_at.desc())
    )

    return list(db.scalars(statement).all())
