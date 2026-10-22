from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.organization import Organization
from app.models.organization_member import OrganizationMember
from app.models.project import Project


def require_project_organization_membership(
    db: Session,
    project: Project,
    user_id: int,
    *,
    allow_unorganized: bool = True,
    detail: str = "No perteneces a la organización.",
) -> OrganizationMember | None:
    if project.organization_id is None:
        if allow_unorganized:
            return None
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
        )

    organization = db.get(Organization, project.organization_id)
    if organization is None or organization.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organizaci\u00f3n no encontrada.",
        )

    membership = db.get(
        OrganizationMember,
        (project.organization_id, user_id),
    )
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
        )

    return membership
