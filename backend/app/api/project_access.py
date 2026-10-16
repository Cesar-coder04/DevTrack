from fastapi import HTTPException, status
from sqlalchemy.orm import Session

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
