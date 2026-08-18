"""Bibliothèque : le corpus consultable, et la recherche hybride exposée telle quelle.

Exposer la recherche à l'utilisateur n'est pas un gadget : cela lui permet de
vérifier lui-même sur quoi l'IA s'appuie, et de constater que les fiches citées
existent réellement.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from .. import db, search
from ..config import KNOWLEDGE_DIR
from ..deps import CurrentUser
from ..schemas import KbDocDetailOut, KbDocOut

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.get("", response_model=list[KbDocOut])
def list_docs(user: CurrentUser, category: str | None = None) -> list[KbDocOut]:
    rows = db.query_all(
        """
        SELECT doc_id, title, category, evidence_level, targets, up_module,
               duration_min, sources
        FROM kb_documents
        WHERE (%s::text IS NULL OR category = %s::text)
        ORDER BY up_module NULLS FIRST, doc_id
        """,
        (category, category),
    )
    return [KbDocOut(**r) for r in rows]


@router.get("/search")
async def search_docs(
    user: CurrentUser,
    q: str = Query(min_length=2, max_length=300),
    k: int = Query(default=8, ge=1, le=20),
) -> dict[str, Any]:
    chunks = await asyncio.to_thread(lambda: search.hybrid_search(q, k=k))
    return {
        "query": q,
        "mode": chunks[0]["retrieval"]["mode"] if chunks else "aucun résultat",
        "explication": (
            "Recherche hybride : le classement vectoriel (embeddings OpenAI "
            "text-embedding-3-large, 3072 dimensions, index HNSW sur halfvec) et le classement "
            "plein texte PostgreSQL sont fusionnés par rangs réciproques (RRF). Les rangs de "
            "chaque méthode sont affichés pour chaque résultat."
        ),
        "resultats": [
            {
                "doc_id": c["doc_id"],
                "titre": c["title"],
                "section": c["heading"],
                "extrait": c["content"][:600],
                "niveau_de_preuve": c["evidence_level"],
                "sources": c["sources"],
                "recuperation": c["retrieval"],
            }
            for c in chunks
        ],
    }


@router.get("/{doc_id}", response_model=KbDocDetailOut)
def get_doc(doc_id: str, user: CurrentUser) -> KbDocDetailOut:
    row = db.query_one(
        """
        SELECT doc_id, title, category, evidence_level, targets, up_module,
               duration_min, sources, path
        FROM kb_documents WHERE doc_id = %s
        """,
        (doc_id,),
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Fiche introuvable.")

    # Le contenu est relu depuis le disque : les fiches sont la source de vérité,
    # la base ne stocke que les chunks vectorisés.
    content = ""
    if row.get("path"):
        path = KNOWLEDGE_DIR / str(row["path"])
        if path.is_file() and path.parent == KNOWLEDGE_DIR:
            raw = path.read_text(encoding="utf-8")
            parts = raw.split("---", 2)
            content = parts[2].strip() if len(parts) >= 3 else raw
    if not content:
        chunks = db.query_all(
            """
            SELECT content FROM kb_chunks c
            JOIN kb_documents d ON d.id = c.document_id
            WHERE d.doc_id = %s ORDER BY chunk_index
            """,
            (doc_id,),
        )
        content = "\n\n".join(c["content"] for c in chunks)

    row.pop("path", None)
    return KbDocDetailOut(**row, content=content)
