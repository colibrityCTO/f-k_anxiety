"""Moteur du programme quotidien.

Un seul programme, pas de modules séparés par diagnostic : c'est la logique du
Protocole Unifié (Barlow), validée par essai randomisé d'équivalence contre les
protocoles spécifiques au trouble panique, à l'anxiété généralisée et à l'anxiété
sociale. Les particularités de chacun sont traitées par la **couche adaptative**,
qui ajoute des activités en fonction de ce que les données montrent.

Chaque item de la journée porte trois éléments :
  - `slot` : socle (tous les jours), module (semaine en cours), adaptatif (déclenché) ;
  - `why_for_you` : la raison personnalisée, en français, avec les chiffres ;
  - `triggered_by` : les observations exactes qui l'ont déclenché.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from . import db, signals as signals_mod

# --- Progression sur 12 semaines --------------------------------------------

MODULES: list[dict[str, Any]] = [
    {
        "module": 1,
        "weeks": (1, 1),
        "title": "Se repérer et se motiver",
        "goal": "Poser une ligne de base chiffrée et clarifier ce que tu veux retrouver.",
        "explainer": (
            "On ne commence pas par des exercices, on commence par mesurer. C'est l'étape 1 des "
            "recommandations NICE pour l'anxiété généralisée (« éducation et suivi actif ») : "
            "sans ligne de base, tu ne pourras pas savoir plus tard si quelque chose a marché. "
            "Cette semaine, le programme est volontairement léger."
        ),
        "activities": ["objectifs-valeurs", "regularite-sommeil", "gad7-hebdo"],
    },
    {
        "module": 2,
        "weeks": (2, 2),
        "title": "Comprendre le mécanisme",
        "goal": "Découper tes épisodes d'anxiété en trois composantes et voir ton cycle de maintien.",
        "explainer": (
            "Le module 2 du Protocole Unifié. Objectif : que tu puisses expliquer ta propre "
            "anxiété avec tes mots et tes exemples. C'est ce qui rendra les modules suivants "
            "acceptables — notamment les expositions, qui n'ont aucun sens si le cycle "
            "évitement → soulagement → aggravation n'est pas clair."
        ),
        "activities": ["psychoeducation-cycle", "activite-physique", "gad7-hebdo"],
    },
    {
        "module": 3,
        "weeks": (3, 4),
        "title": "Observer sans fuir",
        "goal": "Apprendre à rester avec une émotion et à faire redescendre l'activation physiologique.",
        "explainer": (
            "Deux outils complémentaires. La respiration lente et la relaxation agissent sur le "
            "corps (activité vagale, tension musculaire) ; la conscience émotionnelle agit sur la "
            "relation à l'émotion. C'est aussi la préparation indispensable aux expositions : on "
            "ne peut pas s'exposer à ce qu'on ne sait pas observer."
        ),
        "activities": ["conscience-emotionnelle", "scan-corporel", "relaxation-musculaire", "meditation-souffle"],
    },
    {
        "module": 4,
        "weeks": (5, 6),
        "title": "Assouplir les pensées",
        "goal": "Repérer les deux pièges de pensée et tester des interprétations alternatives.",
        "explainer": (
            "Le Protocole Unifié réduit les distorsions cognitives à deux pièges : surestimer la "
            "probabilité, et catastrophiser. La seconde question — « et si c'était vrai, comment "
            "je ferais face ? » — est la plus utile et la plus négligée : elle reste valable même "
            "si le scénario redouté finit par arriver."
        ),
        "activities": ["journal-pensees", "meditation-souffle", "gad7-hebdo"],
    },
    {
        "module": 5,
        "weeks": (7, 7),
        "title": "Repérer ce qui entretient le problème",
        "goal": "Inventorier évitements, réassurance et comportements de sécurité, et commencer à en retirer.",
        "explainer": (
            "La semaine la plus révélatrice. Tant qu'un comportement de sécurité est présent, "
            "ton cerveau garde une explication alternative disponible et la prédiction "
            "catastrophique n'est jamais mise à l'épreuve. C'est pourquoi le retrait des signaux "
            "de sécurité figure parmi les stratégies fondamentales d'optimisation de l'exposition "
            "(Craske et al., 2014)."
        ),
        "activities": ["inventaire-securite", "temps-inquietude", "resolution-problemes"],
    },
    {
        "module": 6,
        "weeks": (8, 8),
        "title": "Apprivoiser les sensations",
        "goal": "Provoquer volontairement les sensations redoutées pour apprendre qu'elles ne sont pas dangereuses.",
        "explainer": (
            "Exposition intéroceptive. Tu écris ta prédiction avant, tu fais "
            "l'exercice en entier, tu notes ce qui s'est réellement passé. L'apprentissage ne "
            "vient pas de la baisse d'anxiété pendant l'exercice mais de l'écart entre ta "
            "prédiction et le résultat. Lis les contre-indications avant de commencer."
        ),
        "activities": ["exposition-interoceptive", "scan-corporel", "gad7-hebdo"],
    },
    {
        "module": 7,
        "weeks": (9, 11),
        "title": "Affronter, pour de vrai",
        "goal": "Gravir ton échelle d'expositions, sans comportements de sécurité, en variant les contextes.",
        "explainer": (
            "Le module qui produit l'essentiel du changement durable. La question n'est plus "
            "« est-ce que mon anxiété est descendue ? » mais « qu'est-ce que j'ai appris que je ne "
            "savais pas ? ». On répète chaque item 3 à 5 fois, dans des lieux et à des heures "
            "différents, parce que la variabilité contextuelle est l'un des deux leviers dont "
            "l'effet est le mieux démontré."
        ),
        "activities": ["echelle-exposition", "exposition-in-vivo", "experience-sociale", "exposition-imaginaire"],
    },
    {
        "module": 8,
        "weeks": (12, 99),
        "title": "Consolider",
        "goal": "Écrire ton plan de maintien et passer en régime d'entretien.",
        "explainer": (
            "Ce qui distingue les personnes qui rechutent de celles qui ne rechutent pas, c'est de "
            "continuer les expositions après la guérison : l'évitement se réinstalle "
            "silencieusement, par petites décisions confortables. Le régime d'entretien conserve "
            "donc une exposition volontaire par semaine, même quand tout va bien."
        ),
        "activities": ["plan-prevention-rechute", "exposition-in-vivo", "gad7-hebdo"],
    },
]


def module_for_week(week: int) -> dict[str, Any]:
    for module in MODULES:
        low, high = module["weeks"]
        if low <= week <= high:
            return module
    return MODULES[-1]


# --- État du programme -------------------------------------------------------


def ensure_state(user_id: str) -> dict[str, Any]:
    state = db.query_one("SELECT * FROM program_state WHERE user_id = %s", (user_id,))
    if state is None:
        state = db.execute_returning(
            """
            INSERT INTO program_state (user_id) VALUES (%s)
            ON CONFLICT (user_id) DO UPDATE SET updated_at = now()
            RETURNING *
            """,
            (user_id,),
        )
        assert state is not None
    return state


def recompute_week(user_id: str, today: dt.date | None = None) -> dict[str, Any]:
    """Fait avancer la semaine du programme.

    Règle volontairement simple et explicable : une semaine calendaire écoulée
    depuis le début de la semaine en cours fait passer à la suivante. On ne
    bloque pas la progression sur l'assiduité — bloquer transformerait un outil
    de soin en système de punition, ce qui est le meilleur moyen de faire
    abandonner l'utilisateur. L'assiduité est en revanche affichée et commentée.
    """
    today = today or dt.date.today()
    state = ensure_state(user_id)
    week_started = state["week_started_on"]
    elapsed = (today - week_started).days
    if elapsed >= 7 and state["status"] == "actif":
        advance = elapsed // 7
        new_week = state["current_week"] + advance
        new_module = module_for_week(new_week)["module"]
        state = db.execute_returning(
            """
            UPDATE program_state
            SET current_week = %s,
                current_module = %s,
                week_started_on = week_started_on + (%s * INTERVAL '7 days'),
                updated_at = now()
            WHERE user_id = %s
            RETURNING *
            """,
            (new_week, new_module, advance, user_id),
        )
        assert state is not None

    return _apply_maintenance(state, today)


# --- Mode entretien ----------------------------------------------------------


def remission_state(user_id: str) -> dict[str, Any]:
    """Le critère de sortie, calculé, sans marge d'interprétation.

    Trois conditions simultanées — le critère est fixé à l'avance précisément pour
    ne pas être déplacé au fil du temps :

    1. GAD-7 ≤ 5 sur les 4 dernières mesures hebdomadaires (rémission) ;
    2. plus aucun item non maîtrisé dans l'échelle d'expositions ;
    3. fonctionnement retrouvé — déclaratif, et donc jamais coché automatiquement.
    """
    gad = db.query_all(
        """
        SELECT taken_on, total FROM assessments
        WHERE user_id = %s AND instrument = 'gad7' ORDER BY taken_on DESC LIMIT 4
        """,
        (user_id,),
    )
    remaining = db.query_one(
        "SELECT count(*) AS n FROM exposure_items WHERE user_id = %s AND NOT mastered",
        (user_id,),
    )
    open_items = int(remaining["n"]) if remaining else 0
    gad_ok = len(gad) == 4 and all(row["total"] <= 5 for row in gad)
    # Rechute : le score repasse au moins 4 points (la DMCI) au-dessus du seuil de
    # rémission. En dessous, c'est du bruit de mesure, pas une rechute.
    relapse = bool(gad) and gad[0]["total"] >= 5 + 4

    return {
        "gad7_ok": gad_ok,
        "gad7_mesures": [{"date": str(r["taken_on"]), "total": r["total"]} for r in gad],
        "expositions_ok": open_items == 0,
        "expositions_restantes": open_items,
        "remission": gad_ok and open_items == 0,
        "rechute_probable": relapse,
    }


def _apply_maintenance(state: dict[str, Any], today: dt.date) -> dict[str, Any]:
    """Bascule automatique entre programme actif et régime d'entretien."""
    user_id = state["user_id"]
    criterion = remission_state(user_id)

    target = state["status"]
    if state["status"] == "actif" and criterion["remission"]:
        target = "entretien"
    elif state["status"] == "entretien" and criterion["rechute_probable"]:
        target = "actif"

    if target != state["status"]:
        updated = db.execute_returning(
            """
            UPDATE program_state SET status = %s, week_started_on = %s, updated_at = now()
            WHERE user_id = %s RETURNING *
            """,
            (target, today, user_id),
        )
        if updated is not None:
            state = updated
    state["critere"] = criterion
    return state


