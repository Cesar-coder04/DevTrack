
import hashlib
from datetime import datetime, timedelta, timezone

import jwt
from pwdlib import PasswordHash

from app.config import JWT_SECRET_KEY

password_hash = PasswordHash.recommended()


def hash_access_token(token: str) -> str:
    """Genera el hash SHA-256 de un token de acceso."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    """Genera un hash seguro de una contraseña."""
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    """Comprueba una contraseña frente a su hash."""
    return password_hash.verify(password, hashed_password)


def create_access_token(
    subject: str,
    expires_delta: timedelta = timedelta(minutes=30),
) -> tuple[str, datetime]:
    """Genera un JWT y devuelve también su fecha de expiración."""
    if not JWT_SECRET_KEY:
        raise RuntimeError(
            "Falta configurar JWT_SECRET_KEY en backend/.env."
        )

    now = datetime.now(timezone.utc)
    expires_at = now + expires_delta

    payload = {
        "sub": subject,
        "iat": now,
        "exp": expires_at,
    }

    token = jwt.encode(
        payload,
        JWT_SECRET_KEY,
        algorithm="HS256",
    )

    return token, expires_at


def decode_access_token(token: str) -> dict:
    """Valida un token JWT y devuelve su contenido."""
    if not JWT_SECRET_KEY:
        raise RuntimeError(
            "Falta configurar JWT_SECRET_KEY en backend/.env."
        )

    return jwt.decode(
        token,
        JWT_SECRET_KEY,
        algorithms=["HS256"],
    )
