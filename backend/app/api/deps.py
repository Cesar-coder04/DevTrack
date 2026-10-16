from datetime import datetime, timezone

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config
from app.core.security import decode_access_token, hash_access_token
from app.db.session import get_db
from app.models.user import User
from app.models.user_session import UserSession

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def get_current_user(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudo validar la autenticación.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    authorization = request.headers.get("authorization")
    if authorization is not None:
        if token is None:
            raise credentials_exception
        credential = token
    else:
        credential = request.cookies.get(config.SESSION_COOKIE_NAME)
        if credential is None:
            raise credentials_exception

        # This legacy GET creates the preference row when one does not exist.
        is_preferences_read_write = (
            request.method == "GET"
            and request.url.path.rstrip("/") == "/users/me/preferences"
        )
        if (
            request.method.upper() not in {"GET", "HEAD", "OPTIONS"}
            or is_preferences_read_write
        ) and not config.is_trusted_web_origin(request.headers.get("origin")):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="El origen de la solicitud no está permitido.",
            )

    try:
        payload = decode_access_token(credential)
        user_id = int(payload.get("sub"))
    except (jwt.InvalidTokenError, ValueError, TypeError):
        raise credentials_exception

    session = db.scalar(
        select(UserSession).where(
            UserSession.token_hash == hash_access_token(credential),
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
