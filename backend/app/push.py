"""Notifications push (Web Push / VAPID).

C'est la seule façon d'avoir un rappel fiable **application fermée** : un
`setTimeout` dans la page ne survit pas à la fermeture de l'onglet. Le service de
push du navigateur (FCM, Mozilla, Apple) réveille le service worker, qui affiche
la notification.

Sans paire de clés VAPID configurée, ce module ne fait rien et le dit — l'interface
retombe alors sur le rappel local, en annonçant sa limite.

Générer une paire :

    python -m app.vapid
"""

from __future__ import annotations

import json
import logging
from typing import Any

from . import db
from .config import settings

logger = logging.getLogger(__name__)

# Un abonnement révoqué renvoie 404 ou 410 : ce n'est pas une panne, c'est un
# appareil qui a désinstallé l'application ou révoqué l'autorisation.
GONE_STATUSES = {404, 410}


def available() -> bool:
    return settings.has_push


def public_key() -> str | None:
    return settings.vapid_public_key


def save_subscription(
    user_id: str, endpoint: str, p256dh: str, auth: str, user_agent: str | None = None
) -> dict[str, Any]:
    """Enregistre (ou réactive) un abonnement. Idempotent sur l'endpoint."""
    row = db.execute_returning(
        """
        INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth, user_agent)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (endpoint) DO UPDATE SET
            user_id = EXCLUDED.user_id,
            p256dh = EXCLUDED.p256dh,
            auth = EXCLUDED.auth,
            user_agent = EXCLUDED.user_agent,
            active = true,
            last_error = NULL
        RETURNING id::text, endpoint, active, created_at
        """,
        (user_id, endpoint, p256dh, auth, user_agent),
    )
    assert row is not None
    return row


def remove_subscription(user_id: str, endpoint: str) -> int:
    return db.execute(
        "DELETE FROM push_subscriptions WHERE user_id = %s AND endpoint = %s",
        (user_id, endpoint),
    )


def subscriptions(user_id: str, active_only: bool = True) -> list[dict[str, Any]]:
    return db.query_all(
        """
        SELECT id::text, endpoint, p256dh, auth, user_agent, active, last_error, last_sent_at
        FROM push_subscriptions
        WHERE user_id = %s AND (NOT %s OR active)
        ORDER BY created_at
        """,
        (user_id, active_only),
    )


def _disable(subscription_id: str, reason: str) -> None:
    db.execute(
        "UPDATE push_subscriptions SET active = false, last_error = %s WHERE id = %s",
        (reason[:300], subscription_id),
    )


def send_to_user(
    user_id: str, title: str, body: str, url: str = "/", tag: str = "fa"
) -> dict[str, int]:
    """Envoie à tous les appareils actifs. Retourne {envoyes, revoques, echecs}.

    Ne lève jamais : une notification perdue ne doit pas faire échouer le tic du
    planificateur ni une requête HTTP.
    """
    result = {"envoyes": 0, "revoques": 0, "echecs": 0}
    if not available():
        return result

    try:
        from pywebpush import WebPushException, webpush
    except ImportError:  # pragma: no cover - dépendance absente
        logger.error("pywebpush non installé : notifications désactivées")
        return result

    payload = json.dumps(
        {"title": title, "body": body, "url": url, "tag": tag}, ensure_ascii=False
    )

    for subscription in subscriptions(user_id):
        try:
            webpush(
                subscription_info={
                    "endpoint": subscription["endpoint"],
                    "keys": {"p256dh": subscription["p256dh"], "auth": subscription["auth"]},
                },
                data=payload,
                vapid_private_key=settings.vapid_private_key,
                vapid_claims={"sub": settings.vapid_subject},
                timeout=10,
            )
            db.execute(
                "UPDATE push_subscriptions SET last_sent_at = now(), last_error = NULL WHERE id = %s",
                (subscription["id"],),
            )
            result["envoyes"] += 1
        except WebPushException as exc:  # noqa: PERF203 - un échec par appareil
            status = getattr(exc.response, "status_code", None)
            if status in GONE_STATUSES:
                _disable(subscription["id"], f"révoqué ({status})")
                result["revoques"] += 1
            else:
                _disable(subscription["id"], str(exc))
                result["echecs"] += 1
                logger.warning("Push refusé (%s) : %s", status, exc)
        except Exception as exc:  # noqa: BLE001
            result["echecs"] += 1
            logger.warning("Push impossible : %s", exc)
    return result


# --- Réglage du rappel -------------------------------------------------------


def get_reminder(profile: dict[str, Any] | None) -> dict[str, Any]:
    reminder = (profile or {}).get("rappel") or {}
    return {
        "actif": bool(reminder.get("actif")),
        "heure": str(reminder.get("heure") or "21:00"),
    }


def set_reminder(user_id: str, enabled: bool, time_hhmm: str) -> dict[str, Any]:
    row = db.execute_returning(
        """
        UPDATE users
        SET profile = jsonb_set(
            COALESCE(profile, '{}'::jsonb), '{rappel}', %s::jsonb, true
        )
        WHERE id = %s
        RETURNING profile
        """,
        (json.dumps({"actif": enabled, "heure": time_hhmm}), user_id),
    )
    assert row is not None
    return get_reminder(row["profile"])
