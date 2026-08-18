"""Journal : entrées libres, journaux de pensées, expositions, inquiétudes."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, HTTPException, Query, status

from .. import db
from ..deps import CurrentUser
from ..schemas import JournalIn, JournalOut

router = APIRouter(prefix="/journal", tags=["journal"])

_COLUMNS = """
id::text, entry_date, kind, situation, emotions, body_sensations,
intensity_before, intensity_after, belief_before_0_100, belief_after_0_100,
similarity_0_10, automatic_thought, thinking_trap,
evidence_for, evidence_against, coping_plan, alternative_thought,
prediction, prediction_probability, actual_outcome, learning,
safety_behaviors_dropped, worry_text, worry_actionable, next_action,
free_text, created_at
"""


@router.post("", response_model=JournalOut, status_code=status.HTTP_201_CREATED)
def create_entry(payload: JournalIn, user: CurrentUser) -> JournalOut:
    data = payload.model_dump()
    data["entry_date"] = payload.entry_date or dt.date.today()
    data["user_id"] = user["id"]

    # Une entrée d'exposition sans prédiction perd tout son intérêt : c'est
    # l'écart prédiction/réalité qui produit l'apprentissage (Craske et al.).
    if payload.kind == "exposition" and not (payload.prediction or payload.actual_outcome):
        raise HTTPException(
            status_code=422,
            detail=(
                "Une exposition doit comporter au moins la prédiction ou le résultat réel : "
                "c'est l'écart entre les deux qui produit l'apprentissage."
            ),
        )

    row = db.execute_returning(
        f"""
        INSERT INTO journal_entries
            (user_id, entry_date, kind, situation, emotions, body_sensations,
             intensity_before, intensity_after, belief_before_0_100, belief_after_0_100,
             similarity_0_10, automatic_thought, thinking_trap,
             evidence_for, evidence_against, coping_plan, alternative_thought,
             prediction, prediction_probability, actual_outcome, learning,
             safety_behaviors_dropped, worry_text, worry_actionable, next_action, free_text)
        VALUES
            (%(user_id)s, %(entry_date)s, %(kind)s, %(situation)s, %(emotions)s,
             %(body_sensations)s, %(intensity_before)s, %(intensity_after)s,
             %(belief_before_0_100)s, %(belief_after_0_100)s, %(similarity_0_10)s,
             %(automatic_thought)s, %(thinking_trap)s, %(evidence_for)s,
             %(evidence_against)s, %(coping_plan)s, %(alternative_thought)s,
             %(prediction)s, %(prediction_probability)s, %(actual_outcome)s, %(learning)s,
             %(safety_behaviors_dropped)s, %(worry_text)s, %(worry_actionable)s,
             %(next_action)s, %(free_text)s)
        RETURNING {_COLUMNS}
        """,
        data,
    )
    assert row is not None
    return JournalOut(**row)


@router.get("", response_model=list[JournalOut])
def list_entries(
    user: CurrentUser,
    kind: str | None = None,
    days: int = Query(default=60, ge=1, le=400),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[JournalOut]:
    start = dt.date.today() - dt.timedelta(days=days - 1)
    rows = db.query_all(
        f"""
        SELECT {_COLUMNS} FROM journal_entries
        WHERE user_id = %s AND entry_date >= %s
          AND (%s::text IS NULL OR kind = %s::text)
        ORDER BY entry_date DESC, created_at DESC
        LIMIT %s
        """,
        (user["id"], start, kind, kind, limit),
    )
    return [JournalOut(**r) for r in rows]


@router.patch("/{entry_id}", response_model=JournalOut)
def update_entry(entry_id: str, payload: JournalIn, user: CurrentUser) -> JournalOut:
    existing = db.query_one(
        "SELECT id FROM journal_entries WHERE id = %s AND user_id = %s", (entry_id, user["id"])
    )
    if existing is None:
        raise HTTPException(status_code=404, detail="Entrée introuvable.")
    data = payload.model_dump()
    data["entry_date"] = payload.entry_date or dt.date.today()
    data["id"] = entry_id
    data["user_id"] = user["id"]
    row = db.execute_returning(
        f"""
        UPDATE journal_entries SET
            entry_date = %(entry_date)s, kind = %(kind)s, situation = %(situation)s,
            emotions = %(emotions)s, body_sensations = %(body_sensations)s,
            intensity_before = %(intensity_before)s, intensity_after = %(intensity_after)s,
            belief_before_0_100 = %(belief_before_0_100)s,
            belief_after_0_100 = %(belief_after_0_100)s,
            automatic_thought = %(automatic_thought)s, thinking_trap = %(thinking_trap)s,
            evidence_for = %(evidence_for)s, evidence_against = %(evidence_against)s,
            coping_plan = %(coping_plan)s, alternative_thought = %(alternative_thought)s,
            prediction = %(prediction)s, prediction_probability = %(prediction_probability)s,
            actual_outcome = %(actual_outcome)s, learning = %(learning)s,
            safety_behaviors_dropped = %(safety_behaviors_dropped)s,
            worry_text = %(worry_text)s, worry_actionable = %(worry_actionable)s,
            next_action = %(next_action)s, free_text = %(free_text)s,
            updated_at = now()
        WHERE id = %(id)s AND user_id = %(user_id)s
        RETURNING {_COLUMNS}
        """,
        data,
    )
    assert row is not None
    return JournalOut(**row)


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_entry(entry_id: str, user: CurrentUser) -> None:
    deleted = db.execute(
        "DELETE FROM journal_entries WHERE id = %s AND user_id = %s", (entry_id, user["id"])
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Entrée introuvable.")
