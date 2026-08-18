"""Échelle d'expositions : la hiérarchie personnelle de l'utilisateur."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, HTTPException, status

from .. import db
from ..deps import CurrentUser
from ..schemas import ExposureItemIn, ExposureItemOut

router = APIRouter(prefix="/exposures", tags=["exposures"])

_COLUMNS = """
id::text, label, kind, anticipated_anxiety, safety_behaviors, attempts,
last_attempt_on, best_learning, mastered
"""


@router.get("", response_model=list[ExposureItemOut])
def list_items(user: CurrentUser) -> list[ExposureItemOut]:
    rows = db.query_all(
        f"""
        SELECT {_COLUMNS} FROM exposure_items
        WHERE user_id = %s
        ORDER BY mastered, anticipated_anxiety NULLS LAST, created_at
        """,
        (user["id"],),
    )
    return [ExposureItemOut(**r) for r in rows]


@router.post("", response_model=ExposureItemOut, status_code=status.HTTP_201_CREATED)
def create_item(payload: ExposureItemIn, user: CurrentUser) -> ExposureItemOut:
    row = db.execute_returning(
        f"""
        INSERT INTO exposure_items (user_id, label, kind, anticipated_anxiety, safety_behaviors)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING {_COLUMNS}
        """,
        (
            user["id"],
            payload.label,
            payload.kind,
            payload.anticipated_anxiety,
            payload.safety_behaviors,
        ),
    )
    assert row is not None
    return ExposureItemOut(**row)


@router.post("/{item_id}/attempt", response_model=ExposureItemOut)
def record_attempt(
    item_id: str,
    user: CurrentUser,
    learning: str | None = None,
    mastered: bool | None = None,
) -> ExposureItemOut:
    """Enregistre une tentative. `learning` est la phrase d'apprentissage.

    Rappel du modèle d'apprentissage inhibiteur : ce qui compte n'est pas la
    baisse d'anxiété pendant l'exposition mais ce que la personne a appris.
    """
    row = db.execute_returning(
        f"""
        UPDATE exposure_items
        SET attempts = attempts + 1,
            last_attempt_on = %s,
            best_learning = COALESCE(NULLIF(%s, ''), best_learning),
            mastered = COALESCE(%s, mastered)
        WHERE id = %s AND user_id = %s
        RETURNING {_COLUMNS}
        """,
        (dt.date.today(), learning, mastered, item_id, user["id"]),
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Item introuvable.")
    return ExposureItemOut(**row)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(item_id: str, user: CurrentUser) -> None:
    deleted = db.execute(
        "DELETE FROM exposure_items WHERE id = %s AND user_id = %s", (item_id, user["id"])
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Item introuvable.")
