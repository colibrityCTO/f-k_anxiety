"""Schémas Pydantic : contrat d'API entre le backend et le frontend."""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

# --- Auth -------------------------------------------------------------------


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=72)
    display_name: str | None = Field(default=None, max_length=80)
    timezone: str = "Europe/Paris"

    @field_validator("password")
    @classmethod
    def _strength(cls, v: str) -> str:
        if v.lower() in {"motdepasse", "password123", "1234567890"}:
            raise ValueError("Mot de passe trop courant.")
        return v


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: "UserOut"


class UserOut(BaseModel):
    id: str
    email: str
    display_name: str | None = None
    timezone: str = "Europe/Paris"
    ai_consent: bool = True
    profile: dict[str, Any] = Field(default_factory=dict)
    created_at: dt.datetime | None = None


class ProfileUpdateIn(BaseModel):
    """Ce qu'un compte peut modifier de lui-même.

    `ai_consent` n'y figure pas : l'IA est active pour tout le monde et ne se
    coupe pas. Le champ reste exposé en lecture dans `UserOut` — c'est un état
    du compte, plus un réglage — mais aucune requête ne peut le remettre à
    false, sinon l'interrupteur retiré de l'interface reviendrait par l'API.
    """

    display_name: str | None = Field(default=None, max_length=80)
    timezone: str | None = None
    profile: dict[str, Any] | None = None


# --- Check-in ---------------------------------------------------------------


class CheckinIn(BaseModel):
    entry_date: dt.date | None = None
    moment: Literal["matin", "soir"] = "soir"
    anxiety_0_10: int | None = Field(default=None, ge=0, le=10)
    # Le pic du jour, distinct de la moyenne : sous anxiété, la mémoire retient les
    # pires moments, donc une « moyenne » rétrospective est en réalité un pic.
    anxiety_peak_0_10: int | None = Field(default=None, ge=0, le=10)
    mood_0_10: int | None = Field(default=None, ge=0, le=10)
    sleep_hours: float | None = Field(default=None, ge=0, le=24)
    # D'où vient la durée de sommeil : déclarée, lue sur un capteur, ou rectifiée
    # par l'utilisateur. Mélanger les trois rendrait toute corrélation illisible.
    sleep_source: Literal["declare", "capteur", "corrige"] | None = None
    sleep_quality_0_10: int | None = Field(default=None, ge=0, le=10)
    bed_time: dt.time | None = None
    wake_time: dt.time | None = None
    caffeine_units: int | None = Field(default=None, ge=0, le=30)
    alcohol_units: int | None = Field(default=None, ge=0, le=40)
    exercise_min: int | None = Field(default=None, ge=0, le=600)
    panic_attacks: int = Field(default=0, ge=0, le=50)
    avoidance_0_10: int | None = Field(default=None, ge=0, le=10)
    contexts: list[str] = Field(default_factory=list)
    main_trigger: str | None = Field(default=None, max_length=500)
    note: str | None = Field(default=None, max_length=5000)


class CheckinOut(CheckinIn):
    id: str
    entry_date: dt.date
    created_at: dt.datetime | None = None
    updated_at: dt.datetime | None = None


# --- Journal ----------------------------------------------------------------

JournalKind = Literal["libre", "pensee", "exposition", "inquietude"]


class JournalIn(BaseModel):
    entry_date: dt.date | None = None
    kind: JournalKind = "libre"
    situation: str | None = Field(default=None, max_length=4000)
    emotions: list[str] = Field(default_factory=list)
    body_sensations: list[str] = Field(default_factory=list)
    intensity_before: int | None = Field(default=None, ge=0, le=10)
    intensity_after: int | None = Field(default=None, ge=0, le=10)
    automatic_thought: str | None = Field(default=None, max_length=4000)
    thinking_trap: str | None = None
    evidence_for: str | None = Field(default=None, max_length=4000)
    evidence_against: str | None = Field(default=None, max_length=4000)
    coping_plan: str | None = Field(default=None, max_length=4000)
    alternative_thought: str | None = Field(default=None, max_length=4000)
    prediction: str | None = Field(default=None, max_length=2000)
    prediction_probability: int | None = Field(default=None, ge=0, le=100)
    # Journal de pensées en trois colonnes : à combien j'y crois, avant / après.
    belief_before_0_100: int | None = Field(default=None, ge=0, le=100)
    belief_after_0_100: int | None = Field(default=None, ge=0, le=100)
    # Intéroceptif : ressemblance des sensations provoquées à celles des crises.
    similarity_0_10: int | None = Field(default=None, ge=0, le=10)
    actual_outcome: str | None = Field(default=None, max_length=4000)
    learning: str | None = Field(default=None, max_length=2000)
    safety_behaviors_dropped: list[str] = Field(default_factory=list)
    worry_text: str | None = Field(default=None, max_length=4000)
    worry_actionable: bool | None = None
    next_action: str | None = Field(default=None, max_length=1000)
    free_text: str | None = Field(default=None, max_length=20000)


class JournalOut(JournalIn):
    id: str
    entry_date: dt.date
    created_at: dt.datetime | None = None


# --- Activités --------------------------------------------------------------


class SourceRef(BaseModel):
    label: str
    url: str | None = None


