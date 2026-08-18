"""Signaux déterministes calculés sur les données de l'utilisateur.

Ce module est le garant de la traçabilité. Chaque signal produit :

    {
      "id": "correlation_sommeil_anxiete",
      "label": "Sommeil court → anxiété plus élevée le lendemain",
      "value": -0.62,
      "verdict": "association marquée",
      "method": "corrélation de Pearson entre heures de sommeil et anxiété du lendemain",
      "observations": [{"date": "2026-08-12", "sommeil": 5.5, "anxiete": 8}, ...],
      "n": 11
    }

Les `observations` sont les données brutes exactes qui ont produit le chiffre :
c'est ce que l'interface affiche dans le panneau « d'où ça sort ».

Ces signaux servent à deux choses : alimenter le prompt du LLM (qui n'a donc pas
à calculer, seulement à interpréter), et permettre une analyse complète **sans
aucun LLM** si aucune clé n'est configurée ou si l'utilisateur refuse l'envoi de
ses données.
"""

from __future__ import annotations

import datetime as dt
import math
import re
from typing import Any

from . import db, stats

# --- Détection de drapeaux rouges -------------------------------------------

# Formulations qui déclenchent l'affichage des ressources d'urgence et la
# suspension des conseils habituels. Volontairement large : un faux positif
# coûte un encart d'information, un faux négatif coûte beaucoup plus cher.
RED_FLAG_PATTERNS = [
    r"\bme tuer\b",
    r"\bme suicider\b",
    r"\bsuicid",
    r"\ben finir\b",
    r"\bplus envie de vivre\b",
    r"\bne plus être là\b",
    r"\bme faire du mal\b",
    r"\bm'automutil",
    r"\bje veux mourir\b",
    r"\bmourir\b.{0,20}\b(envie|voudrais|souhaite)\b",
    r"\b(envie|voudrais|souhaite)\b.{0,20}\bmourir\b",
    r"\bdisparaître pour de bon\b",
    r"\bpasser à l'acte\b",
]
_RED_FLAG_RE = re.compile("|".join(RED_FLAG_PATTERNS), re.IGNORECASE)

CRISIS_RESOURCES = [
    {"pays": "France", "libelle": "3114 — prévention du suicide, gratuit, 24 h/24", "numero": "3114"},
    {"pays": "France", "libelle": "SAMU — urgences médicales", "numero": "15"},
    {"pays": "Europe", "libelle": "Numéro d'urgence européen", "numero": "112"},
    {"pays": "Belgique", "libelle": "Centre de prévention du suicide", "numero": "0800 32 123"},
    {"pays": "Suisse", "libelle": "La Main Tendue", "numero": "143"},
    {"pays": "Canada", "libelle": "Ligne d'aide en cas de crise de suicide", "numero": "988"},
]


def detect_red_flags(texts: list[str]) -> list[str]:
    """Retourne les extraits ayant déclenché une alerte (max 3, tronqués)."""
    hits: list[str] = []
    for text in texts:
        if not text:
            continue
        match = _RED_FLAG_RE.search(text)
        if match:
            start = max(0, match.start() - 60)
            hits.append(text[start : match.end() + 60].strip())
        if len(hits) >= 3:
            break
    return hits


# --- Statistiques élémentaires ----------------------------------------------


def _mean(values: list[float]) -> float | None:
    clean = [v for v in values if v is not None]
    return sum(clean) / len(clean) if clean else None


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    """Corrélation de Pearson brute. Conservée pour compatibilité.

    Délègue à `stats.pearson` : garder deux implémentations aurait fini par les faire
    diverger. Le seuil de n a disparu d'ici — c'est `stats.correlation` qui porte la
    décision de conclure ou non, avec son intervalle de confiance.
    """
    pairs = [(x, y) for x, y in zip(xs, ys, strict=True) if x is not None and y is not None]
    return stats.pearson(pairs)


def _verdict_correlation(r: float) -> str:
    a = abs(r)
    if a >= 0.6:
        return "association marquée"
    if a >= 0.4:
        return "association modérée"
    if a >= 0.25:
        return "association faible"
    return "pas d'association nette"


def gad7_severity(total: int) -> str:
    if total <= 4:
        return "minimale"
    if total <= 9:
        return "légère"
    if total <= 14:
        return "modérée"
    return "sévère"


GAD7_MCID = 4  # Toussaint et al., J Affect Disord 2020


# --- Collecte ----------------------------------------------------------------


