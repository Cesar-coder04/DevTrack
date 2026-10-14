from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import (
    create_access_token,
    hash_access_token,
    verify_password,
)
from app.db.session import get_db
from app.models.user_session import UserSession
from app.schemas.user import TokenResponse, UserCreate, UserResponse
from app.services.user_service import (
    create_user,
    get_user_by_email,
    get_user_by_username,
)


router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_user(
    user_data: UserCreate,
    db: Session = Depends(get_db),
):
    if get_user_by_username(db, user_data.username):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El nombre de usuario ya está en uso.",
        )

    if get_user_by_email(db, str(user_data.email)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El correo electrónico ya está registrado.",
        )

    try:
        return create_user(db, user_data)
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No se pudo registrar el usuario por un conflicto de datos.",
        )




@router.post("/login", response_model=TokenResponse)
def login_user(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = get_user_by_username(db, form_data.username)

    if not user or not verify_password(
        form_data.password,
        user.password_hash,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="La cuenta está desactivada.",
        )

    token, expires_at = create_access_token(str(user.id))

    session = UserSession(
        user_id=user.id,
        token_hash=hash_access_token(token),
        expires_at=expires_at,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
    )

    try:
        db.add(session)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "access_token": token,
        "token_type": "bearer",
    }
