"""Programme du jour et vue d'ensemble des 12 semaines."""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, Query

from .. import db
from ..deps import CurrentUser
from ..program import MODULES, build_day, ensure_state, module_for_week
from ..schemas import ProgramDayOut

router = APIRouter(prefix="/program", tags=["program"])


@router.get("/today", response_model=ProgramDayOut)
def today(user: CurrentUser, day: dt.date | None = None) -> ProgramDayOut:
    data = build_day(user["id"], user.get("profile") or {}, day)
    return ProgramDayOut(**data)


@router.get("/overview")
def overview(user: CurrentUser) -> dict[str, Any]:
    """Les 8 modules, la position actuelle, et le critère de sortie du programme."""
    state = ensure_state(user["id"])
    week = state["current_week"]
    current = module_for_week(week)

    gad = db.query_all(
        """
        SELECT taken_on, total FROM assessments
        WHERE user_id = %s AND instrument = 'gad7'
        ORDER BY taken_on DESC LIMIT 4
        """,
        (user["id"],),
    )
    remission = len(gad) == 4 and all(row["total"] <= 5 for row in gad)
    open_exposures = db.query_one(
        """
        SELECT count(*) AS n FROM exposure_items
        WHERE user_id = %s AND NOT mastered
        """,
        (user["id"],),
    )

    return {
        "started_on": state["started_on"],
        "current_week": week,
        "current_module": current["module"],
        "status": state["status"],
        "modules": [
            {
                "module": m["module"],
                "weeks": list(m["weeks"]),
                "title": m["title"],
                "goal": m["goal"],
                "explainer": m["explainer"],
                "activities": m["activities"],
                "state": (
                    "termine"
                    if week > m["weeks"][1]
                    else "en_cours"
                    if m["weeks"][0] <= week <= m["weeks"][1]
                    else "a_venir"
                ),
            }
            for m in MODULES
        ],
        "critere_de_sortie": {
            "explication": (
                "Le critère est fixé à l'avance pour éviter de le déplacer indéfiniment. Trois "
                "conditions simultanées, et non une seule."
            ),
            "conditions": [
                {
                    "libelle": "GAD-7 ≤ 5 sur 4 mesures hebdomadaires consécutives (rémission)",
                    "atteinte": remission,
                    "detail": [
                        {"date": str(row["taken_on"]), "total": row["total"]} for row in gad
                    ],
                    "source": {
                        "label": "Seuils du GAD-7 et DMCI de 4 points (Toussaint et al., 2020)",
                        "url": "https://pubmed.ncbi.nlm.nih.gov/32090765/",
                    },
                },
                {
                    "libelle": "Plus d'évitement significatif dans l'échelle d'expositions",
                    "atteinte": bool(open_exposures and int(open_exposures["n"]) == 0),
                    "detail": [{"items_non_maitrises": int(open_exposures["n"]) if open_exposures else 0}],
                    "source": {
                        "label": "Craske et al., 2014 — l'évitement résiduel prédit la rechute",
                        "url": "https://pubmed.ncbi.nlm.nih.gov/24864005/",
                    },
                },
                {
                    "libelle": "Fonctionnement retrouvé dans les domaines qui comptent pour vous",
                    "atteinte": None,
                    "detail": [
                        {
                            "note": "Évaluation subjective : c'est à vous de la déclarer, aucun "
                            "questionnaire ne peut le faire à votre place."
                        }
                    ],
                    "source": {
                        "label": "NICE CG113 — l'objectif de la prise en charge inclut le fonctionnement, pas seulement le score",
                        "url": "https://www.nice.org.uk/guidance/cg113/chapter/Recommendations",
                    },
                },
            ],
            "ensuite": (
                "Quand les trois conditions sont réunies, le programme ne s'arrête pas : il passe "
                "en régime d'entretien (module 8), avec une exposition volontaire par semaine. "
                "C'est ce qui distingue les personnes qui rechutent de celles qui ne rechutent pas."
            ),
        },
    }


@router.get("/history")
def history(
    user: CurrentUser, days: int = Query(default=60, ge=7, le=400)
) -> dict[str, Any]:
    """Séries prêtes à tracer : anxiété, humeur, sommeil, GAD-7, assiduité."""
    start = dt.date.today() - dt.timedelta(days=days - 1)
    daily = db.query_all(
        """
        SELECT entry_date,
               avg(anxiety_0_10)::numeric(4,2)   AS anxiete,
               avg(mood_0_10)::numeric(4,2)      AS humeur,
               max(sleep_hours)                  AS sommeil_h,
               max(sleep_quality_0_10)           AS sommeil_qualite,
               max(caffeine_units)               AS cafeine,
               max(alcohol_units)                AS alcool,
               max(exercise_min)                 AS sport_min,
               sum(panic_attacks)                AS paniques,
               max(avoidance_0_10)               AS evitement
        FROM daily_checkins
        WHERE user_id = %s AND entry_date >= %s
        GROUP BY entry_date ORDER BY entry_date
        """,
        (user["id"], start),
    )
    gad = db.query_all(
        """
        SELECT taken_on, total, severity FROM assessments
        WHERE user_id = %s AND instrument = 'gad7' AND taken_on >= %s
        ORDER BY taken_on
        """,
        (user["id"], start),
    )
    adherence = db.query_all(
        """
        SELECT entry_date,
               count(*) FILTER (WHERE status IN ('fait','partiel')) AS faites,
               count(*) AS total
        FROM activity_logs
        WHERE user_id = %s AND entry_date >= %s
        GROUP BY entry_date ORDER BY entry_date
        """,
        (user["id"], start),
    )
    return {"quotidien": daily, "gad7": gad, "assiduite": adherence}
