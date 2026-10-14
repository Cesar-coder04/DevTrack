
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.models.user_session import UserSession
from app.schemas.user_session import UserSessionResponse


router = APIRouter(
    prefix="/users/me/sessions",
    tags=["User sessions"],
)


@router.get("/", response_model=list[UserSessionResponse])
def list_sessions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = (
        select(UserSession)
        .where(UserSession.user_id == current_user.id)
        .order_by(UserSession.created_at.desc())
    )

    return db.scalars(query).all()


@router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def revoke_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = db.scalar(
        select(UserSession).where(
            UserSession.id == session_id,
            UserSession.user_id == current_user.id,
        )
    )

    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sesión no encontrada.",
        )

    if session.revoked_at is None:
        session.revoked_at = datetime.now(timezone.utc)
        db.commit()
