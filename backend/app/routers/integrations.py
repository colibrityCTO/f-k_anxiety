"""Routes d'intégration : connexion d'un bracelet, synchronisation, révocation.

L'intégration est **absente** de l'interface si le serveur n'est pas configuré : pas
de bouton qui mène à une erreur, pas de route qui échoue à moitié. `GET /integrations`
le dit, et le front s'y conforme.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .. import crypto, db
from ..config import settings
from ..deps import CurrentUser
from ..integrations import whoop

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.get("")
def list_integrations(user: CurrentUser) -> dict[str, Any]:
    """État des intégrations pour ce compte."""
    connection = whoop.connection(user["id"])
    summary: dict[str, Any] = {"connecte": connection is not None}
    if connection is not None:
        summary.update(
            {
                "scopes": connection["scopes"],
                "expire_le": connection["expires_at"],
                "derniere_synchro": connection["last_sync_at"],
                "derniere_erreur": connection["last_error"],
            }
        )
        volume = db.query_one(
            """
            SELECT count(*) AS jours,
                   (SELECT count(*) FROM wearable_workouts
                    WHERE user_id = %(uid)s AND provider = 'whoop') AS seances,
                   max(entry_date) AS dernier_jour
            FROM wearable_daily WHERE user_id = %(uid)s AND provider = 'whoop'
            """,
            {"uid": user["id"]},
        )
        summary["volume"] = dict(volume) if volume else {}

    return {
        "whoop": {
            # Deux conditions, pas une : les identifiants **et** la bibliothèque de
            # chiffrement. Sans elle, on ne peut pas stocker un jeton en sécurité, donc
            # on ne propose pas la connexion — plutôt que d'échouer au premier clic.
            "configure": settings.has_whoop and crypto.available(),
            **summary,
            # Dit une fois, à l'endroit où la question se pose : ce que cette source
            # peut et ne peut pas faire. Sans ça, l'attente est « l'app détectera mes
            # crises », et la déception est garantie.
            "limite": (
                "L'API Whoop ne fournit aucune série de fréquence cardiaque, seulement "
                "des agrégats par nuit, par cycle et par séance. On peut donc croiser "
                "une séance intense avec une crise du lendemain, mais pas détecter une "
                "crise. Et ce ne serait pas souhaitable : une fausse alerte de panique "
                "est un déclencheur de panique."
            ),
        }
    }


@router.post("/whoop/authorize")
def start_authorization(user: CurrentUser) -> dict[str, str]:
    """Renvoie l'URL d'autorisation, et retient `state` pour le vérifier au retour."""
    if not settings.has_whoop:
        raise HTTPException(status_code=503, detail="Intégration Whoop non configurée sur ce serveur.")
    if not crypto.available():
        raise HTTPException(
            status_code=503,
            detail=(
                "La bibliothèque de chiffrement n'est pas installée sur ce serveur : un "
                "jeton d'accès à des données physiologiques ne serait pas stocké en "
                "sécurité, donc la connexion est refusée."
            ),
        )
    state = whoop.new_state()
    # `state` vit dans le profil : il est à usage unique, vérifié puis effacé au retour.
    # Sans cette vérification, n'importe qui pourrait faire aboutir un code d'autorisation
    # sur le compte d'un autre.
    db.execute(
        "UPDATE users SET profile = jsonb_set(profile, '{whoop_state}', %s::jsonb) WHERE id = %s",
        (f'"{state}"', user["id"]),
    )
    return {"url": whoop.authorize_url(state)}


@router.get("/whoop/callback", response_class=HTMLResponse)
def finish_authorization(request: Request, code: str = "", state: str = "") -> Any:
    """Retour de Whoop. Vérifie `state`, échange le code, enregistre les jetons.

    Route non authentifiée par jeton — c'est le navigateur qui revient, sans en-tête
    Authorization. C'est `state` qui identifie le compte, et c'est pour ça qu'il est
    à usage unique et retiré immédiatement.
    """
    if not code or not state:
        return HTMLResponse("<p>Connexion annulée.</p>", status_code=400)

    row = db.query_one(
        "SELECT id::text FROM users WHERE profile->>'whoop_state' = %s", (state,)
    )
    if row is None:
        return HTMLResponse(
            "<p>Ce lien de connexion n'est plus valide. Relance la connexion depuis "
            "l'application.</p>",
            status_code=400,
        )
    user_id = row["id"]
    db.execute(
        "UPDATE users SET profile = profile - 'whoop_state' WHERE id = %s", (user_id,)
    )

    try:
        payload = whoop.exchange_code(code)
    except whoop.WhoopError as exc:
        db.execute(
            "UPDATE oauth_tokens SET last_error = %s WHERE user_id = %s AND provider = 'whoop'",
            (str(exc), user_id),
        )
        return HTMLResponse(f"<p>{exc}</p>", status_code=400)

    whoop.save_tokens(user_id, payload)
    # L'identifiant Whoop du membre sert aux webhooks : il est récupéré après coup,
    # une fois les jetons en place.
    try:
        basic = whoop._get(user_id, "/v2/user/profile/basic")  # noqa: SLF001
        whoop.save_tokens(user_id, payload, str(basic.get("user_id")))
    except whoop.WhoopError:
        logger.warning("Profil Whoop indisponible juste après la connexion", exc_info=True)

    return HTMLResponse(
        "<!doctype html><meta charset=utf-8>"
        "<body style=\'font-family:system-ui;background:#000;color:#fff;padding:32px\'>"
        "<h1 style=\'text-transform:uppercase\'>Whoop est connecté</h1>"
        "<p>Tu peux fermer cet onglet et revenir dans l\'application.</p></body>"
    )


@router.post("/whoop/sync")
def sync_now(user: CurrentUser, days: int = 30) -> dict[str, Any]:
    try:
        counts = whoop.sync(user["id"], max(1, min(days, 180)))
    except whoop.WhoopError as exc:
        db.execute(
            "UPDATE oauth_tokens SET last_error = %s WHERE user_id = %s AND provider = 'whoop'",
            (str(exc), user["id"]),
        )
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"importe": counts}


@router.delete("/whoop")
def revoke(user: CurrentUser, purge: bool = False) -> dict[str, Any]:
    """Débranche. `purge=true` supprime aussi les données importées **et** leurs
    traces en mémoire vectorisée — sinon la donnée survivrait à sa suppression."""
    return {"supprime": whoop.disconnect(user["id"], purge=purge)}


@router.post("/whoop/webhook")
async def webhook(request: Request) -> dict[str, str]:
    """Notification de Whoop : on ne fait pas confiance au contenu, on resynchronise.

    Le corps annonce qu'un enregistrement a changé ; il n'apporte pas la donnée. Aller
    la relire par l'API est plus simple **et** plus sûr : rien de ce qui est écrit en
    base ne vient d'une requête non authentifiée.
    """
    body = await request.body()
    if not whoop.verify_signature(
        body,
        request.headers.get("X-WHOOP-Signature"),
        request.headers.get("X-WHOOP-Signature-Timestamp"),
    ):
        raise HTTPException(status_code=401, detail="Signature invalide.")

    import json as _json

    try:
        payload = _json.loads(body or b"{}")
    except ValueError:
        raise HTTPException(status_code=400, detail="Corps illisible.") from None

    user_id = whoop.user_for_provider_id(str(payload.get("user_id") or ""))
    if user_id is None:
        # 200 volontaire : un membre inconnu n'est pas une erreur du service de push,
        # et renvoyer une erreur le ferait réessayer indéfiniment.
        return {"statut": "membre inconnu, ignoré"}
    try:
        whoop.sync(user_id, days=3)
    except whoop.WhoopError as exc:
        logger.warning("Synchronisation par webhook échouée : %s", exc)
        return {"statut": "synchronisation reportée"}
    return {"statut": "synchronisé"}