# --- Couche adaptative -------------------------------------------------------


def _obs(signal: dict[str, Any] | None, limit: int = 5) -> list[dict[str, Any]]:
    if not signal:
        return []
    return [
        {
            "signal": signal["id"],
            "libelle": signal["label"],
            "valeur": signal.get("value"),
            "verdict": signal.get("verdict"),
            "methode": signal.get("method"),
            "donnees": signal.get("observations", [])[:limit],
        }
    ]


def adaptive_items(sig: dict[str, Any], profile: dict[str, Any]) -> list[dict[str, Any]]:
    """Règles adaptatives. Chaque règle retourne slug + justification + preuves.

    Les seuils sont explicites et documentés : l'utilisateur doit pouvoir
    comprendre exactement pourquoi une activité lui est proposée aujourd'hui.
    """
    out: list[dict[str, Any]] = []
    get = lambda sid: signals_mod.signal_by_id(sig, sid)  # noqa: E731

    # 1. Sommeil
    sleep_corr = get("correlation_sommeil_anxiete")
    quality_corr = get("correlation_qualite_sommeil")
    for corr in (sleep_corr, quality_corr):
        if corr and corr.get("value") is not None and corr["value"] <= -0.4:
            out.append(
                {
                    "slug": "regularite-sommeil",
                    "why": (
                        f"Sur tes {corr['n']} nuits enregistrées, {corr['label'].lower()} : "
                        f"corrélation de {corr['value']} ({corr['verdict']}). Chez toi, le "
                        "sommeil est donc un levier — et c'est souvent le plus facile à saisir, "
                        "parce que les règles sont concrètes et vérifiables."
                    ),
                    "triggered_by": _obs(corr, limit=8),
                }
            )
            break

    # 2. Attaques de panique récentes → exposition intéroceptive
    panic = get("attaques_panique")
    if panic and isinstance(panic.get("value"), int) and panic["value"] > 0:
        out.append(
            {
                "slug": "exposition-interoceptive",
                "why": (
                    f"T'as enregistré {panic['value']} attaque(s) de panique sur la période. "
                    "Le traitement de référence de la peur des sensations corporelles est "
                    "l'exposition intéroceptive : provoquer volontairement ces sensations, en "
                    "sécurité, pour que ton cerveau apprenne qu'elles ne sont pas dangereuses."
                ),
                "triggered_by": _obs(panic),
            }
        )

    # 3. Évitement élevé → expositions
    avoidance = get("evitement")
    if avoidance and avoidance.get("value") is not None and avoidance["value"] >= 5:
        out.append(
            {
                "slug": "exposition-in-vivo",
                "why": (
                    f"Ton évitement moyen déclaré est de {avoidance['value']}/10 "
                    f"({avoidance['verdict']}). L'évitement est le moteur du maintien de "
                    "l'anxiété : c'est la cible la plus rentable, et la seule qui produise un "
                    "changement durable."
                ),
                "triggered_by": _obs(avoidance, limit=8),
            }
        )

    # 4. Caféine
    caffeine = get("correlation_cafeine_anxiete")
    if caffeine and caffeine.get("value") is not None and caffeine["value"] >= 0.35:
        out.append(
            {
                "slug": "reduction-cafeine",
                "why": (
                    f"Tes jours les plus caféinés sont aussi tes jours les plus anxieux "
                    f"(corrélation {caffeine['value']}, {caffeine['n']} jours). Une corrélation "
                    "n'est pas une preuve de causalité, mais c'est un test simple et peu coûteux "
                    "à faire sur deux semaines."
                ),
                "triggered_by": _obs(caffeine, limit=8),
            }
        )

    # 5. Sédentarité
    sport = get("correlation_sport_anxiete")
    if sport is not None and sport.get("n", 0) >= 3 and not any(
        (o.get("sport_min") or 0) >= 20 for o in sport.get("observations", [])
    ):
        out.append(
            {
                "slug": "activite-physique",
                "why": (
                    "Aucune journée avec au moins 20 minutes d'activité physique sur la période. "
                    "L'exercice a un double intérêt ici : effet propre sur l'anxiété, et "
                    "exposition intéroceptive naturelle aux sensations que tu redoutes "
                    "(cœur rapide, essoufflement, chaleur)."
                ),
                "triggered_by": _obs(sport, limit=8),
            }
        )

    # 6. Anxiété en hausse → outils de régulation renforcés
    trend = get("tendance_anxiete")
    if trend and trend.get("delta") is not None and trend["delta"] >= 0.7:
        out.append(
            {
                "slug": "temps-inquietude",
                "why": (
                    f"Ton anxiété moyenne a augmenté de {trend['delta']} point sur les 7 "
                    "derniers jours par rapport aux 7 précédents. Quand l'inquiétude prend de la "
                    "place, la contenir dans un créneau fixe évite qu'elle colonise la journée. "
                    "Niveau de preuve B : outil d'appoint, à évaluer sur tes propres données."
                ),
                "triggered_by": _obs(trend),
            }
        )

    # 7. Adhérence faible → on allège plutôt que d'ajouter
    adherence = get("adherence")
    if adherence and adherence.get("value") is not None and adherence["value"] < 0.4:
        out.append(
            {
                "slug": "soupir-physiologique",
                "why": (
                    f"Ton taux de réalisation est de {round(adherence['value'] * 100)} %. "
                    "Plutôt que d'ajouter des exercices, le programme propose aujourd'hui le plus "
                    "court (3 minutes) : reprendre la régularité compte davantage que le volume. "
                    "Les activités non faites ne sont pas un échec, elles indiquent seulement que "
                    "le format ne convient pas."
                ),
                "triggered_by": _obs(adherence),
            }
        )

    # 8. Difficulté sociale déclarée à l'inscription
    social_flag = profile.get("difficultes", [])
    if isinstance(social_flag, list) and "social" in social_flag:
        out.append(
            {
                "slug": "experience-sociale",
                "why": (
                    "T'as indiqué les situations sociales comme difficulté principale. "
                    "L'ingrédient spécifique ici n'est pas seulement d'y aller, mais de diriger "
                    "l'attention vers l'extérieur : tant que tu t'observes de l'intérieur, "
                    "tu ne peux pas recueillir la preuve que rien de grave ne s'est produit."
                ),
                "triggered_by": [
                    {
                        "signal": "profil_utilisateur",
                        "libelle": "Difficulté déclarée à l'inscription",
                        "valeur": "social",
                        "methode": "réponse au questionnaire initial",
                        "donnees": [],
                    }
                ],
            }
        )

    # Dédoublonnage en conservant le premier déclenchement (le plus prioritaire)
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for item in out:
        if item["slug"] in seen:
            continue
        seen.add(item["slug"])
        unique.append(item)
    return unique[:4]


