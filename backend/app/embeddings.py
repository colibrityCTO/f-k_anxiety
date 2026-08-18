"""Embeddings OpenAI text-embedding-3-large (3072 dimensions).

Singleton paresseux, comme les clients LLM. Les vecteurs sont stockés dans
PostgreSQL en `halfvec(3072)` : la demi-précision divise par deux la taille de
l'index et permet de rester sous la limite dimensionnelle de HNSW, pour une perte
de précision négligeable en recherche sémantique.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from .config import settings

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_embedder: Any | None = None


class EmbeddingsUnavailable(RuntimeError):
    """Pas de clé OpenAI : la recherche vectorielle est indisponible.

    Le système reste fonctionnel en recherche lexicale seule (voir search.py).
    """


def get_embedder() -> Any:
    global _embedder
    if not settings.has_embeddings:
        raise EmbeddingsUnavailable(
            "OPENAI_API_KEY est requis pour les embeddings (text-embedding-3-large)."
        )
    if _embedder is None:
        with _lock:
            if _embedder is None:
                from langchain_openai import OpenAIEmbeddings

                _embedder = OpenAIEmbeddings(
                    model=settings.embedding_model,
                    api_key=settings.openai_api_key,
                    dimensions=settings.embedding_dim,
                    timeout=60,
                    max_retries=3,
                )
                logger.info(
                    "Embedder initialisé (%s, %s dimensions)",
                    settings.embedding_model,
                    settings.embedding_dim,
                )
    return _embedder


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embeddings d'un lot de textes (appel synchrone, utilisé par ingest.py)."""
    return get_embedder().embed_documents(texts)


def embed_query(text: str) -> list[float]:
    """Embedding d'une requête (synchrone : à envelopper dans asyncio.to_thread)."""
    return get_embedder().embed_query(text)


async def aembed_query(text: str) -> list[float]:
    return await get_embedder().aembed_query(text)


def try_embed_query(text: str) -> list[float] | None:
    """Version tolérante : retourne None au lieu de lever, pour dégrader en lexical."""
    try:
        return embed_query(text)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Embedding indisponible, repli sur la recherche lexicale : %s", exc)
        return None
