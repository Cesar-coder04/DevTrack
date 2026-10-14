
from datetime import datetime, timedelta, timezone

import jwt
from pwdlib import PasswordHash

from app.config import JWT_SECRET_KEY

password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """Genera un hash seguro de una contraseña."""
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    """Comprueba una contraseña frente a su hash."""
    return password_hash.verify(password, hashed_password)


def create_access_token(subject: str) -> str:
    """Genera un token JWT válido durante 30 minutos."""
    if not JWT_SECRET_KEY:
        raise RuntimeError("Falta configurar JWT_SECRET_KEY en backend/.env.")

    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "iat": now,
        "exp": now + timedelta(minutes=30),
    }

    return jwt.encode(payload, JWT_SECRET_KEY, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    """Valida un token JWT y devuelve su contenido."""
    if not JWT_SECRET_KEY:
        raise RuntimeError("Falta configurar JWT_SECRET_KEY en backend/.env.")

    return jwt.decode(
        token,
        JWT_SECRET_KEY,
        algorithms=["HS256"],
    )
