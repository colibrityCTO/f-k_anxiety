"""Planificateur : rappel quotidien et bilan hebdomadaire.

Une boucle asyncio démarrée avec l'application, qui se réveille chaque minute.
Trois précautions, chacune pour un problème réel :

1. **Verrou consultatif Postgres.** Avec plusieurs répliques, chaque instance
   ferait partir le même rappel. `pg_try_advisory_lock` garantit qu'une seule
   instance travaille par tic ; les autres passent leur tour sans attendre.
2. **Journal des notifications.** La contrainte d'unicité
   `(user_id, kind, sent_on)` rend l'envoi idempotent : même en cas de tic
   dupliqué ou de redémarrage, un rappel ne part qu'une fois par jour.
3. **Heure locale de chacun.** L'heure choisie est comparée dans le fuseau de
   l'utilisateur, pas dans celui du serveur — sinon un serveur en UTC enverrait
   les rappels à 23 h à Paris.

Le rappel ne part que si le check-in du jour manque : notifier quelqu'un qui a
déjà fait son suivi, c'est le dresser à ignorer les notifications.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import db, push
from .config import settings

logger = logging.getLogger(__name__)

# Identifiant arbitraire mais stable du verrou consultatif.
LOCK_KEY = 815_243_001

WEEKLY_WEEKDAY = 6  # dimanche
WEEKLY_HOUR = 20


def _zone(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or "Europe/Paris")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("Europe/Paris")


def _candidates() -> list[dict[str, Any]]:
    """Comptes ayant un rappel actif et au moins un appareil abonné."""
    return db.query_all(
        """
        SELECT u.id::text AS id, u.email, u.timezone, u.profile,
               u.profile->'rappel'->>'heure' AS heure
        FROM users u
        WHERE (u.profile->'rappel'->>'actif')::boolean IS TRUE
          AND EXISTS (
              SELECT 1 FROM push_subscriptions s WHERE s.user_id = u.id AND s.active
          )
        """
    )


def _already_sent(user_id: str, kind: str, day: dt.date) -> bool:
    row = db.query_one(
        "SELECT 1 FROM notification_log WHERE user_id = %s AND kind = %s AND sent_on = %s",
        (user_id, kind, day),
    )
    return row is not None


def _mark_sent(user_id: str, kind: str, day: dt.date, detail: dict[str, Any]) -> bool:
    """Réserve l'envoi. Retourne False si une autre instance l'a déjà fait."""
    import json

    row = db.execute_returning(
        """
        INSERT INTO notification_log (user_id, kind, sent_on, detail)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (user_id, kind, sent_on) DO NOTHING
        RETURNING id
        """,
        (user_id, kind, day, json.dumps(detail, ensure_ascii=False, default=str)),
    )
    return row is not None


def _checkin_missing(user_id: str, day: dt.date) -> bool:
    row = db.query_one(
        "SELECT 1 FROM daily_checkins WHERE user_id = %s AND entry_date = %s LIMIT 1",
        (user_id, day),
    )
    return row is None


def tick(now_utc: dt.datetime | None = None) -> dict[str, int]:
    """Un passage du planificateur. Synchrone : appelé dans un thread.

    Exposé publiquement pour être testable sans attendre l'heure réelle.
    """
    now_utc = now_utc or dt.datetime.now(dt.timezone.utc)
    stats = {"rappels": 0, "bilans": 0, "candidats": 0, "synchros": 0}

    with db.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_KEY,))
            acquired = bool(cur.fetchone()[0])
    if not acquired:
        return stats  # une autre instance s'en occupe

    try:
        # --- Rattrapage des bracelets ---------------------------------------
        #
        # Séparé de la boucle des rappels, et c'est nécessaire : `_candidates()` ne
        # renvoie que les comptes qui ont un rappel actif **et** un appareil abonné aux
        # notifications. Une synchronisation de bracelet n'a rien à voir avec ça — la
        # lier aux notifications aurait produit des comptes connectés à Whoop qui ne se
        # synchronisent jamais, sans que rien ne le signale.
        #
        # Les webhooks font le travail en temps normal ; ce rattrapage couvre ce qu'ils
        # perdent : serveur redémarré, notification jamais arrivée, connexion refaite.
        # Une fois par jour suffit, et le journal des notifications le rend idempotent.
        stats["synchros"] = _sync_wearables(now_utc)

        for user in _candidates():
            stats["candidats"] += 1
            local = now_utc.astimezone(_zone(user["timezone"]))
            today = local.date()
            hour, _, minute = (user["heure"] or "21:00").partition(":")

            # --- Rappel du check-in -----------------------------------------
            try:
                due = local.hour == int(hour) and local.minute >= int(minute or 0)
            except ValueError:
                due = False
            if due and not _already_sent(user["id"], "rappel_checkin", today):
                if _checkin_missing(user["id"], today) and _mark_sent(
                    user["id"], "rappel_checkin", today, {"heure_locale": local.isoformat()}
                ):
                    push.send_to_user(
                        user["id"],
                        "FUCK ANXIETY",
                        "T'as pas fait ton check-in aujourd'hui. Deux minutes.",
                        tag="fa-checkin",
                    )
                    stats["rappels"] += 1

            # --- Bilan hebdomadaire, dimanche soir --------------------------
            if (
                local.weekday() == WEEKLY_WEEKDAY
                and local.hour == WEEKLY_HOUR
                and not _already_sent(user["id"], "bilan_hebdo", today)
                and _mark_sent(user["id"], "bilan_hebdo", today, {})
            ):
                _push_weekly(user["id"])
                push.send_to_user(
                    user["id"],
                    "FUCK ANXIETY",
                    "Bilan de la semaine : il t'attend dans le fil.",
                    tag="fa-bilan",
                )
                stats["bilans"] += 1
    finally:
        with db.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))

    return stats


def _sync_wearables(now_utc: dt.datetime) -> int:
    """Resynchronise les bracelets connectés, au plus une fois par jour et par compte.

    Les erreurs sont consignées sur la connexion et n'interrompent pas la boucle : un
    jeton révoqué chez un utilisateur ne doit pas empêcher les dix-neuf autres de se
    synchroniser. C'est aussi pour ça que la marque de passage est posée **avant**
    l'appel — un service en incident ne doit pas être réinterrogé à chaque tic.
    """
    from .integrations import whoop

    done = 0
    rows = db.query_all(
        """
        SELECT t.user_id::text AS user_id, u.timezone
        FROM oauth_tokens t JOIN users u ON u.id = t.user_id
        WHERE t.provider = 'whoop'
        """
    )
    for row in rows:
        today = now_utc.astimezone(_zone(row["timezone"])).date()
        if _already_sent(row["user_id"], "synchro_bracelet", today):
            continue
        if not _mark_sent(row["user_id"], "synchro_bracelet", today, {}):
            continue
        try:
            counts = whoop.sync(row["user_id"], days=7)
            logger.info("Bracelet synchronisé pour %s : %s", row["user_id"], counts)
            done += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("Synchronisation bracelet impossible : %s", exc)
            db.execute(
                "UPDATE oauth_tokens SET last_error = %s WHERE user_id = %s AND provider = 'whoop'",
                (str(exc)[:400], row["user_id"]),
            )
    return done


def _push_weekly(user_id: str) -> None:
    """Dépose la proposition de bilan dans le fil.

    On dépose, on ne génère pas : l'analyse coûte un appel au modèle et se lance
    d'un clic. Le planificateur garantit la régularité, pas la dépense.
    """
    from .routers.chat import _items_from_decision

    _items_from_decision(
        user_id,
        {
            "reply": (
                "Bilan de la semaine. Je regarde les 4 dernières semaines : ce que les chiffres "
                "montrent, ce qui a été fait, ce qui ne l'a pas été et pourquoi."
            ),
            # Durable : la présence de ce widget dans le fil est ce qui empêche de
            # redéposer le bilan au tic suivant.
            "widget": {
                "type": "analysis",
                "prefill": {"scope": "hebdomadaire"},
                "a_verifier": [],
                "ephemeral": False,
            },
            "suggestions": ["Plus tard"],
            "engine": "local",
        },
    )


async def run_forever() -> None:
    """Boucle du planificateur, démarrée par le lifespan de l'application."""
    interval = max(20, settings.scheduler_interval_seconds)
    logger.info("Planificateur démarré (tic toutes les %s s)", interval)
    while True:
        try:
            stats = await asyncio.to_thread(tick)
            if stats["rappels"] or stats["bilans"]:
                logger.info("Planificateur : %s", stats)
        except asyncio.CancelledError:
            logger.info("Planificateur arrêté")
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("Tic du planificateur en échec : %s", exc)
        await asyncio.sleep(interval)
