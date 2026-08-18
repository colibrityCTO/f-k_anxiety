"""Échelles psychométriques : GAD-7, PHQ-2, évitement.

Le GAD-7 (Spitzer et al., 2006) est libre de reproduction et d'usage. Les seuils,
la sévérité et la différence minimale cliniquement importante sont renvoyés avec
chaque score, avec leur source : l'utilisateur doit savoir d'où vient
l'interprétation de son chiffre.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from .. import db
from ..deps import CurrentUser
from ..schemas import AssessmentIn, AssessmentOut
from ..signals import GAD7_MCID, gad7_severity

router = APIRouter(prefix="/assessments", tags=["assessments"])

RESPONSE_OPTIONS = [
    {"value": 0, "label": "Jamais"},
    {"value": 1, "label": "Plusieurs jours"},
    {"value": 2, "label": "Plus de la moitié du temps"},
    {"value": 3, "label": "Presque tous les jours"},
]

INSTRUMENTS: dict[str, dict[str, Any]] = {
    "gad7": {
        "instrument": "gad7",
        "title": "GAD-7",
        "subtitle": "Sévérité de l'anxiété généralisée",
        "prompt": "Au cours des 2 dernières semaines, à quelle fréquence avez-vous été gêné(e) par les problèmes suivants ?",
        "frequency": "hebdomadaire",
        "options": RESPONSE_OPTIONS,
        "items": [
            "Sentiment de nervosité, d'anxiété ou de tension",
            "Incapacité d'arrêter de vous inquiéter ou de contrôler vos inquiétudes",
            "Inquiétudes excessives à propos de tout et de rien",
            "Difficulté à vous détendre",
            "Agitation telle qu'il est difficile de rester tranquille",
            "Tendance à être facilement contrarié(e) ou irritable",
            "Peur que quelque chose d'épouvantable puisse arriver",
        ],
        "scoring": {
            "range": [0, 21],
            "cutoffs": [
                {"min": 0, "max": 4, "label": "minimale"},
                {"min": 5, "max": 9, "label": "légère"},
                {"min": 10, "max": 14, "label": "modérée"},
                {"min": 15, "max": 21, "label": "sévère"},
            ],
            "mcid": GAD7_MCID,
        },
        "explanation": (
            "Le seuil de 10 sert de seuil de dépistage d'un probable trouble d'anxiété "
            "généralisée (sensibilité 89 %, spécificité 82 %). Une variation de moins de "
            f"{GAD7_MCID} points n'est pas considérée comme un changement cliniquement "
            "significatif : c'est du bruit de mesure. C'est pourquoi l'application ne commente "
            "pas les petites variations."
        ),
        "sources": [
            {
                "label": "Toussaint et al., J Affect Disord 2020 — sensibilité au changement et DMCI du GAD-7",
                "url": "https://pubmed.ncbi.nlm.nih.gov/32090765/",
            },
            {
                "label": "GAD-7 — seuils 5/10/15 et performances diagnostiques",
                "url": "https://www.labvanced.com/content/research/en/questionnaires-and-scales/gad-7-scoring-and-interpretation",
            },
        ],
        "limits": (
            "Outil de dépistage et de suivi, pas de diagnostic. Il capte mal la fréquence des "
            "attaques de panique et l'évitement social, suivis séparément dans l'application."
        ),
    },
    "phq2": {
        "instrument": "phq2",
        "title": "PHQ-2",
        "subtitle": "Dépistage rapide de la dépression",
        "prompt": "Au cours des 2 dernières semaines, à quelle fréquence avez-vous été gêné(e) par les problèmes suivants ?",
        "frequency": "mensuelle",
        "options": RESPONSE_OPTIONS,
        "items": [
            "Peu d'intérêt ou de plaisir à faire les choses",
            "Être triste, déprimé(e) ou désespéré(e)",
        ],
        "scoring": {
            "range": [0, 6],
            "cutoffs": [
                {"min": 0, "max": 2, "label": "dépistage négatif"},
                {"min": 3, "max": 6, "label": "dépistage positif"},
            ],
            "mcid": None,
        },
        "explanation": (
            "L'anxiété et la dépression sont très souvent associées. Un score ≥ 3 justifie d'en "
            "parler à un professionnel : la présence de symptômes dépressifs marqués change la "
            "prise en charge recommandée."
        ),
        "sources": [
            {
                "label": "NICE CG113 — évaluer la comorbidité dépressive dans les troubles anxieux",
                "url": "https://www.nice.org.uk/guidance/cg113/chapter/Recommendations",
            }
        ],
        "limits": "Deux items seulement : c'est un dépistage, en aucun cas un diagnostic.",
    },
    "avoidance": {
        "instrument": "avoidance",
        "title": "Évitement",
        "subtitle": "Suivi du comportement qui entretient l'anxiété",
        "prompt": "Au cours des 7 derniers jours, à quelle fréquence avez-vous fait ceci ?",
        "frequency": "hebdomadaire",
        "options": RESPONSE_OPTIONS,
        "items": [
            "Annuler ou refuser quelque chose à cause de l'anxiété",
            "Y aller, mais accompagné(e) ou en restant près de la sortie",
            "Demander à quelqu'un de me rassurer",
            "Vérifier mes symptômes, mes messages ou des informations pour me rassurer",
            "Préparer excessivement avant une interaction",
        ],
        "scoring": {
            "range": [0, 15],
            "cutoffs": [
                {"min": 0, "max": 3, "label": "faible"},
                {"min": 4, "max": 8, "label": "modéré"},
                {"min": 9, "max": 15, "label": "élevé"},
            ],
            "mcid": None,
        },
        "explanation": (
            "Échelle maison, non validée : elle sert uniquement de suivi personnel. Elle existe "
            "parce que le GAD-7 ne mesure pas l'évitement, alors que c'est le mécanisme central "
            "du maintien de l'anxiété et la cible du module 7."
        ),
        "sources": [
            {
                "label": "Craske et al., Behav Res Ther 2014 — retrait des comportements de sécurité",
                "url": "https://pubmed.ncbi.nlm.nih.gov/24864005/",
            }
        ],
        "limits": (
            "Non validée psychométriquement : à interpréter comme un repère d'évolution "
            "personnelle, pas comme un score comparable à une norme."
        ),
    },
}


def _severity(instrument: str, total: int) -> str:
    if instrument == "gad7":
        return gad7_severity(total)
    for cutoff in INSTRUMENTS[instrument]["scoring"]["cutoffs"]:
        if cutoff["min"] <= total <= cutoff["max"]:
            return str(cutoff["label"])
    return "inconnue"


def _interpretation(instrument: str, total: int, previous: int | None) -> dict[str, Any]:
    meta = INSTRUMENTS[instrument]
    out: dict[str, Any] = {
        "severite": _severity(instrument, total),
        "seuils": meta["scoring"]["cutoffs"],
        "explication": meta["explanation"],
        "sources": meta["sources"],
        "limites": meta["limits"],
        "dmci": meta["scoring"]["mcid"],
    }
    if previous is not None:
        delta = total - previous
        out["precedent"] = previous
        out["delta"] = delta
        mcid = meta["scoring"]["mcid"]
        if mcid is None:
            out["lecture_du_delta"] = (
                f"Variation de {delta:+d} point(s). Aucune DMCI publiée pour cette échelle : "
                "regardez la tendance sur plusieurs mesures plutôt qu'un écart isolé."
            )
        elif delta <= -mcid:
            out["lecture_du_delta"] = (
                f"Baisse de {abs(delta)} points : c'est une amélioration cliniquement "
                f"significative (seuil {mcid})."
            )
        elif delta >= mcid:
            out["lecture_du_delta"] = (
                f"Hausse de {delta} points : c'est une aggravation cliniquement significative "
                f"(seuil {mcid}). Si cela se confirme sur la mesure suivante, parlez-en à un professionnel."
            )
        else:
            out["lecture_du_delta"] = (
                f"Variation de {delta:+d} point(s), inférieure au seuil de {mcid} : à considérer "
                "comme du bruit de mesure, pas comme un progrès ni un recul."
            )
    if instrument == "gad7" and total >= 15:
        out["alerte"] = (
            "Score dans la zone sévère. Les recommandations NICE prévoient à ce niveau une TCC "
            "accompagnée par un professionnel (étape 3) : cette application seule ne suffit pas."
        )
    if instrument == "phq2" and total >= 3:
        out["alerte"] = (
            "Dépistage positif pour des symptômes dépressifs. À évoquer avec un médecin ou un "
            "psychologue : cela modifie la prise en charge indiquée."
        )
    return out


@router.get("/instruments")
def list_instruments(user: CurrentUser) -> dict[str, Any]:
    return {"instruments": list(INSTRUMENTS.values())}


@router.post("", response_model=AssessmentOut)
def submit(payload: AssessmentIn, user: CurrentUser) -> AssessmentOut:
    meta = INSTRUMENTS.get(payload.instrument)
    if meta is None:
        raise HTTPException(status_code=404, detail="Instrument inconnu.")
    if len(payload.items) != len(meta["items"]):
        raise HTTPException(
            status_code=422,
            detail=f"{meta['title']} comporte {len(meta['items'])} items, {len(payload.items)} reçus.",
        )

    taken_on = payload.taken_on or dt.date.today()
    total = sum(payload.items)
    severity = _severity(payload.instrument, total)

    previous_row = db.query_one(
        """
        SELECT total FROM assessments
        WHERE user_id = %s AND instrument = %s AND taken_on < %s
        ORDER BY taken_on DESC LIMIT 1
        """,
        (user["id"], payload.instrument, taken_on),
    )

    row = db.execute_returning(
        """
        INSERT INTO assessments (user_id, instrument, taken_on, items, total, severity)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (user_id, instrument, taken_on) DO UPDATE SET
            items = EXCLUDED.items, total = EXCLUDED.total, severity = EXCLUDED.severity
        RETURNING id::text, instrument, taken_on, items, total, severity
        """,
        (user["id"], payload.instrument, taken_on, payload.items, total, severity),
    )
    assert row is not None
    return AssessmentOut(
        **row,
        interpretation=_interpretation(
            payload.instrument, total, previous_row["total"] if previous_row else None
        ),
    )


@router.get("", response_model=list[AssessmentOut])
def history(
    user: CurrentUser,
    instrument: str | None = None,
    limit: int = Query(default=60, ge=1, le=400),
) -> list[AssessmentOut]:
    rows = db.query_all(
        """
        SELECT id::text, instrument, taken_on, items, total, severity
        FROM assessments
        WHERE user_id = %s AND (%s::text IS NULL OR instrument = %s::text)
        ORDER BY taken_on DESC
        LIMIT %s
        """,
        (user["id"], instrument, instrument, limit),
    )
    out: list[AssessmentOut] = []
    for index, row in enumerate(rows):
        previous = rows[index + 1]["total"] if index + 1 < len(rows) and (
            rows[index + 1]["instrument"] == row["instrument"]
        ) else None
        out.append(
            AssessmentOut(**row, interpretation=_interpretation(row["instrument"], row["total"], previous))
        )
    return out
