"""Recherche hybride dans le corpus : similarité vectorielle + plein texte + filtres.

`hybrid_search` combine deux classements indépendants par fusion de rangs
réciproques (RRF, Cormack et al.) :

    score = 1/(k + rang_vectoriel) + 1/(k + rang_lexical)

C'est plus robuste qu'une somme pondérée de scores hétérogènes (distance cosinus
et ts_rank_cd ne sont pas sur la même échelle) et cela ne nécessite aucune
normalisation. Chaque résultat conserve ses deux rangs, ce qui permet d'expliquer
à l'utilisateur *pourquoi* une fiche a été retenue.
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from typing import Any

from . import db
from .embeddings import try_embed_query

logger = logging.getLogger(__name__)

RRF_K = 60

_WORD_RE = re.compile(r"[\wÀ-ÿ']{3,}", re.UNICODE)


def lexical_query(text: str) -> str:
    """Transforme une requête en disjonction de termes pour `websearch_to_tsquery`.

    Par défaut, `websearch_to_tsquery` combine les mots avec un ET : une requête
    de cinq mots ne remonte alors que les chunks contenant les cinq, et le
    classement lexical est presque toujours vide. On passe donc en OU explicite ;
    `ts_rank_cd` fait ensuite remonter les chunks qui couvrent le plus de termes.
    """
    terms = _WORD_RE.findall(text.lower())[:14]
    return " or ".join(terms) if terms else text


@lru_cache(maxsize=1)
def embedding_cast() -> str:
    """Type réel de la colonne `kb_chunks.embedding` : 'halfvec' ou 'vector'.

    Le cast SQL doit correspondre au type de la colonne, sinon aucun opérateur de
    distance n'est trouvé. On l'interroge une fois et on met en cache.
    """
    try:
        row = db.query_one(
            """
            SELECT udt_name FROM information_schema.columns
            WHERE table_name = 'kb_chunks' AND column_name = 'embedding'
            """
        )
        if row and row.get("udt_name") in {"halfvec", "vector"}:
            return str(row["udt_name"])
    except Exception as exc:  # noqa: BLE001
        logger.warning("Type de colonne embedding indéterminé : %s", exc)
    return "halfvec"


_SQL = """
WITH filtered AS (
    SELECT c.id, c.embedding
    FROM kb_chunks c
    JOIN kb_documents d ON d.id = c.document_id
    WHERE (%(targets)s::text[] IS NULL OR d.targets && %(targets)s::text[])
      AND (%(categories)s::text[] IS NULL OR d.category = ANY(%(categories)s::text[]))
      AND (%(doc_ids)s::text[] IS NULL OR d.doc_id = ANY(%(doc_ids)s::text[]))
      AND (%(evidence_levels)s::text[] IS NULL OR d.evidence_level = ANY(%(evidence_levels)s::text[]))
      AND (%(up_module)s::int IS NULL OR d.up_module = %(up_module)s::int)
),
vec AS (
    SELECT f.id,
           row_number() OVER (ORDER BY f.embedding <=> %(embedding)s::{cast}) AS rnk,
           1 - (f.embedding <=> %(embedding)s::{cast}) AS similarity
    FROM filtered f
    WHERE %(embedding)s IS NOT NULL AND f.embedding IS NOT NULL
    ORDER BY f.embedding <=> %(embedding)s::{cast}
    LIMIT %(candidates)s
),
lex AS (
    SELECT c.id,
           row_number() OVER (ORDER BY ts_rank_cd(c.tsv, q.query) DESC) AS rnk,
           ts_rank_cd(c.tsv, q.query) AS lex_score
    FROM kb_chunks c
    JOIN filtered f ON f.id = c.id
    CROSS JOIN websearch_to_tsquery('french', %(query_text)s) AS q(query)
    WHERE c.tsv @@ q.query
    ORDER BY ts_rank_cd(c.tsv, q.query) DESC
    LIMIT %(candidates)s
),
merged AS (
    SELECT id FROM vec
    UNION
    SELECT id FROM lex
)
SELECT c.id                                        AS chunk_id,
       c.chunk_index,
       c.heading,
       c.content,
       d.doc_id,
       d.title,
       d.category,
       d.evidence_level,
       d.targets,
       d.up_module,
       d.sources,
       v.similarity,
       v.rnk                                       AS vector_rank,
       l.lex_score,
       l.rnk                                       AS lexical_rank,
       COALESCE(1.0 / (%(rrf_k)s + v.rnk), 0)
     + COALESCE(1.0 / (%(rrf_k)s + l.rnk), 0)      AS rrf_score
