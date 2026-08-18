"""Analyse IA : génération, historique, signaux bruts, et chat explicatif en SSE."""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from sse_starlette.sse import EventSourceResponse

from .. import analysis, db, llm_client, signals as signals_mod
from ..config import settings
from ..deps import CurrentUser
from ..schemas import AnalyzeIn, ChatIn, InsightOut

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/insights", tags=["insights"])


@router.get("/engine")
def engine_status(user: CurrentUser) -> dict[str, Any]:
    """Ce que le serveur peut réellement faire, et ce que l'utilisateur a autorisé."""
    return {
        "moteurs_disponibles": llm_client.available_engines(),
        "moteur_principal": (
            f"anthropic:{settings.anthropic_model}" if settings.has_anthropic else None
        ),
        "fallback": f"openai:{settings.openai_model}" if settings.has_openai else None,
        "recherche_vectorielle": settings.has_embeddings,
        "modele_embeddings": settings.embedding_model if settings.has_embeddings else None,
        "consentement_utilisateur": bool(user.get("ai_consent")),
        "mode_effectif": (
            "llm"
            if (settings.has_llm and user.get("ai_consent"))
            else "local_deterministe"
        ),
        "explication": (
            "En mode « local_deterministe », aucune donnée ne quitte le serveur : l'analyse est "
            "produite par des règles et des calculs statistiques explicites (app/signals.py). "
            "En mode « llm », les signaux calculés et le contenu pertinent de votre journal sont "
            "envoyés à l'API du fournisseur pour la rédaction."
        ),
    }


@router.get("/signals")
async def raw_signals(
    user: CurrentUser,
    days: int = Query(default=21, ge=7, le=180),
    end: dt.date | None = None,
) -> dict[str, Any]:
    """Les signaux bruts, tels qu'ils sont injectés dans le prompt.

    C'est le panneau de traçabilité : chaque chiffre affiché dans l'application
    peut être retrouvé ici avec sa méthode de calcul et ses données sources.
    """
    return await asyncio.to_thread(signals_mod.compute, user["id"], end or dt.date.today(), days)


@router.post("/analyze", response_model=InsightOut)
async def analyze(payload: AnalyzeIn, user: CurrentUser) -> InsightOut:
    result = await analysis.analyze(user, scope=payload.scope, end_date=payload.end_date)
    return InsightOut(**result)


@router.get("", response_model=list[InsightOut])
def history(
    user: CurrentUser,
    scope: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
) -> list[InsightOut]:
    rows = db.query_all(
        """
        SELECT id::text, scope, period_start, period_end, headline, body, signals,
               citations, recommendations, engine, risk_flag, created_at
        FROM insights
        WHERE user_id = %s AND (%s::text IS NULL OR scope = %s::text)
        ORDER BY created_at DESC LIMIT %s
        """,
        (user["id"], scope, scope, limit),
    )
    return [InsightOut(**r) for r in rows]


@router.get("/{insight_id}", response_model=InsightOut)
def get_insight(insight_id: str, user: CurrentUser) -> InsightOut:
    row = db.query_one(
        """
        SELECT id::text, scope, period_start, period_end, headline, body, signals,
               citations, recommendations, engine, risk_flag, created_at
        FROM insights WHERE id = %s AND user_id = %s
        """,
        (insight_id, user["id"]),
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Analyse introuvable.")
    return InsightOut(**row)


@router.post("/chat")
async def chat(payload: ChatIn, user: CurrentUser) -> EventSourceResponse:
    """Chat explicatif « d'où ça sort ? », en streaming SSE.

    Les événements émis : `citations` (d'abord, pour afficher les sources tout de
    suite), `engine`, `token`, éventuellement `safety`, puis `done`.
    """

    async def event_generator():
        collected: list[str] = []
        engine = "inconnu"
        try:
            async for event in analysis.stream_explanation(
                user,
                payload.question,
                include_my_data=payload.include_my_data,
                about_activity=payload.about_activity,
            ):
                if event["event"] == "token":
                    collected.append(event["data"])
                if event["event"] == "done":
                    engine = event["data"].get("engine", engine)
                yield {
                    "event": event["event"],
                    "data": event["data"]
                    if isinstance(event["data"], str)
                    else json.dumps(event["data"], ensure_ascii=False, default=str),
                }
        except asyncio.CancelledError:  # client déconnecté
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("Erreur pendant le streaming")
            yield {"event": "error", "data": f"Erreur interne : {exc}"}
        finally:
            answer = "".join(collected).strip()
            if answer:
                # Conservation de l'échange pour que l'utilisateur retrouve ses
                # explications ; exécuté hors boucle événementielle.
                await asyncio.to_thread(
                    db.execute,
                    """
                    INSERT INTO chat_messages (user_id, role, content, engine)
                    VALUES (%s, 'user', %s, NULL), (%s, 'assistant', %s, %s)
                    """,
                    (user["id"], payload.question, user["id"], answer, engine),
                )

    return EventSourceResponse(event_generator())


@router.get("/chat/history")
def chat_history(
    user: CurrentUser, limit: int = Query(default=40, ge=1, le=200)
) -> list[dict[str, Any]]:
    return db.query_all(
        """
        SELECT id::text, role, content, engine, created_at
        FROM chat_messages WHERE user_id = %s
        ORDER BY created_at DESC LIMIT %s
        """,
        (user["id"], limit),
    )
