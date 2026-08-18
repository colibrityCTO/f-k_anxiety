"""Ingestion du corpus : knowledge/*.md → chunks → embeddings → pgvector.

Usage :
    python -m app.ingest              # ingère ce qui a changé
    python -m app.ingest --force      # réingère tout
    python -m app.ingest --no-embed   # structure seule, sans appel OpenAI

Le découpage respecte la structure markdown (titres de section), ce qui donne des
chunks sémantiquement cohérents et permet de citer une section précise à
l'utilisateur plutôt qu'un fragment arbitraire.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

from . import db
from .config import KNOWLEDGE_DIR, settings
from .data.activities import ACTIVITIES

logger = logging.getLogger(__name__)

CHUNK_SIZE = 1200
CHUNK_OVERLAP = 150
FRONT_MATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


# --- Lecture des fiches ------------------------------------------------------


def parse_front_matter(text: str) -> tuple[dict[str, Any], str]:
    match = FRONT_MATTER_RE.match(text)
    if not match:
        return {}, text
    import yaml

    meta = yaml.safe_load(match.group(1)) or {}
    return meta, text[match.end() :]


def split_sections(body: str) -> list[tuple[str, str]]:
    """Découpe le markdown par titre de niveau 2, puis en blocs de taille bornée."""
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    sections: list[tuple[str, str]] = []
    current_heading = "Introduction"
    buffer: list[str] = []

    for line in body.splitlines():
        if line.startswith("## "):
            if buffer:
                sections.append((current_heading, "\n".join(buffer).strip()))
                buffer = []
            current_heading = line[3:].strip()
        else:
            buffer.append(line)
    if buffer:
        sections.append((current_heading, "\n".join(buffer).strip()))

    out: list[tuple[str, str]] = []
    for heading, content in sections:
        if not content:
            continue
        for piece in splitter.split_text(content):
            # On préfixe chaque chunk du titre de section : le contexte survit à
            # la découpe, ce qui améliore nettement la qualité des embeddings.
            out.append((heading, f"{heading}\n\n{piece}"))
    return out


# --- Écriture en base --------------------------------------------------------


def upsert_document(meta: dict[str, Any], path: Path, checksum: str) -> tuple[str, bool]:
    """Retourne (document_id, doit_reingerer)."""
    doc_id = meta.get("id") or path.stem
    existing = db.query_one(
        "SELECT id::text, checksum FROM kb_documents WHERE doc_id = %s", (doc_id,)
    )
    row = db.execute_returning(
        """
        INSERT INTO kb_documents
            (doc_id, title, category, evidence_level, targets, up_module,
             duration_min, sources, path, checksum, updated_at)
        VALUES (%(doc_id)s, %(title)s, %(category)s, %(evidence_level)s, %(targets)s,
                %(up_module)s, %(duration_min)s, %(sources)s, %(path)s, %(checksum)s, now())
        ON CONFLICT (doc_id) DO UPDATE SET
            title = EXCLUDED.title,
            category = EXCLUDED.category,
            evidence_level = EXCLUDED.evidence_level,
            targets = EXCLUDED.targets,
            up_module = EXCLUDED.up_module,
            duration_min = EXCLUDED.duration_min,
            sources = EXCLUDED.sources,
            path = EXCLUDED.path,
            checksum = EXCLUDED.checksum,
            updated_at = now()
        RETURNING id::text
        """,
        {
            "doc_id": doc_id,
            "title": meta.get("title") or doc_id,
            "category": meta.get("category"),
            "evidence_level": meta.get("evidence_level"),
            "targets": meta.get("targets") or [],
            "up_module": meta.get("up_module"),
            "duration_min": meta.get("duration_min"),
            "sources": json.dumps(meta.get("sources") or [], ensure_ascii=False),
            "path": str(path.name),
            "checksum": checksum,
        },
    )
    assert row is not None
    changed = existing is None or existing.get("checksum") != checksum
    return row["id"], changed


def replace_chunks(document_id: str, chunks: list[tuple[str, str]], meta: dict[str, Any]) -> None:
    with db.cursor() as cur:
        cur.execute("DELETE FROM kb_chunks WHERE document_id = %s", (document_id,))
        for index, (heading, content) in enumerate(chunks):
            cur.execute(
                """
                INSERT INTO kb_chunks (document_id, chunk_index, heading, content, metadata)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    document_id,
                    index,
                    heading,
                    content,
                    json.dumps(
                        {
                            "doc_id": meta.get("id"),
                            "category": meta.get("category"),
                            "evidence_level": meta.get("evidence_level"),
                            "targets": meta.get("targets") or [],
                        },
                        ensure_ascii=False,
                    ),
                ),
            )