class ActivityOut(BaseModel):
    slug: str
    title: str
    category: str
    short_label: str | None = None
    duration_min: int
    up_module: int
    evidence_level: str
    targets: list[str] = Field(default_factory=list)
    mechanism: str
    sources: list[SourceRef] = Field(default_factory=list)
    kb_doc_id: str | None = None
    instructions: list[str] = Field(default_factory=list)
    contraindications: str | None = None
    is_core: bool = False


class ActivityLogIn(BaseModel):
    activity_slug: str
    entry_date: dt.date | None = None
    status: Literal["fait", "partiel", "pas_fait", "reporte"]
    duration_min: int | None = Field(default=None, ge=0, le=600)
    anxiety_before: int | None = Field(default=None, ge=0, le=10)
    anxiety_after: int | None = Field(default=None, ge=0, le=10)
    skip_reason: str | None = Field(default=None, max_length=1000)
    notes: str | None = Field(default=None, max_length=4000)


class ActivityLogOut(ActivityLogIn):
    id: str
    entry_date: dt.date
    created_at: dt.datetime | None = None
    # En lecture seulement. `propose` est posé par le serveur quand `build_day`
    # calcule le programme du jour ; il reste absent de `ActivityLogIn`, sans quoi un
    # client pourrait se déclarer « proposé » et fausser sa propre assiduité.
    status: Literal["propose", "fait", "partiel", "pas_fait", "reporte"]


# --- Échelles ---------------------------------------------------------------


class AssessmentIn(BaseModel):
    instrument: Literal["gad7", "phq2", "avoidance"] = "gad7"
    taken_on: dt.date | None = None
    items: list[int]

    @field_validator("items")
    @classmethod
    def _range(cls, v: list[int]) -> list[int]:
        if not v:
            raise ValueError("Aucune réponse fournie.")
        if any(i < 0 or i > 3 for i in v):
            raise ValueError("Chaque item doit être coté de 0 à 3.")
        return v


class AssessmentOut(BaseModel):
    id: str
    instrument: str
    taken_on: dt.date
    items: list[int]
    total: int
    severity: str | None = None
    # Interprétation explicite renvoyée avec le score : seuils, DMCI, source.
    interpretation: dict[str, Any] = Field(default_factory=dict)


# --- Expositions ------------------------------------------------------------


class ExposureItemIn(BaseModel):
    label: str = Field(max_length=300)
    kind: Literal["in_vivo", "interoceptif", "imaginaire"] = "in_vivo"
    anticipated_anxiety: int | None = Field(default=None, ge=0, le=10)
    safety_behaviors: list[str] = Field(default_factory=list)


class ExposureItemOut(ExposureItemIn):
    id: str
    attempts: int = 0
    last_attempt_on: dt.date | None = None
    best_learning: str | None = None
    mastered: bool = False


# --- Programme --------------------------------------------------------------


class ProgramItem(BaseModel):
    activity: ActivityOut
    slot: Literal["socle", "corps", "module", "adaptatif"]
    # Le widget que cet item ouvre, ou `null` s'il n'y a rien à ouvrir (conseil
    # d'hygiène). Sans ce champ, le parcours du jour serait une liste à lire.
    widget: str | None = None
    # Le « pourquoi pour vous » : la raison personnalisée, avec ses données.
    why_for_you: str
    triggered_by: list[dict[str, Any]] = Field(default_factory=list)
    # `propose` : calculé par `build_day` et pas encore fait. C'est ce statut qui donne
    # un dénominateur à l'assiduité — sans lui, seuls des « fait » étaient enregistrés
    # et la part des activités réalisées valait 100 % en permanence.
    status: Literal["propose", "fait", "partiel", "pas_fait", "reporte"] | None = None
    log: ActivityLogOut | None = None


class ProgramDayOut(BaseModel):
    entry_date: dt.date
    week: int
    module: int
    module_title: str
    module_goal: str
    phase_explainer: str
    items: list[ProgramItem]
    checkin_done: bool
    adherence_7j: float
    streak: int
    gad7_due: bool
    # Jours réellement pratiqués, à côté de la semaine calendaire : la progression
    # est calendaire, et l'écart entre les deux est une information, pas un défaut.
    jours_pratiques: int = 0
    notices: list[str] = Field(default_factory=list)


# --- Analyse IA -------------------------------------------------------------


class InsightOut(BaseModel):
    id: str
    scope: str
    period_start: dt.date
    period_end: dt.date
    headline: str | None = None
    body: str
    signals: dict[str, Any] = Field(default_factory=dict)
    citations: list[dict[str, Any]] = Field(default_factory=list)
    recommendations: list[dict[str, Any]] = Field(default_factory=list)
    engine: str
    risk_flag: bool = False
    created_at: dt.datetime | None = None


class AnalyzeIn(BaseModel):
    scope: Literal["quotidien", "hebdomadaire"] = "quotidien"
    end_date: dt.date | None = None


class ChatIn(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    # Contexte optionnel : id d'activité ou d'insight sur lequel porte la question
    about_activity: str | None = None
    include_my_data: bool = True


# --- Bibliothèque -----------------------------------------------------------


class KbDocOut(BaseModel):
    doc_id: str
    title: str
    category: str | None = None
    evidence_level: str | None = None
    targets: list[str] = Field(default_factory=list)
    up_module: int | None = None
    duration_min: int | None = None
    sources: list[SourceRef] = Field(default_factory=list)


class KbDocDetailOut(KbDocOut):
    content: str


TokenOut.model_rebuild()
