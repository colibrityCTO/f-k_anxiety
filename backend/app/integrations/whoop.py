"""Intégration Whoop — API v2.

## Ce que cette source permet, et ce qu'elle ne permettra jamais

L'API v2 expose des **agrégats** : variabilité cardiaque et fréquence cardiaque de
repos par récupération, stades et efficacité par sommeil, charge et fréquence
cardiaque moyenne / maximale par cycle, et par séance la fréquence maximale plus le
temps passé dans chaque zone.

Elle n'expose **aucune série temporelle de fréquence cardiaque**. Ni à la seconde,
ni à la minute. Deux conséquences, et il faut les tenir toutes les deux :

- ✅ « Il a fait une séance, son cœur est monté au-dessus de 150, et il a noté une
  crise le lendemain » est calculable — `max_heart_rate` et `zone_durations` d'une
  séance suffisent, croisés avec `panic_episodes`. C'est l'hypothèse
  pré-enregistrée `anxiete_haute_et_sport_intense`.
- ❌ **Détecter une crise nous-mêmes est hors de portée.** Repérer un pic autonome de
  dix à vingt minutes demande la fréquence cardiaque à la minute. Les travaux qui y
  parviennent utilisent de l'ECG à 500 Hz ou des capteurs de recherche, sans
  validation externe et avec un fort déséquilibre de classes.

Et une raison de ne pas contourner la limite même si on pouvait : **une fausse
alerte de panique est un déclencheur de panique.** Ce module ne produit donc aucune
alerte d'épisode. Il alimente les signaux journaliers et une invite contextuelle
après une séance intense — ce qui est utile et ne peut pas se retourner contre
l'utilisateur.

## Choix d'implémentation

`httpx` en synchrone dans un thread plutôt qu'en asynchrone : le reste du projet
appelle la base en synchrone via un pool threadé, et mélanger les deux styles pour
gagner quelques millisecondes sur une synchronisation quotidienne n'en vaut pas la
peine.

La pagination est bornée (`MAX_PAGES`) : sans borne, un `next_token` renvoyé en
boucle par un service en incident ferait tourner la synchronisation indéfiniment.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import logging
import secrets
from typing import Any

import httpx

from .. import crypto, db
from ..config import settings

logger = logging.getLogger(__name__)

PROVIDER = "whoop"

AUTHORIZE_URL = "https://api.prod.whoop.com/oauth/oauth2/auth"
TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"
API_BASE = "https://api.prod.whoop.com/developer"

# `offline` est ce qui délivre un jeton de rafraîchissement. Sans lui, l'accès expire
# au bout d'une heure et l'utilisateur devrait se reconnecter chaque jour — donc ne le
# ferait pas.
SCOPES = [
    "offline",
    "read:recovery",
    "read:cycles",
    "read:sleep",
    "read:workout",
    "read:body_measurement",
]

# L'API plafonne `limit` à 25 : demander plus est refusé, pas tronqué.
PAGE_SIZE = 25
MAX_PAGES = 40

# Au-delà de ce maximum de fréquence cardiaque sur une séance, l'application demande
# le lendemain comment ça s'est passé. Ce n'est pas une alerte et ce n'est pas une
# prédiction : c'est une question. Le seuil est volontairement grossier — il sera
# remplacé par un percentile personnel dès qu'il y aura assez de séances.
INTENSE_HR_THRESHOLD = 150


class WhoopError(RuntimeError):
    """Erreur d'intégration destinée à être montrée à l'utilisateur."""


# --- OAuth ------------------------------------------------------------------


def authorize_url(state: str) -> str:
    """URL d'autorisation. `state` protège du CSRF et doit être vérifié au retour."""
    if not settings.has_whoop:
        raise WhoopError("L'intégration Whoop n'est pas configurée sur ce serveur.")
    params = {
        "response_type": "code",
        "client_id": settings.whoop_client_id or "",
        "redirect_uri": settings.whoop_redirect_uri or "",
        "scope": " ".join(SCOPES),
        "state": state,
    }
    return AUTHORIZE_URL + "?" + httpx.QueryParams(params).__str__()


def new_state() -> str:
    return secrets.token_urlsafe(24)


def _token_request(payload: dict[str, str]) -> dict[str, Any]:
    with httpx.Client(timeout=20.0) as client:
        response = client.post(TOKEN_URL, data=payload)
    if response.status_code >= 400:
        logger.warning("Whoop a refusé l'échange de jeton : %s", response.text[:300])
        raise WhoopError(
            "Whoop a refusé la connexion. Vérifie que l'URL de redirection déclarée "
            "correspond exactement à celle configurée ici."
        )
    return response.json()


def exchange_code(code: str) -> dict[str, Any]:
    return _token_request(
        {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": settings.whoop_client_id or "",
            "client_secret": settings.whoop_client_secret or "",
            "redirect_uri": settings.whoop_redirect_uri or "",
        }
    )


