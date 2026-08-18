"""Dépendances FastAPI : authentification obligatoire sur tout le reste de l'API."""

from __future__ import annotations

from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import db
from .security import decode_token

bearer_scheme = HTTPBearer(auto_error=False, description="Jeton JWT d'accès")

_CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Authentification requise.",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> dict[str, Any]:
    if creds is None or not creds.credentials:
        raise _CREDENTIALS_ERROR
    try:
        payload = decode_token(creds.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expirée, reconnectez-vous.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    except jwt.PyJWTError:
        raise _CREDENTIALS_ERROR from None

    user_id = payload.get("sub")
    if not user_id:
        raise _CREDENTIALS_ERROR

    user = db.query_one(
        """
        SELECT id::text, email, display_name, timezone, profile, ai_consent, created_at
        FROM users WHERE id = %s
        """,
        (user_id,),
    )
    if user is None:
        raise _CREDENTIALS_ERROR
    return user


CurrentUser = Annotated[dict[str, Any], Depends(get_current_user)]