def _fetch(user_id: str, start: dt.date, end: dt.date) -> dict[str, list[dict]]:
    checkins = db.query_all(
        """
        SELECT entry_date, moment, anxiety_0_10, anxiety_peak_0_10, mood_0_10,
               sleep_hours, sleep_quality_0_10, caffeine_units, alcohol_units,
               exercise_min, panic_attacks, avoidance_0_10, contexts, main_trigger, note
        FROM daily_checkins
        WHERE user_id = %s AND entry_date BETWEEN %s AND %s
        ORDER BY entry_date, moment
        """,
        (user_id, start, end),
    )
    logs = db.query_all(
        """
        SELECT l.entry_date, l.activity_slug, l.status, l.duration_min,
               l.anxiety_before, l.anxiety_after, l.skip_reason, l.notes,
               a.title, a.category, a.is_core, a.up_module
        FROM activity_logs l
        JOIN activities a ON a.slug = l.activity_slug
        WHERE l.user_id = %s AND l.entry_date BETWEEN %s AND %s
        ORDER BY l.entry_date
        """,
        (user_id, start, end),
    )
    journal = db.query_all(
        """
        SELECT entry_date, kind, situation, emotions, body_sensations,
               intensity_before, intensity_after, automatic_thought, thinking_trap,
               alternative_thought, prediction, prediction_probability,
               actual_outcome, learning, safety_behaviors_dropped, worry_text,
               worry_actionable, next_action, free_text
        FROM journal_entries
        WHERE user_id = %s AND entry_date BETWEEN %s AND %s
        ORDER BY entry_date
        """,
        (user_id, start, end),
    )
    assessments = db.query_all(
        """
        SELECT instrument, taken_on, items, total, severity
        FROM assessments
        WHERE user_id = %s
        ORDER BY taken_on DESC
        LIMIT 20
        """,
        (user_id,),
    )
    exposures = db.query_all(
        """
        SELECT label, kind, anticipated_anxiety, attempts, last_attempt_on,
               best_learning, mastered
        FROM exposure_items
        WHERE user_id = %s
        ORDER BY anticipated_anxiety NULLS LAST
        """,
        (user_id,),
    )
    momentary = db.query_all(
        """
        SELECT entry_date, rated_at, anxiety_0_10, contexts, note
        FROM momentary_ratings
        WHERE user_id = %s AND entry_date BETWEEN %s AND %s
        ORDER BY rated_at
        """,
        (user_id, start, end),
    )
    # Bracelet. Volontairement lu comme n'importe quelle autre source : mêmes seuils
    # de n, mêmes corrections de multiplicité, même panneau de traçabilité. Une donnée
    # de capteur n'a aucun statut particulier ici — elle est juste mesurée au lieu
    # d'être déclarée, et `sleep_source` garde la trace de la différence.
    wearable = db.query_all(
        """
        SELECT entry_date, hrv_rmssd_milli, resting_heart_rate, recovery_score,
               sleep_hours, respiratory_rate, strain, max_heart_rate
        FROM wearable_daily
        WHERE user_id = %s AND entry_date BETWEEN %s AND %s
        """,
        (user_id, start, end),
    )
    sessions = db.query_all(
        """
        SELECT entry_date, sport, max_heart_rate, strain
        FROM wearable_workouts
        WHERE user_id = %s AND entry_date BETWEEN %s AND %s
        """,
        (user_id, start, end),
    )
    return {
        "checkins": checkins,
        "logs": logs,
        "journal": journal,
        "assessments": assessments,
        "exposures": exposures,
        "momentary": momentary,
        "wearable": wearable,
        "sessions": sessions,
    }


def _daily_anxiety(
    checkins: list[dict], momentary: list[dict] | None = None
) -> dict[dt.date, float]:
    """L'anxiété **de la journée**, une valeur par jour, par ordre de fiabilité.

    Ne pas moyenner les moments : c'est le piège du découpage. Le chiffre du matin
    répond à « comment tu te sens là », à 8 h, avant que la journée commence ; celui
    du soir résume la journée entière. Les additionner produirait une valeur qui ne
    mesure rien, et toutes les corrélations en dépendent.

    Ordre retenu :

    1. la saisie du **soir**, qui est la mesure de la journée ;
    2. sinon la **moyenne des mesures instantanées** du jour — plusieurs points
       valent mieux qu'un souvenir ;
    3. sinon le **matin**, faute de mieux, en sachant que c'est un instant et pas
       une journée.
    """
    by_moment: dict[dt.date, dict[str, float]] = {}
    for row in checkins:
        if row["anxiety_0_10"] is None:
            continue
        by_moment.setdefault(row["entry_date"], {})[row["moment"]] = float(row["anxiety_0_10"])

    spot: dict[dt.date, list[float]] = {}
    for row in momentary or []:
        spot.setdefault(row["entry_date"], []).append(float(row["anxiety_0_10"]))

    out: dict[dt.date, float] = {}
    for day in set(by_moment) | set(spot):
        moments = by_moment.get(day, {})
        if "soir" in moments:
            out[day] = moments["soir"]
        elif day in spot:
            out[day] = sum(spot[day]) / len(spot[day])
        elif "matin" in moments:
            out[day] = moments["matin"]
    return out


