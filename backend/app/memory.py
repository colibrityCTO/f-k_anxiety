"""Mémoire personnelle vectorisée : tout l'historique de l'utilisateur, pour toujours.

Principe : chaque objet produit par l'utilisateur (check-in, entrée de journal,
échelle, activité, message du fil, analyse) est rendu en une ligne de texte
lisible, embeddé, et conservé dans `user_chunks` — définitivement, sans fenêtre
glissante ni troncature.

Ce que cela garantit, et ce que cela ne garantit pas :

- **Rien n'est oublié.** Un check-in de mars reste interrogeable en décembre.
- **Les textes anciens sont retrouvables** par recherche sémantique, sans limite
  d'ancienneté : c'est la raison d'être de cette table.
- **Les chiffres ne passent pas par ici.** Ils sont recalculés exactement par
  `signals.py` sur l'historique entier — une moyenne ne doit jamais dépendre de
  ce qu'une recherche vectorielle a bien voulu remonter.

La fenêtre de contexte d'un modèle reste finie : on n'y colle pas six mois de
données brutes. On y met les chiffres exacts, les extraits pertinents retrouvés
ici, et les derniers tours de conversation.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from typing import Any

from . import db
from .config import settings

logger = logging.getLogger(__name__)

RRF_K = 60

SOURCE_LABELS = {
    "checkin": "Check-in",
    "journal": "Journal",
    "assessment": "Échelle",
    "activity": "Activité",
    "message": "Conversation",
    "insight": "Analyse",
}


# --- Rendus texte ------------------------------------------------------------
#
# Un rendu doit être auto-suffisant : la date, les valeurs et leur unité. C'est
# ce texte qui sera embeddé, et c'est lui que l'assistant relira des mois plus
# tard — s'il manque le contexte, l'extrait est inutilisable.


def render_checkin(row: dict[str, Any]) -> str:
    parts: list[str] = []

    def add(label: str, value: Any, unit: str = "") -> None:
        if value is not None:
            parts.append(f"{label} {value}{unit}")

    add("anxiété", row.get("anxiety_0_10"), "/10")
    add("humeur", row.get("mood_0_10"), "/10")
    add("évitement", row.get("avoidance_0_10"), "/10")
    add("sommeil", row.get("sleep_hours"), " h")
    add("qualité du sommeil", row.get("sleep_quality_0_10"), "/10")
    add("caféine", row.get("caffeine_units"), " unités")
    add("alcool", row.get("alcohol_units"), " unités")
    add("activité physique", row.get("exercise_min"), " min")
    if row.get("panic_attacks"):
        parts.append(f"{row['panic_attacks']} attaque(s) de panique")
    if row.get("contexts"):
        parts.append("contextes : " + ", ".join(row["contexts"]))
    text = f"Check-in du {row.get('entry_date')} — " + ", ".join(parts) + "."
    if row.get("main_trigger"):
        text += f" Déclencheur principal : {row['main_trigger']}."
    if row.get("note"):
        text += f" Note : {row['note']}"
    return text


def render_journal(row: dict[str, Any]) -> str:
    kind = row.get("kind", "libre")
    text = f"Journal ({kind}) du {row.get('entry_date')}."
    if row.get("situation"):
        text += f" Situation : {row['situation']}."
    if row.get("emotions"):
        text += f" Émotions : {', '.join(row['emotions'])}."
    if row.get("body_sensations"):
        text += f" Sensations : {', '.join(row['body_sensations'])}."
    if row.get("intensity_before") is not None:
        text += f" Intensité avant {row['intensity_before']}/10"
        if row.get("intensity_after") is not None:
            text += f", après {row['intensity_after']}/10"
        text += "."
    if row.get("automatic_thought"):
        text += f" Pensée automatique : « {row['automatic_thought']} »."
    if row.get("thinking_trap"):
        text += f" Piège de pensée : {row['thinking_trap']}."
    if row.get("evidence_against"):
        text += f" Preuves contre : {row['evidence_against']}."
    if row.get("coping_plan"):
        text += f" Plan si ça arrive : {row['coping_plan']}."
    if row.get("alternative_thought"):
        text += f" Pensée alternative : « {row['alternative_thought']} »."
    if row.get("prediction"):
        text += f" Prédiction : « {row['prediction']} »"
        if row.get("prediction_probability") is not None:
            text += f" ({row['prediction_probability']} %)"
        text += "."
    if row.get("actual_outcome"):
        text += f" Ce qui est arrivé : {row['actual_outcome']}."
    if row.get("learning"):
        text += f" Appris : {row['learning']}."
    if row.get("safety_behaviors_dropped"):
        text += f" Comportements de sécurité retirés : {', '.join(row['safety_behaviors_dropped'])}."
    if row.get("worry_text"):
        actionable = row.get("worry_actionable")
        nature = "actionnable" if actionable else "hypothétique" if actionable is False else "non triée"
        text += f" Inquiétude ({nature}) : {row['worry_text']}."
    if row.get("next_action"):
        text += f" Action décidée : {row['next_action']}."
    if row.get("free_text"):
        text += f" {row['free_text']}"
    return text


def render_assessment(row: dict[str, Any]) -> str:
    return (
        f"Échelle {str(row.get('instrument', '')).upper()} du {row.get('taken_on')} : "
        f"score {row.get('total')}"
        + (f" ({row['severity']})" if row.get("severity") else "")
        + f". Items : {row.get('items')}."
    )


def render_activity(row: dict[str, Any]) -> str:
    text = (
        f"Activité « {row.get('title') or row.get('activity_slug')} » du "
        f"{row.get('entry_date')} : {row.get('status')}"
    )
    if row.get("anxiety_before") is not None and row.get("anxiety_after") is not None:
        text += f", anxiété {row['anxiety_before']} → {row['anxiety_after']}"
    if row.get("skip_reason"):
        text += f". Raison de non-réalisation : {row['skip_reason']}"
    if row.get("notes"):
        text += f". Note : {row['notes']}"
    return text + "."


def render_message(role: str, content: str, when: dt.date | None = None) -> str:
    who = "L'utilisateur a écrit" if role == "user" else "Réponse de l'assistant"
    date = f" le {when}" if when else ""
    return f"{who}{date} : {content}"


def render_insight(row: dict[str, Any]) -> str:
    return (
        f"Analyse du {row.get('period_start')} au {row.get('period_end')} — "
        f"{row.get('headline') or ''}\n{row.get('body') or ''}"
    )


# --- Écriture ----------------------------------------------------------------


def remember(
    user_id: str,
    source_kind: str,
    source_id: str,
    content: str,
    entry_date: dt.date | str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Enregistre (ou met à jour) un souvenir et calcule son embedding.

    Conçue pour être appelée en tâche de fond (`BackgroundTasks`) : l'appel
    d'embedding prend quelques centaines de millisecondes et ne doit pas ralentir
    l'enregistrement d'un check-in. Ne lève jamais : une mémoire manquante
    dégrade la pertinence, elle ne doit pas casser une écriture de donnée.
    """
    content = (content or "").strip()
    if not content:
        return
    try:
        row = db.execute_returning(
            """
            INSERT INTO user_chunks (user_id, source_kind, source_id, entry_date, content, metadata)
            VALUES (%(user_id)s, %(kind)s, %(sid)s, %(date)s, %(content)s, %(meta)s)
            ON CONFLICT (user_id, source_kind, source_id) DO UPDATE SET
                content = EXCLUDED.content,
                entry_date = EXCLUDED.entry_date,
                metadata = EXCLUDED.metadata,
                embedding = NULL
            RETURNING id
            """,
            {
                "user_id": user_id,
                "kind": source_kind,
                "sid": str(source_id),
                "date": entry_date,
                "content": content,
                "meta": json.dumps(metadata or {}, ensure_ascii=False, default=str),
            },
        )
        if row is None:
            return
        if not settings.has_embeddings:
            return  # la recherche lexicale reste opérationnelle

        from .embeddings import embed_query
        from .search import embedding_cast

        vector = embed_query(content)
        db.execute(
            f"UPDATE user_chunks SET embedding = %s::{embedding_cast()} WHERE id = %s",  # noqa: S608
            (db.to_halfvec(vector), row["id"]),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Mémoire non enregistrée (%s/%s) : %s", source_kind, source_id, exc)


def embed_pending(user_id: str | None = None, batch_size: int = 32) -> int:
    """Vectorise les souvenirs en attente. Utile après ajout d'une clé d'API."""
    if not settings.has_embeddings:
        return 0
    from .embeddings import embed_documents
    from .search import embedding_cast

    cast = embedding_cast()
    total = 0
    while True:
        rows = db.query_all(
            """
            SELECT id, content FROM user_chunks
            WHERE embedding IS NULL AND (%s::uuid IS NULL OR user_id = %s::uuid)
            ORDER BY id LIMIT %s
            """,
            (user_id, user_id, batch_size),
        )
        if not rows:
            break
        vectors = embed_documents([r["content"] for r in rows])
        with db.cursor() as cur:
            for row, vector in zip(rows, vectors, strict=True):
                cur.execute(
                    f"UPDATE user_chunks SET embedding = %s::{cast} WHERE id = %s",  # noqa: S608
                    (db.to_halfvec(vector), row["id"]),
                )
        total += len(rows)
    return total


# --- Recherche ---------------------------------------------------------------

_SEARCH_SQL = """
WITH scoped AS (
    SELECT id, embedding FROM user_chunks
    WHERE user_id = %(user_id)s
      AND (%(kinds)s::text[] IS NULL OR source_kind = ANY(%(kinds)s::text[]))
),
vec AS (
    SELECT s.id,
           row_number() OVER (ORDER BY s.embedding <=> %(embedding)s::{cast}) AS rnk,
           1 - (s.embedding <=> %(embedding)s::{cast}) AS similarity
    FROM scoped s
    WHERE %(embedding)s IS NOT NULL AND s.embedding IS NOT NULL
    ORDER BY s.embedding <=> %(embedding)s::{cast}
    LIMIT %(candidates)s
),
lex AS (
    SELECT c.id,
           row_number() OVER (ORDER BY ts_rank_cd(c.tsv, q.query) DESC) AS rnk
    FROM user_chunks c
    JOIN scoped s ON s.id = c.id
    CROSS JOIN websearch_to_tsquery('french', %(query_text)s) AS q(query)
    WHERE c.tsv @@ q.query
    ORDER BY ts_rank_cd(c.tsv, q.query) DESC
    LIMIT %(candidates)s
),
merged AS (SELECT id FROM vec UNION SELECT id FROM lex)
SELECT c.id, c.source_kind, c.source_id, c.entry_date, c.content, c.metadata,
       v.similarity, v.rnk AS vector_rank, l.rnk AS lexical_rank,
       COALESCE(1.0 / (%(rrf_k)s + v.rnk), 0) + COALESCE(1.0 / (%(rrf_k)s + l.rnk), 0) AS rrf_score
FROM merged m
JOIN user_chunks c ON c.id = m.id
LEFT JOIN vec v ON v.id = m.id
LEFT JOIN lex l ON l.id = m.id
ORDER BY rrf_score DESC, c.entry_date DESC NULLS LAST
LIMIT %(k)s
"""


def search(
    user_id: str,
    query_text: str,
    *,
    kinds: list[str] | None = None,
    k: int = 8,
    candidates: int = 40,
) -> list[dict[str, Any]]:
    """Recherche hybride dans la mémoire personnelle, sans limite d'ancienneté."""
    from .embeddings import try_embed_query
    from .search import embedding_cast, lexical_query

    embedding = try_embed_query(query_text)
    params = {
        "user_id": user_id,
        "kinds": kinds or None,
        "embedding": db.to_halfvec(embedding) if embedding else None,
        "query_text": lexical_query(query_text),
        "candidates": candidates,
        "k": k,
        "rrf_k": RRF_K,
    }
    try:
        rows = db.query_all(_SEARCH_SQL.format(cast=embedding_cast()), params)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Recherche mémoire impossible : %s", exc)
        return []
    for row in rows:
        row["mode"] = "hybride" if embedding else "lexical"
    return rows


def recent(user_id: str, limit: int = 12, kinds: list[str] | None = None) -> list[dict[str, Any]]:
    """Derniers souvenirs, pour amorcer le contexte même sans requête."""
    return db.query_all(
        """
        SELECT source_kind, source_id, entry_date, content
        FROM user_chunks
        WHERE user_id = %s AND (%s::text[] IS NULL OR source_kind = ANY(%s::text[]))
        ORDER BY entry_date DESC NULLS LAST, id DESC
        LIMIT %s
        """,
        (user_id, kinds or None, kinds or None, limit),
    )


def stats(user_id: str) -> dict[str, Any]:
    rows = db.query_all(
        """
        SELECT source_kind,
               count(*) AS n,
               count(embedding) AS vectorises,
               min(entry_date) AS depuis
        FROM user_chunks WHERE user_id = %s GROUP BY source_kind ORDER BY source_kind
        """,
        (user_id,),
    )
    return {
        "par_source": rows,
        "total": sum(int(r["n"]) for r in rows),
        "vectorises": sum(int(r["vectorises"]) for r in rows),
    }


def format_for_prompt(rows: list[dict[str, Any]]) -> str:
    """Met en forme des souvenirs pour le prompt, avec leur date et leur nature."""
    if not rows:
        return "(aucun élément d'historique retrouvé)"
    lines = []
    for row in rows:
        label = SOURCE_LABELS.get(row["source_kind"], row["source_kind"])
        date = row.get("entry_date") or "date inconnue"
        lines.append(f"- [{label} · {date}] {row['content']}")
    return "\n".join(lines)


# --- Reprise de l'existant ---------------------------------------------------


def backfill(user_id: str) -> dict[str, int]:
    """Indexe les données déjà présentes en base pour un utilisateur.

    Nécessaire pour un compte créé avant l'introduction de la mémoire, et
    idempotent : relancer ne crée pas de doublon (contrainte unique).
    """
    counts = {"checkin": 0, "journal": 0, "assessment": 0, "activity": 0, "insight": 0}

    for row in db.query_all(
        "SELECT * FROM daily_checkins WHERE user_id = %s ORDER BY entry_date", (user_id,)
    ):
        remember(
            user_id, "checkin", str(row["id"]), render_checkin(row), row["entry_date"],
            {"moment": row.get("moment")},
        )
        counts["checkin"] += 1

    for row in db.query_all(
        "SELECT * FROM journal_entries WHERE user_id = %s ORDER BY entry_date", (user_id,)
    ):
        remember(
            user_id, "journal", str(row["id"]), render_journal(row), row["entry_date"],
            {"kind": row.get("kind")},
        )
        counts["journal"] += 1

    for row in db.query_all(
        "SELECT * FROM assessments WHERE user_id = %s ORDER BY taken_on", (user_id,)
    ):
        remember(
            user_id, "assessment", str(row["id"]), render_assessment(row), row["taken_on"],
            {"instrument": row.get("instrument"), "total": row.get("total")},
        )
        counts["assessment"] += 1

    for row in db.query_all(
        """
        SELECT l.*, a.title FROM activity_logs l
        JOIN activities a ON a.slug = l.activity_slug
        WHERE l.user_id = %s ORDER BY l.entry_date
        """,
        (user_id,),
    ):
        remember(
            user_id, "activity", str(row["id"]), render_activity(row), row["entry_date"],
            {"slug": row.get("activity_slug"), "status": row.get("status")},
        )
        counts["activity"] += 1

    for row in db.query_all(
        "SELECT * FROM insights WHERE user_id = %s ORDER BY created_at", (user_id,)
    ):
        remember(
            user_id, "insight", str(row["id"]), render_insight(row), row["period_end"],
            {"scope": row.get("scope"), "engine": row.get("engine")},
        )
        counts["insight"] += 1

    return counts