# --- Construction de la journée ---------------------------------------------


def _activities_by_slug(slugs: list[str]) -> dict[str, dict[str, Any]]:
    if not slugs:
        return {}
    rows = db.query_all(
        """
        SELECT slug, title, category, short_label, duration_min, up_module,
               evidence_level, targets, mechanism, sources, kb_doc_id,
               instructions, contraindications, is_core
        FROM activities
        WHERE slug = ANY(%s) AND active
        """,
        (slugs,),
    )
    return {r["slug"]: r for r in rows}


def build_day(user_id: str, profile: dict[str, Any], day: dt.date | None = None) -> dict[str, Any]:
    day = day or dt.date.today()
    state = recompute_week(user_id, day)
    week = state["current_week"]
    module = module_for_week(week)

    sig = signals_mod.compute(user_id, end_date=day, days=21)

    # Socle quotidien : les trois activités faites tous les jours.
    core_slugs = ["checkin-quotidien", "respiration-lente-10", "journal-libre"]
    module_slugs = list(module["activities"])
    adaptive = adaptive_items(sig, profile or {})

    # Le GAD-7 n'est proposé que s'il est dû (une fois par semaine).
    last_gad = db.query_one(
        """
        SELECT taken_on FROM assessments
        WHERE user_id = %s AND instrument = 'gad7'
        ORDER BY taken_on DESC LIMIT 1
        """,
        (user_id,),
    )
    gad7_due = last_gad is None or (day - last_gad["taken_on"]).days >= 7
    if not gad7_due:
        module_slugs = [s for s in module_slugs if s != "gad7-hebdo"]

    all_slugs = core_slugs + module_slugs + [a["slug"] for a in adaptive]
    catalogue = _activities_by_slug(all_slugs)

    logs = {
        r["activity_slug"]: r
        for r in db.query_all(
            """
            SELECT id::text, activity_slug, entry_date, status, duration_min,
                   anxiety_before, anxiety_after, skip_reason, notes, created_at
            FROM activity_logs WHERE user_id = %s AND entry_date = %s
            """,
            (user_id, day),
        )
    }

    items: list[dict[str, Any]] = []

    def _add(slug: str, slot: str, why: str, triggered_by: list[dict[str, Any]]) -> None:
        activity = catalogue.get(slug)
        if activity is None:
            return
        log = logs.get(slug)
        items.append(
            {
                "activity": activity,
                "slot": slot,
                "why_for_you": why,
                "triggered_by": triggered_by,
                "status": log["status"] if log else None,
                "log": log,
            }
        )

    for slug in core_slugs:
        _add(
            slug,
            "socle",
            {
                "checkin-quotidien": (
                    "Le socle du suivi. Sans mesure quotidienne, impossible de savoir si quelque "
                    "chose marche chez toi : la mémoire, sous anxiété, ne retient que les "
                    "pires moments. Deux minutes."
                ),
                "respiration-lente-10": (
                    "À faire tous les jours, à froid, comme un entraînement de fond : l'effet sur "
                    "le tonus vagal se construit sur des semaines, pas en une séance."
                ),
                "journal-libre": (
                    "Quelques lignes suffisent. Ce sont tes mots qui permettront à l'analyse de "
                    "repérer tes schémas récurrents — et de te les montrer."
                ),
            }.get(slug, "Activité du socle quotidien."),
            [],
        )

    for slug in module_slugs:
        _add(
            slug,
            "module",
            f"Semaine {week}, module {module['module']} — {module['title']}. {module['goal']}",
            [
                {
                    "signal": "progression_programme",
                    "libelle": f"Semaine {week} du programme",
                    "valeur": f"module {module['module']}",
                    "verdict": module["title"],
                    "methode": "progression calendaire du Protocole Unifié sur 12 semaines",
                    "donnees": [
                        {"debut_programme": str(state["started_on"]), "semaine_en_cours": week}
                    ],
                }
            ],
        )

    for item in adaptive:
        _add(item["slug"], "adaptatif", item["why"], item["triggered_by"])

    # Assiduité et série
    adherence_signal = signals_mod.signal_by_id(sig, "adherence")
    adherence_7j = 0.0
    rows = db.query_all(
        """
        SELECT status, count(*) AS n FROM activity_logs
        WHERE user_id = %s AND entry_date > %s GROUP BY status
        """,
        (user_id, day - dt.timedelta(days=7)),
    )
    total = sum(int(r["n"]) for r in rows)
    if total:
        done = sum(int(r["n"]) for r in rows if r["status"] in {"fait", "partiel"})
        adherence_7j = round(done / total, 3)

    streak_rows = db.query_all(
        """
        SELECT DISTINCT entry_date FROM daily_checkins
        WHERE user_id = %s AND entry_date <= %s
        ORDER BY entry_date DESC LIMIT 400
        """,
        (user_id, day),
    )
    streak = 0
    expected = day
    for row in streak_rows:
        if row["entry_date"] == expected:
            streak += 1
            expected -= dt.timedelta(days=1)
        elif row["entry_date"] < expected:
            break

    checkin_done = bool(streak_rows and streak_rows[0]["entry_date"] == day)

    notices: list[str] = []
    if sig["drapeaux_rouges"]:
        notices.append(
            "Des formulations inquiétantes ont été repérées dans tes entrées récentes. "
            "Cette application n'est pas l'outil adapté : en France, le 3114 est joignable "
            "gratuitement 24 h/24."
        )
    if week == 1:
        notices.append(
            "Première semaine : l'objectif est uniquement de mesurer. Ne cherchez pas encore à "
            "changer quoi que ce soit — t'as besoin d'une ligne de base."
        )
    if adherence_signal and adherence_signal.get("value") is not None and adherence_signal["value"] < 0.4:
        notices.append(
            "Programme allégé aujourd'hui : mieux vaut trois minutes tenues qu'une heure prévue "
            "et non faite."
        )

    return {
        "entry_date": day,
        "week": week,
        "module": module["module"],
        "module_title": module["title"],
        "module_goal": module["goal"],
        "phase_explainer": module["explainer"],
        "items": items,
        "checkin_done": checkin_done,
        "adherence_7j": adherence_7j,
        "streak": streak,
        "gad7_due": gad7_due,
        "notices": notices,
    }