def embed_pending(batch_size: int = 32) -> int:
    """Calcule les embeddings manquants. Retourne le nombre de chunks vectorisés."""
    from .embeddings import embed_documents
    from .search import embedding_cast

    cast = embedding_cast()
    total = 0
    while True:
        rows = db.query_all(
            """
            SELECT id, content FROM kb_chunks
            WHERE embedding IS NULL
            ORDER BY id
            LIMIT %s
            """,
            (batch_size,),
        )
        if not rows:
            break
        vectors = embed_documents([r["content"] for r in rows])
        with db.cursor() as cur:
            for row, vector in zip(rows, vectors, strict=True):
                cur.execute(
                    f"UPDATE kb_chunks SET embedding = %s::{cast} WHERE id = %s",  # noqa: S608
                    (db.to_halfvec(vector), row["id"]),
                )
        total += len(rows)
        logger.info("%s chunks vectorisés (cumul)", total)
    return total


# --- Catalogue d'activités ---------------------------------------------------


def seed_activities() -> int:
    """Insère/actualise le catalogue d'activités (source de vérité : Python)."""
    with db.cursor() as cur:
        for activity in ACTIVITIES:
            cur.execute(
                """
                INSERT INTO activities
                    (slug, title, category, short_label, duration_min, up_module,
                     evidence_level, targets, mechanism, sources, kb_doc_id,
                     instructions, contraindications, is_core, active, updated_at)
                VALUES (%(slug)s, %(title)s, %(category)s, %(short_label)s, %(duration_min)s,
                        %(up_module)s, %(evidence_level)s, %(targets)s, %(mechanism)s,
                        %(sources)s, %(kb_doc_id)s, %(instructions)s, %(contraindications)s,
                        %(is_core)s, true, now())
                ON CONFLICT (slug) DO UPDATE SET
                    title = EXCLUDED.title,
                    category = EXCLUDED.category,
                    short_label = EXCLUDED.short_label,
                    duration_min = EXCLUDED.duration_min,
                    up_module = EXCLUDED.up_module,
                    evidence_level = EXCLUDED.evidence_level,
                    targets = EXCLUDED.targets,
                    mechanism = EXCLUDED.mechanism,
                    sources = EXCLUDED.sources,
                    kb_doc_id = EXCLUDED.kb_doc_id,
                    instructions = EXCLUDED.instructions,
                    contraindications = EXCLUDED.contraindications,
                    is_core = EXCLUDED.is_core,
                    active = true,
                    updated_at = now()
                """,
                {
                    **activity,
                    "sources": json.dumps(activity["sources"], ensure_ascii=False),
                    "instructions": json.dumps(activity["instructions"], ensure_ascii=False),
                },
            )
    return len(ACTIVITIES)


# --- Point d'entrée ----------------------------------------------------------


def ingest(force: bool = False, embed: bool = True) -> dict[str, Any]:
    files = sorted(KNOWLEDGE_DIR.glob("*.md"))
    if not files:
        raise SystemExit(f"Aucune fiche trouvée dans {KNOWLEDGE_DIR}")

    report: dict[str, Any] = {"documents": 0, "reingested": 0, "chunks": 0, "embedded": 0}

    for path in files:
        text = path.read_text(encoding="utf-8")
        checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]
        meta, body = parse_front_matter(text)
        meta.setdefault("id", path.stem)
        document_id, changed = upsert_document(meta, path, checksum)
        report["documents"] += 1

        if not changed and not force:
            continue

        chunks = split_sections(body)
        replace_chunks(document_id, chunks, meta)
        report["reingested"] += 1
        report["chunks"] += len(chunks)
        logger.info("%s → %s chunks", path.name, len(chunks))

    report["activities"] = seed_activities()

    if embed:
        if settings.has_embeddings:
            report["embedded"] = embed_pending()
        else:
            logger.warning(
                "OPENAI_API_KEY absent : chunks stockés sans embedding. "
                "La recherche fonctionnera en mode lexical seul."
            )
    return report


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Ingestion du corpus Sérénité")
    parser.add_argument("--force", action="store_true", help="réingérer toutes les fiches")
    parser.add_argument("--no-embed", action="store_true", help="ne pas appeler OpenAI")
    args = parser.parse_args(argv)

    db.init_db()
    report = ingest(force=args.force, embed=not args.no_embed)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
