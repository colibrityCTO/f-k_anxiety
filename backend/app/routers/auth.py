"""Inscription, connexion, profil. Seul router accessible sans jeton."""

from __future__ import annotations

import datetime as dt
import json
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr

from .. import db
from ..config import settings
from ..deps import CurrentUser
from ..program import ensure_state
from ..schemas import LoginIn, ProfileUpdateIn, RegisterIn, TokenOut, UserOut
from ..security import PasswordTooLong, create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


def _user_out(row: dict) -> UserOut:
    return UserOut(
        id=row["id"],
        email=row["email"],
        display_name=row.get("display_name"),
        timezone=row.get("timezone") or "Europe/Paris",
        ai_consent=bool(row.get("ai_consent")),
        profile=row.get("profile") or {},
        created_at=row.get("created_at"),
    )


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterIn) -> TokenOut:
    if not settings.allow_registration:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Les inscriptions sont fermées sur cette instance.",
        )
    email = payload.email.strip().lower()
    existing = db.query_one("SELECT 1 FROM users WHERE lower(email) = %s", (email,))
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Cette adresse est déjà utilisée."
        )
    try:
        password_hash = hash_password(payload.password)
    except PasswordTooLong as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    row = db.execute_returning(
        """
        INSERT INTO users (email, password_hash, display_name, timezone)
        VALUES (%s, %s, %s, %s)
        RETURNING id::text, email, display_name, timezone, profile, ai_consent, created_at
        """,
        (email, password_hash, payload.display_name, payload.timezone),
    )
    assert row is not None
    ensure_state(row["id"])

    token, expires_in = create_access_token(row["id"], row["email"])
    return TokenOut(access_token=token, expires_in=expires_in, user=_user_out(row))


@router.post("/login", response_model=TokenOut)
def login(payload: LoginIn) -> TokenOut:
    email = payload.email.strip().lower()
    row = db.query_one(
        """
        SELECT id::text, email, password_hash, display_name, timezone, profile,
               ai_consent, created_at
        FROM users WHERE lower(email) = %s
        """,
        (email,),
    )
    # Message identique dans les deux cas : ne pas révéler si le compte existe.
    invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Identifiants incorrects."
    )
    if row is None or not verify_password(payload.password, row["password_hash"]):
        raise invalid

    db.execute("UPDATE users SET last_login_at = now() WHERE id = %s", (row["id"],))
    ensure_state(row["id"])
    token, expires_in = create_access_token(row["id"], row["email"])
    return TokenOut(access_token=token, expires_in=expires_in, user=_user_out(row))


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return _user_out(user)


@router.get("/export")
def export_data(user: CurrentUser) -> dict[str, Any]:
    """Tout ce que le serveur sait de toi, en JSON.

    Sans condition et sans délai : ce sont tes données. Le fil, la mémoire (son
    texte) et les abonnements aux notifications sont inclus.
    """
    user_id = user["id"]
    tables = {
        "check_ins": "SELECT * FROM daily_checkins WHERE user_id = %s ORDER BY entry_date",
        "journal": "SELECT * FROM journal_entries WHERE user_id = %s ORDER BY entry_date",
        "echelles": "SELECT * FROM assessments WHERE user_id = %s ORDER BY taken_on",
        "activites": "SELECT * FROM activity_logs WHERE user_id = %s ORDER BY entry_date",
        "expositions": "SELECT * FROM exposure_items WHERE user_id = %s ORDER BY created_at",
        "analyses": "SELECT * FROM insights WHERE user_id = %s ORDER BY created_at",
        "fil": "SELECT * FROM thread_items WHERE user_id = %s ORDER BY seq",
        "programme": "SELECT * FROM program_state WHERE user_id = %s",
        "memoire": (
            "SELECT source_kind, source_id, entry_date, content, metadata, created_at "
            "FROM user_chunks WHERE user_id = %s ORDER BY id"
        ),
        "appareils": (
            "SELECT endpoint, user_agent, active, last_error, last_sent_at, created_at "
            "FROM push_subscriptions WHERE user_id = %s"
        ),
        "notifications_envoyees": (
            "SELECT kind, sent_on, detail, created_at FROM notification_log "
            "WHERE user_id = %s ORDER BY created_at"
        ),
    }
    data: dict[str, Any] = {
        "exporte_le": dt.datetime.now(dt.timezone.utc).isoformat(),
        "compte": {
            key: value
            for key, value in user.items()
            if key in {"id", "email", "display_name", "timezone", "ai_consent", "profile", "created_at"}
        },
        "note": (
            "Les vecteurs d'embedding ne sont pas exportés : 3072 nombres par entrée, illisibles, "
            "et reconstructibles à partir du texte."
        ),
    }
    for name, sql in tables.items():
        data[name] = db.query_all(sql, (user_id,))
    return data


class DeleteAccountIn(BaseModel):
    """La saisie de l'adresse évite la suppression par mégarde."""

    email: EmailStr


@router.post("/delete")
def delete_account(payload: DeleteAccountIn, user: CurrentUser) -> dict[str, Any]:
    """Supprime le compte et tout ce qui s'y rattache. Irréversible.

    Toutes les tables portent `ON DELETE CASCADE` sur `user_id` : une seule
    suppression emporte check-in, journal, échelles, expositions, fil, mémoire
    vectorisée et abonnements. Rien ne survit — c'est le but.
    """
    if payload.email.strip().lower() != str(user["email"]).lower():
        raise HTTPException(
            status_code=422,
            detail="L'adresse saisie ne correspond pas au compte : suppression annulée.",
        )

    counted: dict[str, int] = {}
    for name in (
        "daily_checkins", "journal_entries", "assessments", "activity_logs",
        "exposure_items", "insights", "thread_items", "user_chunks", "push_subscriptions",
    ):
        row = db.query_one(
            f"SELECT count(*) AS n FROM {name} WHERE user_id = %s",  # noqa: S608 - noms internes
            (user["id"],),
        )
        counted[name] = int(row["n"]) if row else 0

    deleted = db.execute("DELETE FROM users WHERE id = %s", (user["id"],))
    return {"supprime": bool(deleted), "lignes_effacees": counted}


@router.patch("/me", response_model=UserOut)
def update_me(payload: ProfileUpdateIn, user: CurrentUser) -> UserOut:
    fields: list[str] = []
    params: list[object] = []
    if payload.display_name is not None:
        fields.append("display_name = %s")
        params.append(payload.display_name)
    if payload.timezone is not None:
        fields.append("timezone = %s")
        params.append(payload.timezone)
    if payload.ai_consent is not None:
        fields.append("ai_consent = %s")
        params.append(payload.ai_consent)
    if payload.profile is not None:
        fields.append("profile = %s")
        params.append(json.dumps(payload.profile, ensure_ascii=False))
    if not fields:
        return _user_out(user)

    params.append(user["id"])
    row = db.execute_returning(
        f"""
        UPDATE users SET {", ".join(fields)} WHERE id = %s
        RETURNING id::text, email, display_name, timezone, profile, ai_consent, created_at
        """,  # noqa: S608 - les fragments proviennent d'une liste fermée ci-dessus
        params,
    )
    assert row is not None
    return _user_out(row)
