"""Check-in quotidien : création/mise à jour et séries temporelles."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, HTTPException, Query

from .. import db
from ..deps import CurrentUser
from ..schemas import CheckinIn, CheckinOut

router = APIRouter(prefix="/checkins", tags=["checkins"])

_UPSERT = """
INSERT INTO daily_checkins
    (user_id, entry_date, moment, anxiety_0_10, anxiety_peak_0_10, mood_0_10,
     sleep_hours, sleep_quality_0_10, sleep_source, bed_time, wake_time,
     caffeine_units, alcohol_units, exercise_min, panic_attacks, avoidance_0_10,
     contexts, main_trigger, note)
VALUES
    (%(user_id)s, %(entry_date)s, %(moment)s, %(anxiety_0_10)s, %(anxiety_peak_0_10)s,
     %(mood_0_10)s, %(sleep_hours)s, %(sleep_quality_0_10)s, %(sleep_source)s,
     %(bed_time)s, %(wake_time)s, %(caffeine_units)s, %(alcohol_units)s,
     %(exercise_min)s, %(panic_attacks)s, %(avoidance_0_10)s, %(contexts)s,
     %(main_trigger)s, %(note)s)
ON CONFLICT (user_id, entry_date, moment) DO UPDATE SET
    -- `coalesce(EXCLUDED, existant)` et non `EXCLUDED` seul pour ces colonnes :
    -- matin et soir sont deux lignes distinctes, mais une correction ne renvoie
    -- que les champs de son écran. Écraser avec NULL effacerait le reste.
    anxiety_0_10 = coalesce(EXCLUDED.anxiety_0_10, daily_checkins.anxiety_0_10),
    anxiety_peak_0_10 = coalesce(EXCLUDED.anxiety_peak_0_10, daily_checkins.anxiety_peak_0_10),
    mood_0_10 = coalesce(EXCLUDED.mood_0_10, daily_checkins.mood_0_10),
    sleep_hours = coalesce(EXCLUDED.sleep_hours, daily_checkins.sleep_hours),
    sleep_quality_0_10 = coalesce(EXCLUDED.sleep_quality_0_10, daily_checkins.sleep_quality_0_10),
    sleep_source = coalesce(EXCLUDED.sleep_source, daily_checkins.sleep_source),
    bed_time = EXCLUDED.bed_time,
    wake_time = EXCLUDED.wake_time,
    caffeine_units = coalesce(EXCLUDED.caffeine_units, daily_checkins.caffeine_units),
    alcohol_units = coalesce(EXCLUDED.alcohol_units, daily_checkins.alcohol_units),
    exercise_min = coalesce(EXCLUDED.exercise_min, daily_checkins.exercise_min),
    panic_attacks = greatest(EXCLUDED.panic_attacks, daily_checkins.panic_attacks),
    avoidance_0_10 = coalesce(EXCLUDED.avoidance_0_10, daily_checkins.avoidance_0_10),
    contexts = EXCLUDED.contexts,
    main_trigger = EXCLUDED.main_trigger,
    note = EXCLUDED.note,
    updated_at = now()
RETURNING id::text, entry_date, moment, anxiety_0_10, anxiety_peak_0_10,
          mood_0_10, sleep_hours, sleep_quality_0_10, sleep_source, bed_time,
          wake_time, caffeine_units, alcohol_units, exercise_min, panic_attacks,
          avoidance_0_10, contexts, main_trigger, note, created_at, updated_at
"""


@router.post("", response_model=CheckinOut)
def upsert_checkin(payload: CheckinIn, user: CurrentUser) -> CheckinOut:
    entry_date = payload.entry_date or dt.date.today()
    if entry_date > dt.date.today():
        raise HTTPException(status_code=422, detail="On ne renseigne pas une date future.")
    if entry_date < dt.date.today() - dt.timedelta(days=60):
        raise HTTPException(
            status_code=422,
            detail="Saisie rétroactive limitée à 60 jours : au-delà, le souvenir est trop reconstruit pour être exploitable.",
        )
    data = payload.model_dump()
    data["entry_date"] = entry_date
    data["user_id"] = user["id"]
    row = db.execute_returning(_UPSERT, data)
    assert row is not None
    return CheckinOut(**row)


@router.get("", response_model=list[CheckinOut])
def list_checkins(
    user: CurrentUser,
    days: int = Query(default=30, ge=1, le=400),
    end: dt.date | None = None,
) -> list[CheckinOut]:
    end_date = end or dt.date.today()
    start = end_date - dt.timedelta(days=days - 1)
    rows = db.query_all(
        """
        SELECT id::text, entry_date, moment, anxiety_0_10, mood_0_10, sleep_hours,
               sleep_quality_0_10, bed_time, wake_time, caffeine_units, alcohol_units,
               exercise_min, panic_attacks, avoidance_0_10, contexts, main_trigger,
               note, created_at, updated_at
        FROM daily_checkins
        WHERE user_id = %s AND entry_date BETWEEN %s AND %s
        ORDER BY entry_date, moment
        """,
        (user["id"], start, end_date),
    )
    return [CheckinOut(**r) for r in rows]


@router.get("/today", response_model=list[CheckinOut])
def today(user: CurrentUser) -> list[CheckinOut]:
    rows = db.query_all(
        """
        SELECT id::text, entry_date, moment, anxiety_0_10, mood_0_10, sleep_hours,
               sleep_quality_0_10, bed_time, wake_time, caffeine_units, alcohol_units,
               exercise_min, panic_attacks, avoidance_0_10, contexts, main_trigger,
               note, created_at, updated_at
        FROM daily_checkins WHERE user_id = %s AND entry_date = CURRENT_DATE
        ORDER BY moment
        """,
        (user["id"],),
    )
    return [CheckinOut(**r) for r in rows]