def refresh(refresh_token: str) -> dict[str, Any]:
    # `scope=offline` est requis au rafraîchissement, sinon le nouveau jeton revient
    # sans jeton de rafraîchissement et la connexion meurt silencieusement au bout
    # d'une heure.
    return _token_request(
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": settings.whoop_client_id or "",
            "client_secret": settings.whoop_client_secret or "",
            "scope": "offline",
        }
    )


# --- Stockage des jetons ----------------------------------------------------


def save_tokens(
    user_id: str, payload: dict[str, Any], provider_user_id: str | None = None
) -> None:
    """Enregistre les jetons, chiffrés. Conserve l'ancien rafraîchissement si absent.

    Whoop ne renvoie pas toujours un nouveau `refresh_token` : le `coalesce` évite de
    remplacer un jeton valide par `NULL`, ce qui déconnecterait l'utilisateur au
    prochain rafraîchissement.
    """
    expires_in = int(payload.get("expires_in") or 3600)
    db.execute(
        """
        INSERT INTO oauth_tokens
            (user_id, provider, provider_user_id, access_token, refresh_token, scopes,
             expires_at)
        VALUES (%(user_id)s, %(provider)s, %(provider_user_id)s, %(access)s, %(refresh)s,
                %(scopes)s, now() + (%(expires)s || ' seconds')::interval)
        ON CONFLICT (user_id, provider) DO UPDATE SET
            provider_user_id = coalesce(EXCLUDED.provider_user_id, oauth_tokens.provider_user_id),
            access_token = EXCLUDED.access_token,
            refresh_token = coalesce(EXCLUDED.refresh_token, oauth_tokens.refresh_token),
            scopes = EXCLUDED.scopes,
            expires_at = EXCLUDED.expires_at,
            last_error = NULL,
            updated_at = now()
        """,
        {
            "user_id": user_id,
            "provider": PROVIDER,
            "provider_user_id": provider_user_id,
            "access": crypto.seal(str(payload["access_token"])),
            "refresh": crypto.seal(str(payload["refresh_token"])) if payload.get("refresh_token") else None,
            "scopes": (payload.get("scope") or "").split(),
            "expires": expires_in,
        },
    )


def connection(user_id: str) -> dict[str, Any] | None:
    return db.query_one(
        """
        SELECT id::text, provider_user_id, access_token, refresh_token, scopes,
               expires_at, last_sync_at, last_error
        FROM oauth_tokens WHERE user_id = %s AND provider = %s
        """,
        (user_id, PROVIDER),
    )


def disconnect(user_id: str, purge: bool = False) -> dict[str, int]:
    """Débranche l'intégration. `purge` supprime aussi les données importées.

    Deux niveaux distincts, et le second n'est pas cosmétique : supprimer les jetons
    coupe l'accès à venir, mais les données déjà importées **et leurs traces en
    mémoire vectorisée** restent. Ne pas proposer de les effacer serait un piège.
    """
    removed = {"jetons": db.execute(
        "DELETE FROM oauth_tokens WHERE user_id = %s AND provider = %s", (user_id, PROVIDER)
    )}
    if purge:
        removed["jours"] = db.execute(
            "DELETE FROM wearable_daily WHERE user_id = %s AND provider = %s",
            (user_id, PROVIDER),
        )
        removed["seances"] = db.execute(
            "DELETE FROM wearable_workouts WHERE user_id = %s AND provider = %s",
            (user_id, PROVIDER),
        )
        # La mémoire vectorisée aussi : sans ça, la donnée survivrait à sa suppression
        # dans une table que personne ne penserait à regarder.
        removed["souvenirs"] = db.execute(
            "DELETE FROM user_chunks WHERE user_id = %s AND source_kind = 'wearable'",
            (user_id,),
        )
    return removed


def _access_token(user_id: str) -> str:
    """Jeton d'accès valide, rafraîchi si nécessaire."""
    row = connection(user_id)
    if row is None:
        raise WhoopError("Aucune connexion Whoop sur ce compte.")

    expires_at = row["expires_at"]
    fresh = expires_at is not None and expires_at > dt.datetime.now(expires_at.tzinfo) + dt.timedelta(minutes=2)
    if fresh:
        token = crypto.unseal(row["access_token"])
        if token:
            return token

    sealed_refresh = row["refresh_token"]
    refresh_token = crypto.unseal(sealed_refresh) if sealed_refresh else None
    if not refresh_token:
        raise WhoopError(
            "La connexion Whoop doit être refaite : le jeton de rafraîchissement est "
            "absent ou illisible."
        )
    payload = refresh(refresh_token)
    save_tokens(user_id, payload, row["provider_user_id"])
    return str(payload["access_token"])


# --- Appels API -------------------------------------------------------------


