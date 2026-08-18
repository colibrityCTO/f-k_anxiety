"""Point d'entrée FastAPI.

Toutes les routes sauf /auth/register, /auth/login, /health et /meta exigent un
jeton JWT valide : l'application n'est accessible qu'aux utilisateurs connectés.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import db
from .config import settings
from .routers import (
    activities,
    assessments,
    auth,
    chat,
    checkins,
    exposures,
    insights,
    journal,
    knowledge,
    program,
    push,
)
from .signals import CRISIS_RESOURCES

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task: asyncio.Task | None = None
    try:
        db.init_db()
    except Exception as exc:  # noqa: BLE001
        # On ne veut pas empêcher le démarrage : /health dira ce qui manque.
        logger.error("Initialisation du schéma impossible : %s", exc)
    else:
        _bootstrap_corpus()
        if settings.scheduler_enabled:
            from . import scheduler

            task = asyncio.create_task(scheduler.run_forever())
    yield
    if task is not None:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    db.close_pool()


def _bootstrap_corpus() -> None:
    """Sème le catalogue d'activités et ingère le corpus si la base est vide.

    Objectif : un premier déploiement (Railway par exemple) est immédiatement
    fonctionnel, sans commande manuelle. Si la base contient déjà des fiches, on
    ne touche à rien — l'ingestion se relance alors explicitement avec
    `python -m app.ingest`.
    """
    if os.environ.get("AUTO_INGEST", "true").lower() in {"0", "false", "no"}:
        return
    try:
        from .ingest import ingest

        existing = db.query_one("SELECT count(*) AS n FROM kb_documents")
        if existing and int(existing["n"]) > 0:
            return
        report = ingest(force=False, embed=settings.has_embeddings)
        logger.info("Corpus initialisé : %s", report)
    except Exception as exc:  # noqa: BLE001
        logger.error("Ingestion initiale impossible (l'API reste utilisable) : %s", exc)


app = FastAPI(
    title="Sérénité — API",
    version="1.0.0",
    description=(
        "API du programme quotidien de suivi des troubles anxieux. Fondée sur le Protocole "
        "Unifié (Barlow) et les recommandations NICE. Chaque recommandation renvoyée par l'API "
        "porte son mécanisme, son niveau de preuve, ses sources et les données personnelles qui "
        "l'ont déclenchée."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
# Le fil : l'unique écran de la V1. Les routers suivants restent exposés — ils
# alimentent les widgets et les versions ultérieures.
app.include_router(chat.router)
app.include_router(program.router)
app.include_router(checkins.router)
app.include_router(journal.router)
app.include_router(activities.router)
app.include_router(assessments.router)
app.include_router(exposures.router)
app.include_router(insights.router)
app.include_router(knowledge.router)
app.include_router(push.router)


@app.get("/health", tags=["meta"])
def health() -> JSONResponse:
    """Vivacité : répond 200 dès que le processus tourne.

    Volontairement tolérant. Un healthcheck qui échoue met le service **hors
    ligne** chez Railway : si `/health` renvoyait 503 parce que la base est
    momentanément injoignable, une coupure de quelques secondes côté Postgres
    ferait tomber toute l'API — et le front n'afficherait qu'un 502 opaque.

    L'état réel des dépendances est dans le corps de la réponse, et
    `/health/deep` reste strict pour la supervision.
    """
    status = db.healthcheck()
    degraded = status.get("database") != "up" or not status.get("pgvector")
    return JSONResponse(
        status_code=200,
        content={
            "status": "degraded" if degraded else "ok",
            **status,
            "diagnostic": _diagnose(status),
        },
    )


@app.get("/health/deep", tags=["meta"])
def health_deep() -> JSONResponse:
    """Disponibilité réelle : 503 si la base ou pgvector manquent."""
    status = db.healthcheck()
    ready = status.get("database") == "up" and bool(status.get("pgvector"))
    return JSONResponse(
        status_code=200 if ready else 503,
        content={"status": "ok" if ready else "indisponible", **status, "diagnostic": _diagnose(status)},
    )


def _diagnose(status: dict) -> str | None:
    """Dit quoi corriger, au lieu de laisser deviner."""
    if status.get("database") != "up":
        return (
            "PostgreSQL injoignable : vérifie DATABASE_URL (sur Railway, "
            "${{Postgres.DATABASE_URL}}) et que le service Postgres tourne."
        )
    if not status.get("pgvector"):
        return (
            "Extension pgvector absente : utilise le template « Postgres + pgvector » "
            "(image pgvector/pgvector), pas le Postgres standard."
        )
    if not status.get("kb_chunks"):
        return "Corpus non ingéré : lance « python -m app.ingest » ou laisse AUTO_INGEST à true."
    if not status.get("kb_chunks_embedded"):
        return (
            "Corpus non vectorisé : sans OPENAI_API_KEY la recherche fonctionne en plein texte "
            "seul. Ajoute la clé puis relance l'ingestion."
        )
    return None


@app.get("/meta", tags=["meta"])
def meta() -> dict:
    """Informations publiques : cadre, limites, ressources d'urgence.

    Volontairement accessible sans authentification : les ressources d'urgence
    ne doivent jamais dépendre d'une session valide.
    """
    return {
        "nom": "Sérénité",
        "cadre": (
            "Intervention d'auto-assistance structurée (« faible intensité » au sens des "
            "recommandations NICE), fondée sur le Protocole Unifié de Barlow."
        ),
        "limites": [
            "Ne pose aucun diagnostic.",
            "Ne remplace ni une psychothérapie encadrée ni un suivi médical.",
            "Ne donne aucun conseil sur les médicaments.",
            "N'est pas un dispositif médical certifié.",
        ],
        "quand_consulter": [
            "GAD-7 ≥ 15, ou anxiété qui empêche de travailler ou de sortir.",
            "Aucune amélioration après 6 à 8 semaines de pratique régulière.",
            "Consommation d'alcool ou de médicaments pour tenir.",
            "Symptômes dépressifs marqués.",
            "Symptômes physiques inexpliqués jamais évalués médicalement.",
        ],
        "urgence": CRISIS_RESOURCES,
        "inscriptions_ouvertes": settings.allow_registration,
    }
