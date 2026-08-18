"""Exercices d'exposition intéroceptive.

Provoquer volontairement, en sécurité, les sensations redoutées, pour apprendre
qu'elles sont désagréables mais **non dangereuses**. C'est le traitement de
référence de la sensibilité anxieuse — la peur de ses propres sensations — qui est
le cœur du trouble panique.

Les durées et la liste des exercices viennent de Schmidt & Trakowski (2004) et du
module « When Panic Attacks » du Centre for Clinical Interventions. Quatre
exercices (hyperventilation, paille, apnée, rotation) représentaient la majorité
des séances dans l'étude descriptive, et la majorité de ces séances entraînaient
une baisse de l'anxiété au cours de la séance.

Nuance conservée telle quelle : la respiration à la paille, souvent utilisée pour
les sensations digestives, n'a **pas** montré d'effet significatif sur les peurs
gastro-intestinales dans cette étude. Elle reste proposée pour l'essoufflement.
"""

from __future__ import annotations

from typing import Any

# Conditions qui imposent un avis médical avant de commencer. Cette liste n'est
# pas un ornement : elle est validée une fois par l'utilisateur, et la validation
# est datée et conservée dans son profil.
CONTRAINDICATIONS: list[str] = [
    "une maladie cardiaque",
    "une maladie respiratoire, dont l'asthme",
    "de l'épilepsie",
    "une hypertension non contrôlée",
    "un glaucome",
    "un antécédent d'AVC",
    "une grossesse",
    "une blessure au cou ou au dos",
    "un trouble de l'oreille interne",
    "un diabète mal équilibré",
]

EXERCISES: list[dict[str, Any]] = [
    {
        "slug": "hyperventilation",
        "name": "Hyperventilation volontaire",
        "seconds": 60,
        "how": "Respire vite et profondément, par la bouche, sans t'arrêter.",
        "sensations": ["vertige", "picotements", "irréalité", "oppression"],
        "evidence": "A",
        "note": "L'exercice le mieux documenté : effet démontré sur les peurs de type pseudo-neurologique.",
    },
    {
        "slug": "apnee",
        "name": "Apnée",
        "seconds": 30,
        "how": "Inspire normalement, puis retiens ta respiration le plus longtemps possible.",
        "sensations": ["oppression thoracique", "manque d'air"],
        "evidence": "A",
        "note": None,
    },
    {
        "slug": "paille",
        "name": "Respiration dans une paille",
        "seconds": 90,
        "how": "Pince-toi le nez et respire uniquement dans une paille fine.",
        "sensations": ["souffle court", "étouffement"],
        "evidence": "B",
        "note": (
            "Pas d'effet significatif retrouvé sur les peurs gastro-intestinales dans l'étude de "
            "Schmidt & Trakowski. Utile pour l'essoufflement."
        ),
    },
    {
        "slug": "rotation",
        "name": "Rotation sur une chaise",
        "seconds": 60,
        "how": "Tourne sur une chaise pivotante, ou sur toi-même, à vitesse constante.",
        "sensations": ["vertige", "nausée"],
        "evidence": "A",
        "note": "Arrête-toi assis, pas debout.",
    },
    {
        "slug": "escaliers",
        "name": "Escaliers ou 50 sauts",
        "seconds": 60,
        "how": "Monte des escaliers rapidement, ou fais 50 sauts sur place.",
        "sensations": ["cœur rapide", "essoufflement", "chaleur"],
        "evidence": "A",
        "note": "Ce sont exactement les sensations que produit l'exercice physique quotidien.",
    },
    {
        "slug": "tension",
        "name": "Tension musculaire totale",
        "seconds": 60,
        "how": "Contracte tous les muscles du corps en même temps et tiens.",
        "sensations": ["tremblements", "faiblesse", "jambes molles"],
        "evidence": "B",
        "note": None,
    },
    {
        "slug": "fixation",
        "name": "Fixation d'un point",
        "seconds": 90,
        "how": "Fixe un point au mur sans bouger les yeux, puis regarde autour de toi.",
        "sensations": ["irréalité", "déréalisation"],
        "evidence": "B",
        "note": None,
    },
    {
        "slug": "secouer-tete",
        "name": "Secouer la tête",
        "seconds": 30,
        "how": "Secoue la tête d'un côté à l'autre, yeux ouverts.",
        "sensations": ["étourdissement", "vision floue"],
        "evidence": "B",
        "note": None,
    },
]

EXERCISES_BY_SLUG = {exercise["slug"]: exercise for exercise in EXERCISES}

SOURCES = [
    {
        "label": "Schmidt & Trakowski, 2004 — évaluation et exposition intéroceptives dans le trouble panique",
        "url": "https://anxietyinstitute.com/wp-content/uploads/2021/12/Schmidt-_-Trakowski-2004.pdf",
    },
    {
        "label": "Lee et al., BMC Psychiatry 2006 — hypersensibilité et exposition intéroceptives : spécificité et efficacité",
        "url": "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC1559685/",
    },
    {
        "label": "Centre for Clinical Interventions — When Panic Attacks, module 4 : faire face aux alarmes physiques",
        "url": "https://www.cci.health.wa.gov.au/~/media/CCI/Consumer-Modules/When-Panic-Attacks/When-Panic-Attacks---Module-4---Coping-with-Physical-Alarms.pdf",
    },
    {
        "label": "Craske et al., Behav Res Ther 2014 — violation d'attente et retrait des comportements de sécurité",
        "url": "https://pubmed.ncbi.nlm.nih.gov/24864005/",
    },
]

MECHANISM = (
    "L'apprentissage ne vient pas de la baisse d'anxiété pendant l'exercice, mais de la "
    "violation d'attente : l'écart entre ta prédiction (« je vais m'évanouir ») et ce qui arrive "
    "réellement. D'où l'ordre imposé — prédiction écrite avant, exercice fait en entier sans "
    "l'écourter, une minute de plus avec les sensations, puis constat écrit. Répété 3 à 5 fois, "
    "l'anxiété initiale tombe nettement ; l'objectif n'est pas que l'exercice devienne agréable."
)
