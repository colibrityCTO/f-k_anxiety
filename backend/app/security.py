"""Hachage de mot de passe (bcrypt) et jetons d'accès (JWT HS256)."""

from __future__ import annotations

import datetime as dt
from typing import Any

import bcrypt
import jwt

from .config import settings

# bcrypt ignore silencieusement les octets au-delà de 72 : on refuse plutôt que
# de tronquer, pour ne pas créer de faux sentiment de robustesse.
MAX_PASSWORD_BYTES = 72


class PasswordTooLong(ValueError):
    pass


def hash_password(password: str) -> str:
    raw = password.encode("utf-8")
    if len(raw) > MAX_PASSWORD_BYTES:
        raise PasswordTooLong(
            f"Le mot de passe ne doit pas dépasser {MAX_PASSWORD_BYTES} octets."
        )
    return bcrypt.hashpw(raw, bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    raw = password.encode("utf-8")
    if len(raw) > MAX_PASSWORD_BYTES:
        return False
    try:
        return bcrypt.checkpw(raw, password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: str, email: str) -> tuple[str, int]:
    """Retourne (jeton, durée de validité en secondes)."""
    expires_in = settings.access_token_expire_minutes * 60
    now = dt.datetime.now(dt.timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "email": email,
        "iat": int(now.timestamp()),
        "exp": int((now + dt.timedelta(seconds=expires_in)).timestamp()),
        "typ": "access",
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, expires_in


def decode_token(token: str) -> dict[str, Any]:
    """Lève jwt.PyJWTError si le jeton est invalide ou expiré."""
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
