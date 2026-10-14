from datetime import datetime, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decode_access_token, hash_access_token
from app.db.session import get_db
from app.models.user import User
from app.models.user_session import UserSession

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")



def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudo validar la autenticación.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_access_token(token)
        user_id = int(payload.get("sub"))
    except (jwt.InvalidTokenError, ValueError, TypeError):
        raise credentials_exception

    session = db.scalar(
        select(UserSession).where(
            UserSession.token_hash == hash_access_token(token),
            UserSession.user_id == user_id,
        )
    )

    if session is None or session.revoked_at is not None:
        raise credentials_exception

    expires_at = session.expires_at

    # MySQL puede devolver los DateTime sin información de zona horaria.
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at <= datetime.now(timezone.utc):
        raise credentials_exception

    user = db.get(User, user_id)

    if user is None or not user.is_active:
        raise credentials_exception

    return user