FROM merged m
JOIN kb_chunks c    ON c.id = m.id
JOIN kb_documents d ON d.id = c.document_id
LEFT JOIN vec v ON v.id = m.id
LEFT JOIN lex l ON l.id = m.id
ORDER BY rrf_score DESC, d.evidence_level ASC
LIMIT %(k)s
"""


def hybrid_search(
    query_text: str,
    *,
    targets: list[str] | None = None,
    categories: list[str] | None = None,
    doc_ids: list[str] | None = None,
    evidence_levels: list[str] | None = None,
    up_module: int | None = None,
    k: int = 6,
    candidates: int = 30,
    embedding: list[float] | None = None,
) -> list[dict[str, Any]]:
    """Retourne les chunks les plus pertinents, avec leur traçabilité.

    `embedding` peut être fourni par l'appelant (déjà calculé) ; sinon il est
    calculé ici. S'il est indisponible (pas de clé OpenAI), la recherche se
    dégrade proprement en lexical seul.
    """
    if embedding is None:
        embedding = try_embed_query(query_text)

    params = {
        "embedding": db.to_halfvec(embedding) if embedding else None,
        "query_text": lexical_query(query_text),
        "targets": targets or None,
        "categories": categories or None,
        "doc_ids": doc_ids or None,
        "evidence_levels": evidence_levels or None,
        "up_module": up_module,
        "candidates": candidates,
        "k": k,
        "rrf_k": RRF_K,
    }
    sql = _SQL.format(cast=embedding_cast())
    rows = db.query_all(sql, params)

    for row in rows:
        row["retrieval"] = {
            "vector_rank": row.pop("vector_rank", None),
            "lexical_rank": row.pop("lexical_rank", None),
            "similarity": float(row["similarity"]) if row.get("similarity") is not None else None,
            "lex_score": float(row["lex_score"]) if row.get("lex_score") is not None else None,
            "rrf_score": float(row["rrf_score"]) if row.get("rrf_score") is not None else None,
            "mode": "hybride" if embedding else "lexical",
        }
        row.pop("similarity", None)
        row.pop("lex_score", None)
        row.pop("rrf_score", None)
    return rows


def to_citations(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Réduit des chunks à des citations affichables (une par document)."""
    seen: dict[str, dict[str, Any]] = {}
    for chunk in chunks:
        doc_id = chunk["doc_id"]
        if doc_id in seen:
            seen[doc_id]["extraits"].append(chunk["heading"])
            continue
        seen[doc_id] = {
            "doc_id": doc_id,
            "titre": chunk["title"],
            "niveau_de_preuve": chunk.get("evidence_level"),
            "categorie": chunk.get("category"),
            "sources": chunk.get("sources") or [],
            "extraits": [chunk["heading"]],
            "recuperation": chunk.get("retrieval", {}),
        }
    return list(seen.values())


def build_context(chunks: list[dict[str, Any]], max_chars: int = 12000) -> str:
    """Assemble le contexte injecté dans le prompt, avec des balises citables."""
    parts: list[str] = []
    total = 0
    for index, chunk in enumerate(chunks, start=1):
        header = (
            f"[{index}] doc_id={chunk['doc_id']} | {chunk['title']}"
            f" | niveau de preuve {chunk.get('evidence_level') or '?'}"
            f" | section : {chunk.get('heading') or '—'}"
        )
        sources = chunk.get("sources") or []
        source_lines = "\n".join(
            f"    - {s.get('label', '')} {s.get('url', '')}".rstrip() for s in sources[:3]
        )
        block = f"{header}\n{chunk['content'].strip()}"
        if source_lines:
            block += f"\n  Références de la fiche :\n{source_lines}"
        if total + len(block) > max_chars:
            break
        parts.append(block)
        total += len(block)
    return "\n\n---\n\n".join(parts)