def _get(user_id: str, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    token = _access_token(user_id)
    with httpx.Client(timeout=30.0) as client:
        response = client.get(
            f"{API_BASE}{path}",
            params=params or {},
            headers={"Authorization": f"Bearer {token}"},
        )
    if response.status_code == 429:
        raise WhoopError("Whoop limite les appels pour l'instant. Réessaie dans une minute.")
    if response.status_code >= 400:
        logger.warning("Whoop %s → %s : %s", path, response.status_code, response.text[:200])
        raise WhoopError(f"Whoop a répondu {response.status_code} sur {path}.")
    return response.json()


def _paginate(
    user_id: str, path: str, start: dt.date, end: dt.date
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    params: dict[str, Any] = {
        "limit": PAGE_SIZE,
        "start": f"{start.isoformat()}T00:00:00.000Z",
        "end": f"{(end + dt.timedelta(days=1)).isoformat()}T00:00:00.000Z",
    }
    for _ in range(MAX_PAGES):
        payload = _get(user_id, path, params)
        records += payload.get("records") or []
        token = payload.get("next_token")
        if not token:
            return records
        params = {**params, "nextToken": token}
    logger.warning("Pagination Whoop bornée à %s pages sur %s", MAX_PAGES, path)
    return records


# --- Mapping ----------------------------------------------------------------


def _day_of(value: str | None) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _hours(millis: Any) -> float | None:
    try:
        return round(float(millis) / 3_600_000.0, 2)
    except (TypeError, ValueError):
        return None


def sync(user_id: str, days: int = 30) -> dict[str, Any]:
    """Importe récupérations, sommeils, cycles et séances sur la fenêtre demandée.

    Les quatre ressources alimentent la même ligne par jour, en quatre passes. Un
    `score_state` autre que `SCORED` est ignoré : Whoop renvoie des enregistrements
    dont le score n'est pas encore calculé, et les écrire produirait des valeurs
    nulles qui écraseraient ensuite les bonnes.
    """
    end = dt.date.today()
    start = end - dt.timedelta(days=days)
    counts = {"recuperations": 0, "sommeils": 0, "cycles": 0, "seances": 0}

    def _upsert(day: dt.date, values: dict[str, Any], raw: dict[str, Any]) -> None:
        columns = list(values)
        if not columns:
            return
        assignments = ", ".join(f"{c} = coalesce(EXCLUDED.{c}, wearable_daily.{c})" for c in columns)
        db.execute(
            f"""
            INSERT INTO wearable_daily (user_id, provider, entry_date, raw, {", ".join(columns)})
            VALUES (%(user_id)s, %(provider)s, %(entry_date)s, %(raw)s,
                    {", ".join(f"%({c})s" for c in columns)})
            ON CONFLICT (user_id, provider, entry_date) DO UPDATE SET
                {assignments},
                raw = wearable_daily.raw || EXCLUDED.raw,
                updated_at = now()
            """,
            {
                "user_id": user_id, "provider": PROVIDER, "entry_date": day,
                "raw": json.dumps(raw, default=str), **values,
            },
        )

    for record in _paginate(user_id, "/v2/recovery", start, end):
        if record.get("score_state") != "SCORED":
            continue
        day = _day_of(record.get("created_at"))
        score = record.get("score") or {}
        if day is None:
            continue
        _upsert(
            day,
            {
                "hrv_rmssd_milli": score.get("hrv_rmssd_milli"),
                "resting_heart_rate": score.get("resting_heart_rate"),
                "recovery_score": score.get("recovery_score"),
                "spo2_percentage": score.get("spo2_percentage"),
                "skin_temp_celsius": score.get("skin_temp_celsius"),
            },
            {"recovery": record},
        )
        counts["recuperations"] += 1

    for record in _paginate(user_id, "/v2/activity/sleep", start, end):
        if record.get("score_state") != "SCORED":
            continue
        # Le jour du réveil, pas celui du coucher : c'est la nuit *de* ce jour-là au
        # sens du check-in du matin, et les deux doivent parler du même sommeil.
        day = _day_of(record.get("end"))
        score = record.get("score") or {}
        stages = score.get("stage_summary") or {}
        if day is None:
            continue
        asleep = sum(
            float(stages.get(k) or 0)
            for k in ("total_light_sleep_time_milli", "total_slow_wave_sleep_time_milli",
                      "total_rem_sleep_time_milli")
        )
        _upsert(
            day,
            {
                "sleep_hours": _hours(asleep) if asleep else None,
                "sleep_efficiency": score.get("sleep_efficiency_percentage"),
                "sleep_performance": score.get("sleep_performance_percentage"),
                "respiratory_rate": score.get("respiratory_rate"),
            },
            {"sleep": record},
        )
        counts["sommeils"] += 1

    for record in _paginate(user_id, "/v2/cycle", start, end):
        if record.get("score_state") != "SCORED":
            continue
        day = _day_of(record.get("start"))
        score = record.get("score") or {}
        if day is None:
            continue
        _upsert(
            day,
            {
                "strain": score.get("strain"),
                "average_heart_rate": score.get("average_heart_rate"),
                "max_heart_rate": score.get("max_heart_rate"),
                "kilojoule": score.get("kilojoule"),
            },
            {"cycle": record},
        )
        counts["cycles"] += 1

    for record in _paginate(user_id, "/v2/activity/workout", start, end):
        score = record.get("score") or {}
        day = _day_of(record.get("start"))
        if day is None or not record.get("id"):
            continue
        db.execute(
            """
            INSERT INTO wearable_workouts
                (user_id, provider, provider_id, entry_date, started_at, ended_at, sport,
                 strain, average_heart_rate, max_heart_rate, kilojoule, distance_meter,
                 zone_durations, raw)
            VALUES (%(user_id)s, %(provider)s, %(provider_id)s, %(entry_date)s, %(started)s,
                    %(ended)s, %(sport)s, %(strain)s, %(avg)s, %(max)s, %(kj)s, %(distance)s,
                    %(zones)s, %(raw)s)
            ON CONFLICT (user_id, provider, provider_id) DO UPDATE SET
                strain = EXCLUDED.strain,
                average_heart_rate = EXCLUDED.average_heart_rate,
                max_heart_rate = EXCLUDED.max_heart_rate,
                kilojoule = EXCLUDED.kilojoule,
                distance_meter = EXCLUDED.distance_meter,
                zone_durations = EXCLUDED.zone_durations,
                raw = EXCLUDED.raw,
                updated_at = now()
            """,
            {
                "user_id": user_id, "provider": PROVIDER, "provider_id": str(record["id"]),
                "entry_date": day, "started": record.get("start"), "ended": record.get("end"),
                "sport": record.get("sport_name") or record.get("sport_id"),
                "strain": score.get("strain"),
                "avg": score.get("average_heart_rate"),
                "max": score.get("max_heart_rate"),
                "kj": score.get("kilojoule"),
                "distance": score.get("distance_meter"),
                "zones": json.dumps(score.get("zone_durations") or {}, default=str),
                "raw": json.dumps(record, default=str),
            },
        )
        counts["seances"] += 1

    db.execute(
        "UPDATE oauth_tokens SET last_sync_at = now(), last_error = NULL "
        "WHERE user_id = %s AND provider = %s",
        (user_id, PROVIDER),
    )
    return counts


# --- Webhooks ---------------------------------------------------------------


def verify_signature(body: bytes, signature: str | None, timestamp: str | None) -> bool:
    """Vérifie la signature d'un webhook.

    Refuse par défaut : une signature absente, un secret non configuré ou un horodatage
    manquant renvoient `False`. Un webhook non signé accepté serait un endpoint public
    capable d'écrire des données de santé.
    """
    if not signature or not timestamp or not settings.whoop_client_secret:
        return False
    expected = hmac.new(
        settings.whoop_client_secret.encode("utf-8"),
        timestamp.encode("utf-8") + body,
        hashlib.sha256,
    ).digest()
    import base64

    return hmac.compare_digest(base64.b64encode(expected).decode("ascii"), signature)


def user_for_provider_id(provider_user_id: str) -> str | None:
    row = db.query_one(
        "SELECT user_id::text FROM oauth_tokens WHERE provider = %s AND provider_user_id = %s",
        (PROVIDER, str(provider_user_id)),
    )
    return row["user_id"] if row else None


# --- Lecture pour les signaux ----------------------------------------------


def daily_map(user_id: str, start: dt.date, end: dt.date) -> dict[dt.date, dict[str, Any]]:
    rows = db.query_all(
        """
        SELECT entry_date, hrv_rmssd_milli, resting_heart_rate, recovery_score,
               sleep_hours, sleep_efficiency, respiratory_rate, strain,
               average_heart_rate, max_heart_rate
        FROM wearable_daily
        WHERE user_id = %s AND provider = %s AND entry_date BETWEEN %s AND %s
        """,
        (user_id, PROVIDER, start, end),
    )
    return {r["entry_date"]: r for r in rows}


def intense_sessions(user_id: str, start: dt.date, end: dt.date) -> list[dict[str, Any]]:
    """Séances à fréquence cardiaque maximale élevée. Sert à l'invite du lendemain."""
    return db.query_all(
        """
        SELECT entry_date, sport, max_heart_rate, strain, zone_durations
        FROM wearable_workouts
        WHERE user_id = %s AND provider = %s AND entry_date BETWEEN %s AND %s
          AND max_heart_rate >= %s
        ORDER BY entry_date DESC
        """,
        (user_id, PROVIDER, start, end, INTENSE_HR_THRESHOLD),
    )