def _daily_field(checkins: list[dict], field: str) -> dict[dt.date, float]:
    out: dict[dt.date, float] = {}
    for row in checkins:
        value = row.get(field)
        if value is None:
            continue
        # En cas de double saisie (matin + soir), on garde la valeur maximale
        # pour les cumuls (caféine, alcool, sport) et la dernière sinon.
        out[row["entry_date"]] = max(float(value), out.get(row["entry_date"], float(value)))
    return out


def compute(
    user_id: str,
    end_date: dt.date | None = None,
    days: int = 21,
    with_days: bool = False,
) -> dict[str, Any]:
    """Calcule l'ensemble des signaux sur une fenêtre glissante.

    `with_days` ajoute la clé `jours` : les enregistrements journaliers agrégés, avec
    des objets `date` en clés. Réservé à un usage **serveur** — la prévision en a
    besoin et refaire les requêtes pour les reconstruire serait du gaspillage. Les
    routes qui sérialisent les signaux ne le demandent pas, donc rien ne change pour
    les clients.
    """
    end = end_date or dt.date.today()
    start = end - dt.timedelta(days=days - 1)
    data = _fetch(user_id, start, end)

    checkins = data["checkins"]
    logs = data["logs"]
    journal = data["journal"]
    assessments = data["assessments"]

    momentary = data["momentary"]
    anxiety_by_day = _daily_anxiety(checkins, momentary)
    sleep_by_day = _daily_field(checkins, "sleep_hours")
    sleep_quality_by_day = _daily_field(checkins, "sleep_quality_0_10")
    caffeine_by_day = _daily_field(checkins, "caffeine_units")
    alcohol_by_day = _daily_field(checkins, "alcohol_units")
    exercise_by_day = _daily_field(checkins, "exercise_min")
    avoidance_by_day = _daily_field(checkins, "avoidance_0_10")

    # Séries du bracelet. La VFC nocturne et la fréquence cardiaque de repos sont le
    # meilleur usage réel de cette source : une dégradation nette par rapport à la base
    # personnelle est un signal de risque **journalier**, ce qui est exploitable — là où
    # détecter un épisode ne l'est pas, faute de série temporelle de fréquence cardiaque.
    hrv_by_day = {
        r["entry_date"]: float(r["hrv_rmssd_milli"])
        for r in data["wearable"]
        if r["hrv_rmssd_milli"] is not None
    }
    rhr_by_day = {
        r["entry_date"]: float(r["resting_heart_rate"])
        for r in data["wearable"]
        if r["resting_heart_rate"] is not None
    }
    session_hr_by_day: dict[dt.date, float] = {}
    for row in data["sessions"]:
        if row["max_heart_rate"] is None:
            continue
        day = row["entry_date"]
        session_hr_by_day[day] = max(
            float(row["max_heart_rate"]), session_hr_by_day.get(day, 0.0)
        )

    signals: list[dict[str, Any]] = []

    # --- Assiduité au check-in ---------------------------------------------
    days_with_checkin = sorted(anxiety_by_day)
    signals.append(
        {
            "id": "assiduite_checkin",
            "label": "Jours renseignés sur la période",
            "value": len(days_with_checkin),
            "verdict": f"{len(days_with_checkin)}/{days} jours",
            "method": "comptage des jours avec au moins un check-in contenant l'anxiété",
            "observations": [{"date": str(d), "anxiete": round(anxiety_by_day[d], 1)} for d in days_with_checkin],
            "n": len(days_with_checkin),
        }
    )

    # --- Tendance de l'anxiété ---------------------------------------------
    recent = [anxiety_by_day[d] for d in days_with_checkin if d > end - dt.timedelta(days=7)]
    previous = [
        anxiety_by_day[d]
        for d in days_with_checkin
        if end - dt.timedelta(days=14) < d <= end - dt.timedelta(days=7)
    ]
    mean_recent, mean_previous = _mean(recent), _mean(previous)
    if mean_recent is not None:
        delta = None if mean_previous is None else round(mean_recent - mean_previous, 2)
        signals.append(
            {
                "id": "tendance_anxiete",
                "label": "Anxiété moyenne, 7 derniers jours vs 7 précédents",
                "value": round(mean_recent, 2),
                "delta": delta,
                "verdict": (
                    "pas encore de comparaison possible"
                    if delta is None
                    else "en baisse"
                    if delta <= -0.7
                    else "en hausse"
                    if delta >= 0.7
                    else "stable"
                ),
                "method": "moyenne de l'anxiété quotidienne 0-10 sur deux fenêtres de 7 jours",
                "observations": [
                    {"fenetre": "7 derniers jours", "moyenne": round(mean_recent, 2), "n": len(recent)},
                    {
                        "fenetre": "7 jours précédents",
                        "moyenne": round(mean_previous, 2) if mean_previous is not None else None,
                        "n": len(previous),
                    },
                ],
                "n": len(recent) + len(previous),
            }
        )

    # --- Corrélations personnelles ------------------------------------------
    def _lagged_pairs(source: dict[dt.date, float], lag: int) -> list[tuple[dt.date, float, float]]:
        """Associe la valeur du jour J à l'anxiété du jour J+lag."""
        out = []
        for day, value in source.items():
            target = day + dt.timedelta(days=lag)
            if target in anxiety_by_day:
                out.append((day, value, anxiety_by_day[target]))
        return sorted(out)

    correlations = [
        ("correlation_sommeil_anxiete", "Heures de sommeil → anxiété du lendemain", sleep_by_day, 1, "sommeil_h"),
        ("correlation_qualite_sommeil", "Qualité du sommeil → anxiété du lendemain", sleep_quality_by_day, 1, "qualite_sommeil"),
        ("correlation_cafeine_anxiete", "Caféine → anxiété du jour", caffeine_by_day, 0, "cafeine"),
        ("correlation_alcool_anxiete", "Alcool → anxiété du lendemain", alcohol_by_day, 1, "alcool"),
        ("correlation_sport_anxiete", "Activité physique → anxiété du jour", exercise_by_day, 0, "sport_min"),
        # Bracelet. Décalage 0 pour la VFC : elle est mesurée pendant la nuit qui
        # précède la journée, donc elle appartient bien au jour qu'elle annonce.
        ("correlation_vfc_anxiete", "Variabilité cardiaque nocturne → anxiété du jour", hrv_by_day, 0, "vfc_ms"),
        ("correlation_fc_repos_anxiete", "Fréquence cardiaque de repos → anxiété du jour", rhr_by_day, 0, "fc_repos"),
    ]

    # Deux passes obligatoires, et la seconde est celle qui tranche.
    #
    # En **niveau brut**, deux séries qui dérivent ensemble sur trois semaines
    # corrèlent fortement sans aucun lien : l'anxiété est très autocorrélée d'un jour
    # sur l'autre, et une mauvaise période fait monter tout en même temps. En
    # **différences premières** (la variation de J−1 à J), cette dérive commune
    # disparaît — il ne reste que « quand ça bouge d'un jour à l'autre, est-ce que ça
    # bouge ensemble ? ». C'est cette question qui a un sens ici.
    #
    # On garde les deux et on affiche les deux : l'écart entre le brut et les
    # variations est en soi une information. Un r de 0,6 en brut qui tombe à 0,1 en
    # variations dit exactement une chose — c'était la dérive, pas l'association.
    computed: list[dict[str, Any]] = []
    for sig_id, label, source, lag, key in correlations:
        pairs = _lagged_pairs(source, lag)
        raw = stats.correlation([(v, a) for _, v, a in pairs])

        deltas_source = stats.first_differences(source)
        deltas_anxiety = stats.first_differences(anxiety_by_day)
        delta_pairs = [
            (day, dv, deltas_anxiety[day + dt.timedelta(days=lag)])
            for day, dv in sorted(deltas_source.items())
            if day + dt.timedelta(days=lag) in deltas_anxiety
        ]
        diff = stats.correlation([(dv, da) for _, dv, da in delta_pairs])

        computed.append(
            {
                "id": sig_id, "label": label, "key": key, "lag": lag,
                "pairs": pairs, "raw": raw, "diff": diff,
            }
        )

    # Correction de multiplicité sur la famille entière. Cinq associations testées à
    # 5 % donnent environ une chance sur quatre d'en voir « une » sur des données sans
    # lien : sans correction, l'application finirait par inventer une régularité, avec
    # ses chiffres et sa traçabilité — donc de façon parfaitement convaincante.
    survivors = stats.benjamini_hochberg(
        [c["diff"]["p"] if c["diff"]["concluant"] else None for c in computed]
    )

    for entry, survives in zip(computed, survivors, strict=True):
        raw, diff = entry["raw"], entry["diff"]
        pairs, key, lag = entry["pairs"], entry["key"], entry["lag"]
        signals.append(
            {
                "id": entry["id"],
                "label": entry["label"],
                # `value` reste la corrélation en niveau : c'est ce que le reste du
                # code et les règles adaptatives lisent déjà. Le verdict, lui, porte
                # sur les variations, qui sont la mesure défendable.
                "value": raw["r"],
                "value_variations": diff["r"],
                "ic": [diff["ic_bas"], diff["ic_haut"]],
                "p": diff["p"],
                "retenu": bool(survives),
                "verdict": stats.describe_correlation(diff, bool(survives)),
                "method": (
                    f"corrélation de Pearson entre la valeur du jour J et l'anxiété du jour "
                    f"J+{lag}, calculée sur les **variations d'un jour sur l'autre** pour "
                    "retirer la dérive commune (l'anxiété est fortement autocorrélée). "
                    f"Intervalle de confiance à 95 % par transformée de Fisher, minimum "
                    f"{stats.MIN_PAIRS} paires, et correction de Benjamini-Hochberg sur les "
                    f"{len(computed)} associations testées. En niveau brut, sans retirer la "
                    f"dérive : r = {raw['r']} sur {raw['n']} paires. Une corrélation n'est "
                    "jamais une causalité."
                ),
                "observations": [
                    {"date": str(d), key: v, "anxiete": round(a, 1)} for d, v, a in pairs
                ],
                "n": diff["n"],
                "n_brut": raw["n"],
            }
        )

    # --- Activités faites / non faites --------------------------------------
    done: dict[str, int] = {}
    not_done: dict[str, int] = {}
    skip_reasons: list[dict[str, Any]] = []
    effect_pairs: dict[str, list[tuple[int, int]]] = {}
    for log in logs:
        slug = log["activity_slug"]
        if log["status"] in {"fait", "partiel"}:
            done[slug] = done.get(slug, 0) + 1
            if log["anxiety_before"] is not None and log["anxiety_after"] is not None:
                effect_pairs.setdefault(slug, []).append(
                    (log["anxiety_before"], log["anxiety_after"])
                )
        else:
            not_done[slug] = not_done.get(slug, 0) + 1
            if log["skip_reason"]:
                skip_reasons.append(
                    {
                        "date": str(log["entry_date"]),
                        "activite": log["title"],
                        "raison": log["skip_reason"],
                    }
                )

    total_logged = sum(done.values()) + sum(not_done.values())
    adherence = round(sum(done.values()) / total_logged, 3) if total_logged else None
    signals.append(
        {
            "id": "adherence",
            "label": "Part des activités proposées réalisées",
            "value": adherence,
            "verdict": (
                "aucune activité enregistrée"
                if adherence is None
                else "bonne"
                if adherence >= 0.7
                else "irrégulière"
                if adherence >= 0.4
                else "faible"
            ),
            "method": "(fait + partiel) / total des activités tracées sur la période",
            "observations": [
                {"activite": slug, "fait": done.get(slug, 0), "pas_fait": not_done.get(slug, 0)}
                for slug in sorted(set(done) | set(not_done))
            ],
            "n": total_logged,
        }
    )

    signals.append(
        {
            "id": "activites_non_faites",
            "label": "Activités les plus souvent non faites, et raisons données",
            "value": sorted(not_done.items(), key=lambda kv: -kv[1])[:5],
            "verdict": "à examiner" if not_done else "rien à signaler",
            "method": "comptage des statuts « pas_fait » et « reporte », avec les raisons saisies",
            "observations": skip_reasons[:20],
            "n": sum(not_done.values()),
        }
    )

    # Effet mesuré avant/après par activité
    effects = []
    for slug, pairs in effect_pairs.items():
        deltas = [after - before for before, after in pairs]
        if len(deltas) >= 3:
            effects.append(
                {
                    "activite": slug,
                    "delta_moyen": round(sum(deltas) / len(deltas), 2),
                    "n": len(deltas),
                    "mesures": [{"avant": b, "apres": a} for b, a in pairs][:10],
                }
            )
    effects.sort(key=lambda e: e["delta_moyen"])
    signals.append(
        {
            "id": "effet_mesure_activites",
            "label": "Effet immédiat mesuré des activités (anxiété après − avant)",
            "value": effects[:5],
            "verdict": (
                f"la plus efficace chez vous : {effects[0]['activite']}" if effects else "pas encore de mesure avant/après"
            ),
            "method": "moyenne de (anxiété après − anxiété avant), à partir de 3 mesures par activité",
            "observations": effects[:5],
            "n": sum(e["n"] for e in effects),
        }
    )

    # --- Expositions et violation d'attente ---------------------------------
    exposures_logged = [j for j in journal if j["kind"] == "exposition"]
    violations = [
        {
            "date": str(j["entry_date"]),
            "prediction": j["prediction"],
            "probabilite_annoncee": j["prediction_probability"],
            "resultat_reel": j["actual_outcome"],
            "apprentissage": j["learning"],
        }
        for j in exposures_logged
        if j["prediction"] and j["actual_outcome"]
    ]
    mean_predicted = _mean(
        [float(j["prediction_probability"]) for j in exposures_logged if j["prediction_probability"] is not None]
    )
    signals.append(
        {
            "id": "expositions",
            "label": "Expositions réalisées et écart prédiction / réalité",
            "value": len(exposures_logged),
            "delta": round(mean_predicted, 1) if mean_predicted is not None else None,
            "verdict": (
                "aucune exposition sur la période"
                if not exposures_logged
                else f"{len(exposures_logged)} exposition(s), probabilité moyenne annoncée du pire scénario : {round(mean_predicted or 0)} %"
            ),
            "method": (
                "comptage des entrées de journal de type « exposition » ; la probabilité moyenne "
                "annoncée est comparée aux résultats réellement notés (logique de violation "
                "d'attente, Craske et al. 2014)"
            ),
            "observations": violations[:10],
            "n": len(exposures_logged),
        }
    )

    # --- Journal de pensées --------------------------------------------------
    thought_records = [j for j in journal if j["kind"] == "pensee"]
    deltas = [
        j["intensity_before"] - j["intensity_after"]
        for j in thought_records
        if j["intensity_before"] is not None and j["intensity_after"] is not None
    ]
    traps: dict[str, int] = {}
    for j in thought_records:
        if j["thinking_trap"]:
            traps[j["thinking_trap"]] = traps.get(j["thinking_trap"], 0) + 1
    signals.append(
        {
            "id": "journal_pensees",
            "label": "Journaux de pensées et baisse d'intensité obtenue",
            "value": len(thought_records),
            "delta": round(sum(deltas) / len(deltas), 2) if deltas else None,
            "verdict": (
                "aucun journal de pensées"
                if not thought_records
                else f"baisse moyenne de {round(sum(deltas) / len(deltas), 1)} points sur {len(deltas)} journaux"
                if deltas
                else "intensités avant/après non renseignées"
            ),
            "method": "moyenne de (intensité avant − intensité après) sur les journaux de pensées",
            "observations": [
                {
                    "date": str(j["entry_date"]),
                    "piege": j["thinking_trap"],
                    "avant": j["intensity_before"],
                    "apres": j["intensity_after"],
                }
                for j in thought_records[:10]
            ],
            "n": len(thought_records),
            "pieges_frequents": sorted(traps.items(), key=lambda kv: -kv[1]),
        }
    )

    # --- Attaques de panique et évitement -----------------------------------
    panic_total = sum(int(c["panic_attacks"] or 0) for c in checkins)
    signals.append(
        {
            "id": "attaques_panique",
            "label": "Attaques de panique sur la période",
            "value": panic_total,
            "verdict": "aucune" if panic_total == 0 else f"{panic_total} épisode(s)",
            "method": "somme du champ « attaques de panique » des check-ins",
            "observations": [
                {"date": str(c["entry_date"]), "nombre": c["panic_attacks"]}
                for c in checkins
                if (c["panic_attacks"] or 0) > 0
            ],
            "n": len(checkins),
        }
    )

    avoidance_mean = _mean(list(avoidance_by_day.values()))
    signals.append(
        {
            "id": "evitement",
            "label": "Niveau d'évitement moyen déclaré",
            "value": round(avoidance_mean, 2) if avoidance_mean is not None else None,
            "verdict": (
                "non renseigné"
                if avoidance_mean is None
                else "élevé"
                if avoidance_mean >= 6
                else "modéré"
                if avoidance_mean >= 3
                else "faible"
            ),
            "method": "moyenne du curseur d'évitement 0-10 des check-ins",
            "observations": [
                {"date": str(d), "evitement": v} for d, v in sorted(avoidance_by_day.items())
            ],
            "n": len(avoidance_by_day),
        }
    )

    # --- GAD-7 ---------------------------------------------------------------
    gad = [a for a in assessments if a["instrument"] == "gad7"]
    gad_signal: dict[str, Any] = {
        "id": "gad7",
        "label": "GAD-7 : score, sévérité et progrès cliniquement significatif",
        "value": None,
        "verdict": "aucune mesure enregistrée",
        "method": (
            "seuils 5 / 10 / 15 (léger / modéré / sévère) ; un écart est considéré comme "
            f"cliniquement significatif à partir de {GAD7_MCID} points (DMCI, Toussaint et al. 2020)"
        ),
        "observations": [
            {"date": str(a["taken_on"]), "total": a["total"], "severite": a["severity"]} for a in gad
        ],
        "n": len(gad),
    }
    if gad:
        latest = gad[0]
        gad_signal["value"] = latest["total"]
        if len(gad) >= 2:
            delta = latest["total"] - gad[1]["total"]
            gad_signal["delta"] = delta
            if delta <= -GAD7_MCID:
                verdict = f"amélioration cliniquement significative ({delta} points)"
            elif delta >= GAD7_MCID:
                verdict = f"aggravation cliniquement significative (+{delta} points)"
            else:
                verdict = (
                    f"variation de {delta:+d} point(s) : en dessous du seuil de "
                    f"{GAD7_MCID}, à interpréter comme du bruit de mesure"
                )
            gad_signal["verdict"] = f"{latest['total']}/21 ({latest['severity']}) — {verdict}"
        else:
            gad_signal["verdict"] = (
                f"{latest['total']}/21 ({latest['severity']}) — première mesure, "
                "sert de référence"
            )
        # Critère de rémission : ≤ 5 sur 4 mesures consécutives
        last_four = [a["total"] for a in gad[:4]]
        gad_signal["remission_atteinte"] = len(last_four) == 4 and all(t <= 5 for t in last_four)
    signals.append(gad_signal)

    # --- Meilleurs et pires jours -------------------------------------------
    logs_by_day: dict[dt.date, list[str]] = {}
    for log in logs:
        if log["status"] in {"fait", "partiel"}:
            logs_by_day.setdefault(log["entry_date"], []).append(log["title"])
    ranked = sorted(anxiety_by_day.items(), key=lambda kv: kv[1])
    best = [
        {"date": str(d), "anxiete": round(a, 1), "activites": logs_by_day.get(d, [])}
        for d, a in ranked[:3]
    ]
    worst = [
        {"date": str(d), "anxiete": round(a, 1), "activites": logs_by_day.get(d, [])}
        for d, a in ranked[-3:][::-1]
    ]
    signals.append(
        {
            "id": "meilleurs_pires_jours",
            "label": "Ce qui distingue vos meilleures et vos pires journées",
            "value": {"meilleurs": best, "pires": worst},
            "verdict": "comparaison descriptive, pas une preuve de causalité",
            "method": "tri des jours par anxiété moyenne, avec les activités réalisées ce jour-là",
            "observations": best + worst,
            "n": len(ranked),
        }
    )

    # --- Hypothèses pré-enregistrées ----------------------------------------
    #
    # C'est la réponse à « repérer des combinaisons » — sport intense plus niveau
    # d'anxiété, nuit courte plus caféine — sans fouiller. La liste est fermée et
    # écrite à l'avance dans `hypotheses.py` : croiser toutes les variables deux à deux
    # sur une trentaine de jours produirait plusieurs « découvertes » significatives et
    # fausses, présentées avec leurs chiffres et leur traçabilité, donc crédibles.
    from . import hypotheses as hypotheses_mod

    day_records: dict[dt.date, dict[str, Any]] = {}
    for day in sorted(
        set(anxiety_by_day)
        | set(sleep_by_day)
        | set(caffeine_by_day)
        | set(alcohol_by_day)
        | set(exercise_by_day)
        | set(avoidance_by_day)
        | set(hrv_by_day)
        | set(session_hr_by_day)
    ):
        day_records[day] = {
            "anxiete": anxiety_by_day.get(day),
            "sommeil": sleep_by_day.get(day),
            "cafeine": caffeine_by_day.get(day),
            "alcool": alcohol_by_day.get(day),
            "sport": exercise_by_day.get(day),
            "evitement": avoidance_by_day.get(day),
            "paniques": 0,
            "exposition": False,
            "respiration": False,
            # Mesures, distinctes des déclarations. `fc_max_seance` est ce qui rend
            # testable « séance intense puis crise le lendemain » — le seul usage de
            # la fréquence cardiaque que cette API autorise.
            "vfc": hrv_by_day.get(day),
            "fc_repos": rhr_by_day.get(day),
            "fc_max_seance": session_hr_by_day.get(day),
        }
    for row in checkins:
        record = day_records.get(row["entry_date"])
        if record is not None:
            record["paniques"] = max(record["paniques"], int(row["panic_attacks"] or 0))
    for entry in journal:
        record = day_records.get(entry["entry_date"])
        if record is not None and entry["kind"] == "exposition":
            record["exposition"] = True
    for log in logs:
        record = day_records.get(log["entry_date"])
        if record is not None and log["status"] in {"fait", "partiel"}:
            if log["category"] == "respiration":
                record["respiration"] = True

    tested = hypotheses_mod.evaluate_all(day_records)
    retained = [h for h in tested["hypotheses"] if h["retenu"]]
    signals.append(
        {
            "id": "hypotheses",
            "label": "Hypothèses pré-enregistrées, testées sur tes données",
            "value": [{"id": h["id"], "libelle": h["label"], "verdict": h["verdict"]} for h in retained],
            "verdict": (
                f"{tested['retenues']} retenue(s) sur {tested['testables']} testable(s) "
                f"({tested['ecrites']} écrites)"
                if tested["testables"]
                else f"aucune encore testable — il faut au moins {stats.MIN_GROUP} jours "
                "de chaque côté d'une condition"
            ),
            "method": tested["methode"],
            "observations": [
                {
                    "hypothese": h["label"],
                    "verdict": h["verdict"],
                    "retenu": h["retenu"],
                    "pourquoi_testee": h["pourquoi"],
                }
                for h in tested["hypotheses"]
            ],
            "n": tested["testables"],
        }
    )

    # --- Résolution intra-journée -------------------------------------------
    #
    # Ce que les mesures instantanées débloquent : avec un point par jour, « ça monte
    # toujours en fin d'après-midi » est invisible. Les tranches sont larges (quatre
    # sur la journée) parce que découper plus fin sur peu de mesures ne produirait
    # que du bruit présenté comme un motif.
    SLICES = [("matin", 5, 12), ("après-midi", 12, 17), ("soirée", 17, 22), ("nuit", 22, 5)]

    def _slice_of(hour: int) -> str:
        for name, low, high in SLICES:
            if low <= high and low <= hour < high:
                return name
            if low > high and (hour >= low or hour < high):
                return name
        return "nuit"

    per_slice: dict[str, list[float]] = {}
    for row in momentary:
        per_slice.setdefault(_slice_of(row["rated_at"].hour), []).append(
            float(row["anxiety_0_10"])
        )
    slice_means = sorted(
        ({"tranche": k, "moyenne": round(sum(v) / len(v), 2), "n": len(v)} for k, v in per_slice.items()),
        key=lambda e: -e["moyenne"],
    )
    # Cinq mesures dans une tranche est déjà peu ; en dessous on ne conclut pas.
    conclusive = [e for e in slice_means if e["n"] >= 5]
    signals.append(
        {
            "id": "tranches_horaires",
            "label": "Moment de la journée le plus anxieux",
            "value": conclusive[0]["tranche"] if conclusive else None,
            "verdict": (
                f"{conclusive[0]['tranche']} : {conclusive[0]['moyenne']}/10 en moyenne "
                f"sur {conclusive[0]['n']} mesures"
                if conclusive
                else f"pas concluant ({len(momentary)} mesure(s) instantanée(s), 5 minimum par tranche)"
            ),
            "method": (
                "moyenne des mesures instantanées par tranche horaire (matin, après-midi, "
                "soirée, nuit), à partir de 5 mesures dans la tranche. Les tranches sont larges "
                "volontairement : plus fin, sur ce volume, ne produirait que du bruit."
            ),
            "observations": slice_means,
            "n": len(momentary),
        }
    )

    # --- Drapeaux rouges -----------------------------------------------------
    texts = [j.get("free_text") or "" for j in journal]
    texts += [j.get("situation") or "" for j in journal]
    texts += [j.get("worry_text") or "" for j in journal]
    texts += [c.get("note") or "" for c in checkins]
    texts += [m.get("note") or "" for m in momentary]
    red_flags = detect_red_flags(texts)

    out_extra: dict[str, Any] = {"jours": day_records} if with_days else {}
    return {
        **out_extra,
        "periode": {"debut": str(start), "fin": str(end), "jours": days},
        "signaux": signals,
        "drapeaux_rouges": red_flags,
        "ressources_urgence": CRISIS_RESOURCES if red_flags else [],
        "brut": {
            "checkins": len(checkins),
            "mesures_instantanees": len(momentary),
            "jours_bracelet": len(data["wearable"]),
            "seances_bracelet": len(data["sessions"]),
            "hypotheses_testables": tested["testables"],
            "activites_tracees": total_logged,
            "entrees_journal": len(journal),
            "expositions": len(exposures_logged),
            "echelles": len(assessments),
            "items_echelle_exposition": len(data["exposures"]),
        },
    }


def signal_by_id(signals: dict[str, Any], sig_id: str) -> dict[str, Any] | None:
    for signal in signals.get("signaux", []):
        if signal["id"] == sig_id:
            return signal
    return None
