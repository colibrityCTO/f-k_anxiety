"""Abonnements push et réglage du rappel quotidien."""

from __future__ import annotations

import datetime as dt
import re
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import db, push, scheduler
from ..deps import CurrentUser

router = APIRouter(prefix="/push", tags=["push"])

HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


class SubscriptionIn(BaseModel):
    endpoint: str = Field(min_length=12, max_length=2000)
    p256dh: str = Field(min_length=8, max_length=500)
    auth: str = Field(min_length=4, max_length=200)
    user_agent: str | None = Field(default=None, max_length=300)


class ReminderIn(BaseModel):
    enabled: bool
    time: str = Field(default="21:00")


@router.get("/key")
def key(user: CurrentUser) -> dict[str, Any]:
    """Clé publique VAPID et état du service. Sans clé, le push est impossible."""
    return {
        "disponible": push.available(),
        "cle_publique": push.public_key(),
        "rappel": push.get_reminder(user.get("profile")),
        "appareils": [
            {
                "endpoint": row["endpoint"][:60] + "…",
                "user_agent": row["user_agent"],
                "actif": row["active"],
                "dernier_envoi": row["last_sent_at"],
                "derniere_erreur": row["last_error"],
            }
            for row in push.subscriptions(user["id"], active_only=False)
        ],
        "explication": (
            "Le rappel est envoyé par le service de push du navigateur, qui réveille "
            "l'application même fermée. Il ne part que si le check-in du jour manque encore."
            if push.available()
            else "Aucune paire de clés VAPID configurée sur ce serveur : le push est indisponible. "
            "Génère-la avec « python -m app.vapid » et redémarre."
        ),
    }


@router.post("/subscribe")
def subscribe(payload: SubscriptionIn, user: CurrentUser) -> dict[str, Any]:
    if not push.available():
        raise HTTPException(
            status_code=503,
            detail="Notifications indisponibles : aucune clé VAPID configurée sur ce serveur.",
        )
    saved = push.save_subscription(
        user["id"], payload.endpoint, payload.p256dh, payload.auth, payload.user_agent
    )
    return {"abonnement": saved, "rappel": push.get_reminder(user.get("profile"))}


@router.post("/unsubscribe")
def unsubscribe(payload: SubscriptionIn, user: CurrentUser) -> dict[str, int]:
    return {"supprimes": push.remove_subscription(user["id"], payload.endpoint)}


@router.post("/reminder")
def set_reminder(payload: ReminderIn, user: CurrentUser) -> dict[str, Any]:
    if not HHMM.match(payload.time):
        raise HTTPException(status_code=422, detail="Heure attendue au format HH:MM.")
    reminder = push.set_reminder(user["id"], payload.enabled, payload.time)
    return {
        "rappel": reminder,
        "fuseau": user.get("timezone"),
        "push_disponible": push.available(),
        "note": (
            "L'heure est interprétée dans ton fuseau, pas celui du serveur."
            if payload.enabled
            else "Rappel désactivé."
        ),
    }


@router.post("/test")
def test(user: CurrentUser) -> dict[str, Any]:
    """Envoie une notification de test tout de suite, pour vérifier la chaîne."""
    if not push.available():
        raise HTTPException(status_code=503, detail="Notifications indisponibles sur ce serveur.")
    if not push.subscriptions(user["id"]):
        raise HTTPException(status_code=422, detail="Aucun appareil abonné.")
    return push.send_to_user(
        user["id"], "FUCK ANXIETY", "Test : la chaîne de notification fonctionne.", tag="fa-test"
    )


@router.get("/status")
def status(user: CurrentUser) -> dict[str, Any]:
    """État du planificateur et des envois déjà faits — pour ne pas jouer aux devinettes."""
    return {
        "planificateur_actif": scheduler.settings.scheduler_enabled,
        "intervalle_s": scheduler.settings.scheduler_interval_seconds,
        "push_disponible": push.available(),
        "rappel": push.get_reminder(user.get("profile")),
        "envois_recents": db.query_all(
            """
            SELECT kind, sent_on, created_at FROM notification_log
            WHERE user_id = %s AND sent_on >= %s ORDER BY created_at DESC LIMIT 20
            """,
            (user["id"], dt.date.today() - dt.timedelta(days=30)),
        ),
    }
