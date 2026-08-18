"""Catalogue d'activités et journal de réalisation (fait / pas fait)."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, HTTPException, Query

from .. import db
from ..deps import CurrentUser
from ..schemas import ActivityLogIn, ActivityLogOut, ActivityOut

router = APIRouter(prefix="/activities", tags=["activities"])

_ACTIVITY_COLUMNS = """
slug, title, category, short_label, duration_min, up_module, evidence_level,
targets, mechanism, sources, kb_doc_id, instructions, contraindications, is_core
"""


@router.get("", response_model=list[ActivityOut])
def list_activities(
    user: CurrentUser,
    category: str | None = None,
    up_module: int | None = None,
) -> list[ActivityOut]:
    rows = db.query_all(
        f"""
        SELECT {_ACTIVITY_COLUMNS} FROM activities
        WHERE active
          AND (%s::text IS NULL OR category = %s::text)
          AND (%s::int IS NULL OR up_module = %s::int)
        ORDER BY up_module, category, title
        """,
        (category, category, up_module, up_module),
    )
    return [ActivityOut(**r) for r in rows]


@router.get("/logs", response_model=list[ActivityLogOut])
def list_logs(
    user: CurrentUser,
    days: int = Query(default=30, ge=1, le=400),
) -> list[ActivityLogOut]:
    start = dt.date.today() - dt.timedelta(days=days - 1)
    rows = db.query_all(
        """
        SELECT id::text, activity_slug, entry_date, status, duration_min,
               anxiety_before, anxiety_after, skip_reason, notes, created_at
        FROM activity_logs
        WHERE user_id = %s AND entry_date >= %s
        ORDER BY entry_date DESC
        """,
        (user["id"], start),
    )
    return [ActivityLogOut(**r) for r in rows]


@router.post("/logs", response_model=ActivityLogOut)
def upsert_log(payload: ActivityLogIn, user: CurrentUser) -> ActivityLogOut:
    exists = db.query_one(
        "SELECT 1 FROM activities WHERE slug = %s AND active", (payload.activity_slug,)
    )
    if exists is None:
        raise HTTPException(status_code=404, detail="Activité inconnue.")

    data = payload.model_dump()
    data["entry_date"] = payload.entry_date or dt.date.today()
    data["user_id"] = user["id"]
    row = db.execute_returning(
        """
        INSERT INTO activity_logs
            (user_id, activity_slug, entry_date, status, duration_min,
             anxiety_before, anxiety_after, skip_reason, notes)
        VALUES (%(user_id)s, %(activity_slug)s, %(entry_date)s, %(status)s, %(duration_min)s,
                %(anxiety_before)s, %(anxiety_after)s, %(skip_reason)s, %(notes)s)
        ON CONFLICT (user_id, activity_slug, entry_date) DO UPDATE SET
            status = EXCLUDED.status,
            duration_min = EXCLUDED.duration_min,
            anxiety_before = EXCLUDED.anxiety_before,
            anxiety_after = EXCLUDED.anxiety_after,
            skip_reason = EXCLUDED.skip_reason,
            notes = EXCLUDED.notes
        RETURNING id::text, activity_slug, entry_date, status, duration_min,
                  anxiety_before, anxiety_after, skip_reason, notes, created_at
        """,
        data,
    )
    assert row is not None
    return ActivityLogOut(**row)


@router.get("/{slug}", response_model=ActivityOut)
def get_activity(slug: str, user: CurrentUser) -> ActivityOut:
    row = db.query_one(
        f"SELECT {_ACTIVITY_COLUMNS} FROM activities WHERE slug = %s", (slug,)
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Activité inconnue.")
    return ActivityOut(**row)
