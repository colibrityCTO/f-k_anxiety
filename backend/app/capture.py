"""Extraction de valeurs depuis le français libre.

« nuit pourrie, anxiété 8, j'ai eu une crise dans le métro »
    → {anxiety_0_10: 8, sleep_hours: 5, panic_attacks: 1}

Cette extraction est **déterministe**, et c'est volontaire : les chiffres de
santé ne doivent pas dépendre de l'humeur d'un modèle. Le LLM sert à rédiger la
réponse et à choisir le widget, pas à décider que 8 était en fait 2.

Rien n'est jamais écrit en base à partir de cette extraction : elle ne produit
qu'un **pré-remplissage** que l'utilisateur valide dans le widget. `evidence`
conserve l'extrait de phrase qui a produit chaque valeur, pour pouvoir montrer
d'où elle vient.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

NUMBER_WORDS = {
    "zero": 0, "aucun": 0, "aucune": 0, "un": 1, "une": 1, "deux": 2, "trois": 3,
    "quatre": 4, "cinq": 5, "six": 6, "sept": 7, "huit": 8, "neuf": 9, "dix": 10,
    "onze": 11, "douze": 12, "demi": 1,
}


def _strip_accents(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
    )


def _norm(text: str) -> str:
    return _strip_accents(text.lower())


NUM = r"(\d{1,3}(?:[.,]\d)?|" + "|".join(NUMBER_WORDS) + r")"


def _to_number(raw: str) -> float | None:
    raw = raw.strip()
    if raw in NUMBER_WORDS:
        return float(NUMBER_WORDS[raw])
    try:
        return float(raw.replace(",", "."))
    except ValueError:
        return None


@dataclass
class Capture:
    """Valeurs extraites, avec la trace de ce qui les a produites."""

    values: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, str] = field(default_factory=dict)
    intents: list[str] = field(default_factory=list)
    approximate: list[str] = field(default_factory=list)

    def set(self, key: str, value: Any, why: str, approximate: bool = False) -> None:
        if key in self.values:
            return  # première correspondance gagne : la plus explicite passe d'abord
        self.values[key] = value
        self.evidence[key] = why.strip()
        if approximate:
            self.approximate.append(key)

    @property
    def has_values(self) -> bool:
        return bool(self.values)


# --- Motifs ------------------------------------------------------------------

PATTERNS: list[tuple[str, str, str]] = [
    # (clé, motif sur le texte normalisé, unité)
    ("anxiety_0_10", rf"anxiet\w*\s*(?:a|de|est\s*a|:)?\s*{NUM}\s*(?:/\s*10)?", "0-10"),
    ("anxiety_0_10", rf"(?:angoiss\w*|stress\w*)\s*(?:a|de|:)?\s*{NUM}\s*(?:/\s*10)?", "0-10"),
    ("mood_0_10", rf"humeur\s*(?:a|de|est\s*a|:)?\s*{NUM}\s*(?:/\s*10)?", "0-10"),
    ("mood_0_10", rf"moral\s*(?:a|de|:)?\s*{NUM}\s*(?:/\s*10)?", "0-10"),
    ("sleep_hours", rf"{NUM}\s*(?:h|heures?)\s*(?:de\s*)?(?:sommeil|dormi|de\s*sommeil)", "h"),
    ("sleep_hours", rf"dormi\s*(?:que\s*|environ\s*|a\s*peine\s*)?{NUM}\s*(?:h|heures?)", "h"),
    ("sleep_quality_0_10", rf"(?:qualite\s*(?:du\s*)?sommeil)\s*(?:a|de|:)?\s*{NUM}", "0-10"),
    ("caffeine_units", rf"{NUM}\s*(?:cafes?|expressos?|the?s?|cappuccinos?)", "unités"),
    ("alcohol_units", rf"{NUM}\s*(?:verres?|bieres?|coupes?|pintes?)", "unités"),
    ("exercise_min", rf"{NUM}\s*(?:min|minutes?)\s*(?:de\s*)?(?:sport|marche|course|velo|muscu)", "min"),
    ("exercise_min", rf"(?:sport|couru|marche|nage|velo)\D{{0,12}}{NUM}\s*(?:min|minutes?)", "min"),
    ("avoidance_0_10", rf"evitement\s*(?:a|de|:)?\s*{NUM}", "0-10"),
    ("panic_attacks", rf"{NUM}\s*(?:crises?|attaques?\s*de\s*panique)", "nombre"),
]

# Formulations qualitatives : on pose une valeur plausible et on la marque comme
# approximative — le widget l'affiche pour que l'utilisateur la corrige.
QUALITATIVE: list[tuple[str, str, Any]] = [
    ("sleep_hours", r"nuit\s*blanche|pas\s*(?:du\s*tout\s*)?dormi|aucune?\s*heures?\s*de\s*sommeil", 2),
    ("sleep_hours", r"mal\s*dormi|nuit\s*pourrie|nuit\s*difficile|peu\s*dormi|insomnie", 5),
    ("sleep_hours", r"bien\s*dormi|super\s*nuit|nuit\s*reparatrice", 8),
    ("anxiety_0_10", r"tres\s*(?:anxieu|angoiss|stress)|au\s*bout|panique\s*totale|je\s*craque", 9),
    ("anxiety_0_10", r"(?:plutot\s*)?(?:calme|serein|tranquille|ca\s*va\s*bien)", 2),
    ("mood_0_10", r"deprim|au\s*fond\s*du\s*trou|moral\s*dans\s*les\s*chaussettes", 2),
    ("mood_0_10", r"bonne\s*journee|content|heureu|ca\s*va\s*mieux", 7),
    ("avoidance_0_10", r"j?\s*ai\s*annule|pas\s*(?:pu\s*)?(?:y\s*)?alle|pas\s*sorti|j?\s*ai\s*evite|renonce", 7),
    ("panic_attacks", r"crise\s*(?:d\s*)?(?:angoisse|panique)|attaque\s*de\s*panique|j?\s*ai\s*panique", 1),
]

INTENT_PATTERNS: list[tuple[str, str]] = [
    # `J` couvre « j'ai », « jai », « j ai » : l'apostrophe survit à la
    # normalisation, elle n'est ni un accent ni un espace.
    ("breath", r"respir|calme[rz]?\s*moi|j.?\s*angoisse|ca\s*monte|besoin\s*de\s*souffler"),
    (
        "prevision",
        r"prevision|prevoir|pronostic|prediction|demain|ca\s*va\s*etre\s*comment|"
        r"je\s*vais\s*etre\s*comment|ma\s*charge",
    ),
    ("stats", r"chiffres?|courbe|graphique|statistiques?|evolution|progres|ou\s*j.?\s*en\s*suis"),
    ("analysis", r"comment\s*je\s*vais|bilan|analyse|resume|fais\s*le\s*point|semaine\s*passee"),
    ("gad7", r"\bgad\b|echelle|questionnaire|test\s*d.?\s*anxiete|score"),
    ("sources", r"pourquoi|d.?\s*ou\s*(?:ca\s*)?(?:sort|vient)|preuve|etude|source|comment\s*ca\s*marche"),
    ("journal", r"journal|noter|ecrire|raconter"),
    (
        "jour",
        # `[\s-]*` et non `\s*` : la normalisation retire les accents et met en
        # minuscules, mais elle **garde les tirets** — « qu'est-ce que » ne matchait
        # donc pas un motif qui n'attendait que des espaces.
        r"mon[\s-]*parcours|programme\s*du\s*jour|quoi\s*faire|"
        r"qu.?[\s-]*est[\s-]*ce[\s-]*que\s*je\s*dois|"
        r"mes?\s*(?:exercices?|activites?)\s*(?:du\s*jour|aujourd)",
    ),
    ("checkin", r"check\s*-?\s*in|renseigner|ma\s*journee"),
    # « comment je me sens là » : une mesure instantanée, pas un bilan de journée.
    # Placé après `checkin` mais avant les autres : « là, maintenant » est explicite.
    (
        "maintenant",
        r"(?:la|maintenant|tout\s*de\s*suite|a\s*l.?\s*instant)\s*(?:je|j.?\s*me)|"
        r"je\s*me\s*sens\s*(?:la|maintenant)|comment\s*je\s*me\s*sens\s*(?:la|maintenant)|"
        r"noter\s*(?:mon|un)\s*(?:niveau|chiffre)",
    ),
    (
        "exposition",
        r"exposition|j.?\s*ai\s*ose|j.?\s*ai\s*affronte|affronter|hierarchie|confronter|"
        r"je\s*l.?\s*ai\s*fait",
    ),
    (
        "meditation",
        r"meditation|mediter|scan\s*corporel|pleine\s*conscience|relaxation|me\s*detendre|"
        r"body\s*scan",
    ),
    (
        "memoire",
        r"memoire|historique|la\s*derniere\s*fois|il\s*y\s*a\s*\w+\s*(?:mois|semaines?)|"
        r"retrouve|qu.?\s*est\s*ce\s*que\s*j.?\s*avais|je\s*t.?\s*avais\s*dit",
    ),
    (
        "interoceptif",
        r"interoceptiv|hyperventil|apnee|sensations?\s*(?:physiques?|corporelles?)|"
        r"peur\s*(?:de\s*)?(?:mes\s*)?sensations|mon\s*c(?:oe|œ)ur|palpitations|vertige",
    ),
    (
        "rapport",
        r"rapport|imprimer|pdf|mon\s*medecin|mon\s*psy|psychologue|psychiatre|"
        r"montrer\s*(?:a|au)\s*\w*\s*(?:medecin|psy)",
    ),
]

# Champs bornés à 0-10, pour ne jamais proposer une valeur hors échelle.
BOUNDED = {
    "anxiety_0_10": (0, 10),
    "mood_0_10": (0, 10),
    "avoidance_0_10": (0, 10),
    "sleep_quality_0_10": (0, 10),
    "sleep_hours": (0, 24),
    "caffeine_units": (0, 30),
    "alcohol_units": (0, 40),
    "exercise_min": (0, 600),
    "panic_attacks": (0, 50),
}
INTEGER_FIELDS = {
    "anxiety_0_10", "mood_0_10", "avoidance_0_10", "sleep_quality_0_10",
    "caffeine_units", "alcohol_units", "exercise_min", "panic_attacks",
}


def parse(text: str) -> Capture:
    capture = Capture()
    if not text or not text.strip():
        return capture
    normalised = _norm(text)

    for key, pattern, _unit in PATTERNS:
        match = re.search(pattern, normalised)
        if not match:
            continue
        value = _to_number(match.group(1))
        if value is None:
            continue
        capture.set(key, value, match.group(0))

    for key, pattern, value in QUALITATIVE:
        if key in capture.values:
            continue
        match = re.search(pattern, normalised)
        if match:
            capture.set(key, value, match.group(0), approximate=True)

    # Bornes et arrondis
    for key, value in list(capture.values.items()):
        low, high = BOUNDED.get(key, (None, None))
        if low is not None:
            value = max(low, min(high, float(value)))
        capture.values[key] = int(round(value)) if key in INTEGER_FIELDS else round(float(value), 1)

    for intent, pattern in INTENT_PATTERNS:
        if re.search(pattern, normalised):
            capture.intents.append(intent)

    return capture


def summarise(capture: Capture) -> str:
    """Phrase lisible de ce qui a été compris, pour l'afficher à l'utilisateur."""
    labels = {
        "anxiety_0_10": ("anxiété", "/10"),
        "mood_0_10": ("humeur", "/10"),
        "avoidance_0_10": ("évitement", "/10"),
        "sleep_hours": ("sommeil", " h"),
        "sleep_quality_0_10": ("qualité du sommeil", "/10"),
        "caffeine_units": ("caféine", ""),
        "alcohol_units": ("alcool", ""),
        "exercise_min": ("activité physique", " min"),
        "panic_attacks": ("attaques de panique", ""),
    }
    parts = []
    for key, value in capture.values.items():
        label, unit = labels.get(key, (key, ""))
        approx = " (à vérifier)" if key in capture.approximate else ""
        parts.append(f"{label} {value}{unit}{approx}")
    return ", ".join(parts)
