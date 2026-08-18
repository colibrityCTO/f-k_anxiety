"""Charge du jour, et prévision du lendemain — avec son plafond assumé.

## Ce que dit la littérature, et ce que ça impose

Sur la prévision individuelle de l'anxiété à partir de capteurs et d'évaluations
répétées, les modèles au niveau du **groupe** expliquent beaucoup (R² robuste ≈ 0,75),
les modèles **individuels** nettement moins — R² robuste moyen ≈ 0,39. Et l'essentiel
de cette variance vient de l'autocorrélation : demain ressemble à aujourd'hui.

Deux conséquences de conception, non négociables :

1. **La référence à battre est la persistance**, pas le hasard. Un modèle qui n'améliore
   pas « demain = aujourd'hui » n'apporte rien, et l'afficher serait une mise en scène.
   C'est mesurable, donc c'est décidable : on valide en **avance glissante** (on n'ajuste
   jamais sur des jours déjà utilisés pour tester) et on ne montre la régression que si
   son erreur moyenne est réellement plus basse.
2. **Un intervalle, jamais un point.** « Entre 4 et 7 » est une prévision ; « 5,4 » est
   une promesse. Et l'intervalle est calibré sur les variations quotidiennes de la
   personne, pas sur un écart-type théorique.

## Deux chiffres distincts, jamais fusionnés

L'**anxiété déclarée** est la vérité de référence : elle ne se calcule pas.

La **charge du jour** est autre chose — un cumul de facteurs de risque. Elle porte ce
nom et pas « ton niveau d'anxiété » : un score étiqueté « anxiété » qui monte est
anxiogène par lui-même, et on finit par surveiller le score au lieu de vivre.

Et surtout : la charge n'est pondérée que par des associations **retenues** au sens du
lot 3. Si rien n'a survécu à la correction de multiplicité, il n'y a pas de pondération
personnelle — donc pas d'indice, et on le dit. Inventer des poids universels ici
reviendrait à annuler tout le travail statistique.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from . import db, stats

# Jours minimum d'historique avant de tenter une régression personnelle. En dessous,
# ajuster six coefficients sur une quinzaine de points produit un modèle qui décrit
# le passé et ne prédit rien — c'est du surajustement, pas de la prévision.
MIN_TRAIN_DAYS = 30

# Jours minimum pour afficher une charge, même pondérée.
MIN_LOAD_DAYS = 14

# Quels signaux pondèrent quels facteurs de risque. La correspondance est explicite :
# chaque composante de la charge doit pouvoir nommer l'association qui la justifie.
LOAD_FACTORS: list[dict[str, Any]] = [
    {
        "key": "sommeil",
        "signal": "correlation_sommeil_anxiete",
        "label": "nuit plus courte que ta moyenne",
        "direction": -1,
    },
    {
        "key": "cafeine",
        "signal": "correlation_cafeine_anxiete",
        "label": "plus de caféine que ta moyenne",
        "direction": 1,
    },
    {
        "key": "alcool",
        "signal": "correlation_alcool_anxiete",
        "label": "alcool la veille",
        "direction": 1,
    },
    {
        "key": "sport",
        "signal": "correlation_sport_anxiete",
        "label": "aucune activité physique",
        "direction": -1,
    },
]


# --- Algèbre : moindres carrés en Python pur --------------------------------


def _solve(matrix: list[list[float]], vector: list[float]) -> list[float] | None:
    """Élimination de Gauss avec pivot partiel. `None` si le système est singulier."""
    n = len(vector)
    a = [row[:] + [vector[i]] for i, row in enumerate(matrix)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(a[r][col]))
        if abs(a[pivot][col]) < 1e-10:
            return None
        a[col], a[pivot] = a[pivot], a[col]
        for row in range(col + 1, n):
            factor = a[row][col] / a[col][col]
            for k in range(col, n + 1):
                a[row][k] -= factor * a[col][k]
    out = [0.0] * n
    for col in reversed(range(n)):
        total = a[col][n] - sum(a[col][k] * out[k] for k in range(col + 1, n))
        out[col] = total / a[col][col]
    return out


def _ols(rows: list[list[float]], targets: list[float]) -> list[float] | None:
    """Régression linéaire par équations normales, avec une régularisation minime.

    La régularisation (1e-6 sur la diagonale) n'est pas un choix statistique mais une
    précaution numérique : deux prédicteurs quasi colinéaires — ce qui arrive vite avec
    peu de jours — rendraient le système insoluble sans elle.
    """
    if not rows:
        return None
    k = len(rows[0])
    xtx = [[sum(r[i] * r[j] for r in rows) + (1e-6 if i == j else 0.0) for j in range(k)] for i in range(k)]
    xty = [sum(r[i] * t for r, t in zip(rows, targets, strict=True)) for i in range(k)]
    return _solve(xtx, xty)


# --- Charge du jour ---------------------------------------------------------


def load_index(
    days: dict[dt.date, dict[str, Any]], signals: dict[str, Any], day: dt.date
) -> dict[str, Any]:
    """Cumul pondéré des facteurs de risque du jour. `valeur` à `None` si non calculable.

    La pondération vient des associations **retenues** : le poids d'un facteur est la
    force de sa corrélation chez cette personne. Un facteur dont l'association n'a pas
    survécu à la correction ne compte pas — pas avec un petit poids, pas du tout.
    """
    by_id = {s["id"]: s for s in signals.get("signaux", [])}
    history = {d: rec for d, rec in days.items() if d <= day}
    if len(history) < MIN_LOAD_DAYS:
        return {
            "valeur": None,
            "raison": (
                f"{len(history)} jour(s) d'historique — il en faut {MIN_LOAD_DAYS} pour "
                "établir tes propres moyennes de référence"
            ),
            "composantes": [],
        }

    today_record = days.get(day)
    if today_record is None:
        return {"valeur": None, "raison": "rien de renseigné ce jour-là", "composantes": []}

    yesterday = days.get(day - dt.timedelta(days=1)) or {}
    components: list[dict[str, Any]] = []
    total = 0.0
    weight_sum = 0.0

    for factor in LOAD_FACTORS:
        signal = by_id.get(factor["signal"])
        if not signal or not signal.get("retenu"):
            components.append(
                {
                    "facteur": factor["label"],
                    "poids": 0.0,
                    "actif": None,
                    "note": "association non retenue chez toi — ne compte pas",
                }
            )
            continue

        weight = abs(signal.get("value_variations") or 0.0)
        key = factor["key"]
        baseline = stats.mean([rec[key] for rec in history.values() if rec.get(key) is not None])
        source = yesterday if key == "alcool" else today_record
        value = source.get(key)
        if baseline is None or value is None:
            components.append(
                {"facteur": factor["label"], "poids": round(weight, 3), "actif": None,
                 "note": "valeur manquante ce jour-là"}
            )
            continue

        if key == "alcool":
            active = value > 0
        elif key == "sport":
            active = value < 20
        elif factor["direction"] < 0:
            active = value < baseline - 1
        else:
            active = value > baseline

        weight_sum += weight
        if active:
            total += weight
        components.append(
            {
                "facteur": factor["label"],
                "poids": round(weight, 3),
                "actif": bool(active),
                "valeur": value,
                "ta_moyenne": round(baseline, 2),
            }
        )

    if weight_sum == 0:
        return {
            "valeur": None,
            "raison": (
                "aucune association n'a encore survécu à la correction statistique, donc "
                "aucune pondération personnelle. Un indice avec des poids inventés serait "
                "un faux — mieux vaut ne rien afficher."
            ),
            "composantes": components,
        }

    return {
        "valeur": round(10.0 * total / weight_sum, 1),
        "raison": None,
        "composantes": components,
        "methode": (
            "somme des facteurs de risque présents aujourd'hui, chacun pondéré par la "
            "force de son association **chez toi** (corrélation sur les variations, retenue "
            "après correction de multiplicité), rapportée sur 10. Ce n'est pas ton anxiété : "
            "c'est ce que la journée cumule comme facteurs. Les deux sont affichés séparément "
            "exprès."
        ),
    }


# --- Prévision -------------------------------------------------------------


def _series(days: dict[dt.date, dict[str, Any]]) -> list[tuple[dt.date, dict[str, Any]]]:
    return sorted(days.items())


def _persistence_interval(anxiety: dict[dt.date, float]) -> float:
    """Demi-largeur de l'intervalle, calibrée sur les variations réelles de la personne.

    Un écart-type théorique dirait quelque chose sur une population ; l'écart-type des
    variations d'un jour sur l'autre de *cette* personne dit à quel point *ses* journées
    sautent. C'est la seule version qui rend l'intervalle interprétable.
    """
    deltas = list(stats.first_differences(anxiety).values())
    if len(deltas) < 5:
        return 2.0
    mean = sum(deltas) / len(deltas)
    variance = sum((d - mean) ** 2 for d in deltas) / (len(deltas) - 1)
    return max(0.5, min(4.0, 1.96 * variance**0.5))


def _predictor_keys(signals: dict[str, Any]) -> list[str]:
    """Les prédicteurs autorisés : l'anxiété du jour, plus les associations retenues.

    L'anxiété du jour est toujours dedans — c'est ce qui permet à la régression de faire
    au moins aussi bien que la persistance. Les autres n'entrent que si leur association
    a survécu : ajouter six variables sur trente jours parce qu'on les a en base est la
    façon la plus sûre de fabriquer un modèle qui décrit le passé sans prédire.
    """
    by_id = {s["id"]: s for s in signals.get("signaux", [])}
    mapping = {
        "correlation_sommeil_anxiete": "sommeil",
        "correlation_cafeine_anxiete": "cafeine",
        "correlation_alcool_anxiete": "alcool",
        "correlation_sport_anxiete": "sport",
    }
    keys = ["anxiete"]
    for signal_id, key in mapping.items():
        if by_id.get(signal_id, {}).get("retenu"):
            keys.append(key)
    return keys


def _rows_for(
    series: list[tuple[dt.date, dict[str, Any]]], keys: list[str]
) -> list[tuple[dt.date, list[float], float]]:
    """(jour, prédicteurs du jour J, anxiété du jour J+1) — uniquement jours consécutifs."""
    lookup = dict(series)
    out = []
    for day, record in series:
        target = lookup.get(day + dt.timedelta(days=1))
        if target is None or target.get("anxiete") is None:
            continue
        values = [record.get(k) for k in keys]
        if any(v is None for v in values):
            continue
        out.append((day, [1.0] + [float(v) for v in values], float(target["anxiete"])))
    return out


def evaluate(days: dict[dt.date, dict[str, Any]], signals: dict[str, Any]) -> dict[str, Any]:
    """Validation en avance glissante : la régression bat-elle la persistance ?

    À chaque jour de test, le modèle n'est ajusté que sur les jours **antérieurs**. C'est
    la seule façon de mesurer une capacité de prévision : ajuster puis tester sur les
    mêmes jours mesure une capacité de description, ce qui n'est pas la question.

    Renvoie l'erreur absolue moyenne des deux approches et lequel gagne.
    """
    series = _series(days)
    keys = _predictor_keys(signals)
    rows = _rows_for(series, keys)

    out: dict[str, Any] = {
        "prédicteurs": keys,
        "n_test": 0,
        "mae_persistance": None,
        "mae_regression": None,
        "gagnant": "persistance",
        "methode": (
            "validation en avance glissante : pour chaque jour testé, le modèle est ajusté "
            "uniquement sur les jours antérieurs, jamais sur le jour testé. La référence "
            "n'est pas le hasard mais la persistance (« demain = aujourd'hui »), parce que "
            "l'essentiel de la variance d'un jour sur l'autre vient de l'autocorrélation. "
            "La régression n'est utilisée que si elle fait réellement mieux."
        ),
    }
    if len(rows) < MIN_TRAIN_DAYS + 5:
        out["raison"] = (
            f"{len(rows)} paire(s) de jours consécutifs — il en faut "
            f"{MIN_TRAIN_DAYS + 5} pour tester honnêtement un modèle"
        )
        return out

    errors_p: list[float] = []
    errors_r: list[float] = []
    for index in range(MIN_TRAIN_DAYS, len(rows)):
        train = rows[:index]
        _, features, actual = rows[index]
        beta = _ols([r[1] for r in train], [r[2] for r in train])
        errors_p.append(abs(features[1] - actual))  # features[1] = anxiété du jour
        if beta is None:
            errors_r.append(abs(features[1] - actual))
            continue
        predicted = sum(b * x for b, x in zip(beta, features, strict=True))
        errors_r.append(abs(max(0.0, min(10.0, predicted)) - actual))

    out["n_test"] = len(errors_p)
    out["mae_persistance"] = round(sum(errors_p) / len(errors_p), 3)
    out["mae_regression"] = round(sum(errors_r) / len(errors_r), 3)
    # Marge de 2 % exigée : un gain de 0,001 point d'erreur n'est pas un gain, c'est du
    # bruit d'échantillonnage, et basculer de modèle pour ça serait arbitraire.
    if out["mae_regression"] < out["mae_persistance"] * 0.98:
        out["gagnant"] = "regression"
    return out


def predict(
    days: dict[dt.date, dict[str, Any]], signals: dict[str, Any], today: dt.date
) -> dict[str, Any] | None:
    """La prévision pour demain, avec son intervalle et le modèle réellement retenu."""
    record = days.get(today)
    if record is None or record.get("anxiete") is None:
        return None

    anxiety = {d: r["anxiete"] for d, r in days.items() if r.get("anxiete") is not None}
    half = _persistence_interval(anxiety)
    baseline = float(record["anxiete"])
    validation = evaluate(days, signals)

    model, point = "persistance", baseline
    if validation["gagnant"] == "regression":
        keys = validation["prédicteurs"]
        rows = _rows_for(_series(days), keys)
        beta = _ols([r[1] for r in rows], [r[2] for r in rows])
        values = [record.get(k) for k in keys]
        if beta is not None and all(v is not None for v in values):
            features = [1.0] + [float(v) for v in values]
            point = sum(b * x for b, x in zip(beta, features, strict=True))
            # Distinction qui n'est pas cosmétique. Quand le seul prédicteur retenu est
            # l'anxiété elle-même, le modèle ne fait pas mieux « grâce à tes facteurs » :
            # il tire la valeur du jour vers ta moyenne. C'est un résultat réel — battre
            # la persistance par retour à la moyenne signifie que tes écarts quotidiens
            # sont surtout du bruit autour d'un niveau — mais l'annoncer comme un modèle
            # personnalisé serait faux.
            model = "retour-moyenne" if keys == ["anxiete"] else "regression"

    point = max(0.0, min(10.0, point))
    return {
        "target_date": today + dt.timedelta(days=1),
        "model": model,
        "predicted": round(point, 2),
        "interval_low": round(max(0.0, point - half), 2),
        "interval_high": round(min(10.0, point + half), 2),
        "baseline": round(baseline, 2),
        "predictors": {k: record.get(k) for k in validation["prédicteurs"]},
        "validation": validation,
        # Formulation volontairement prudente. Jamais « tu vas faire une crise » : une
        # prédiction anxiogène est auto-réalisatrice, et un intervalle large annoncé comme
        # un chiffre unique serait lu comme une promesse.
        # Une fourchette dont les deux bornes arrondissent au même chiffre se lit
        # « entre 6 et 6 », ce qui est absurde — et surtout ce serait lu comme une
        # certitude alors que c'est l'inverse : la personne est simplement très stable.
        # On dit « autour de », qui reste une estimation.
        "phrase": (
            (
                f"Demain, probablement autour de **{round(point)}** sur 10."
                if round(max(0.0, point - half)) == round(min(10.0, point + half))
                else f"Demain, probablement entre **{round(max(0.0, point - half))}** et "
                f"**{round(min(10.0, point + half))}** sur 10."
            )
            + {
                "persistance": (
                    " C'est simplement ton niveau d'aujourd'hui reporté : à ce stade, aucun "
                    "modèle ne fait mieux chez toi."
                ),
                "retour-moyenne": (
                    " C'est ta moyenne, pas tes facteurs : chez toi, revenir vers ton niveau "
                    "habituel prédit mieux que reporter la valeur du jour. Autrement dit tes "
                    "écarts d'un jour sur l'autre sont surtout du bruit autour d'un niveau, et "
                    "aucun des facteurs suivis n'ajoute d'information pour l'instant."
                ),
                "regression": (
                    " Calculé sur tes propres facteurs ("
                    + ", ".join(k for k in validation["prédicteurs"] if k != "anxiete")
                    + "), et vérifié : ce calcul fait mieux que de reporter la valeur du jour."
                ),
            }[model]
        ),
    }


def store(user_id: str, forecast: dict[str, Any]) -> None:
    """Écrit la prévision. `DO NOTHING` : une prévision déjà posée ne se réécrit pas.

    C'est la propriété qui rend l'honnêteté vérifiable — sans elle, on pourrait
    « corriger » une prévision ratée après avoir vu le résultat, donc ne jamais se
    tromper.
    """
    db.execute(
        """
        INSERT INTO daily_forecasts
            (user_id, target_date, made_on, model, predicted, interval_low, interval_high,
             baseline, predictors)
        VALUES (%(user_id)s, %(target)s, CURRENT_DATE, %(model)s, %(predicted)s,
                %(low)s, %(high)s, %(baseline)s, %(predictors)s)
        ON CONFLICT (user_id, target_date, model) DO NOTHING
        """,
        {
            "user_id": user_id,
            "target": forecast["target_date"],
            "model": forecast["model"],
            "predicted": forecast["predicted"],
            "low": forecast["interval_low"],
            "high": forecast["interval_high"],
            "baseline": forecast["baseline"],
            "predictors": __import__("json").dumps(forecast["predictors"], default=str),
        },
    )


def track_record(user_id: str, anxiety: dict[dt.date, float]) -> dict[str, Any]:
    """Ce que les prévisions passées ont réellement donné, comparé à la persistance.

    C'est la contrepartie de « jamais réécrite » : puisque les prévisions sont figées, on
    peut afficher l'erreur réelle. Un modèle dont on ne montre pas les échecs n'est pas
    un modèle, c'est une décoration.
    """
    rows = db.query_all(
        """
        SELECT target_date, model, predicted, baseline, interval_low, interval_high
        FROM daily_forecasts WHERE user_id = %s ORDER BY target_date DESC LIMIT 90
        """,
        (user_id,),
    )
    scored = [
        {
            "date": str(r["target_date"]),
            "annonce": float(r["predicted"]),
            "observe": anxiety[r["target_date"]],
            "erreur": round(abs(float(r["predicted"]) - anxiety[r["target_date"]]), 2),
            "erreur_persistance": (
                None if r["baseline"] is None
                else round(abs(float(r["baseline"]) - anxiety[r["target_date"]]), 2)
            ),
            "dans_intervalle": (
                None if r["interval_low"] is None
                else float(r["interval_low"]) <= anxiety[r["target_date"]] <= float(r["interval_high"])
            ),
            "modele": r["model"],
        }
        for r in rows
        if r["target_date"] in anxiety
    ]
    if not scored:
        return {"n": 0, "mae": None, "mae_persistance": None, "couverture": None, "detail": []}

    covered = [s["dans_intervalle"] for s in scored if s["dans_intervalle"] is not None]
    persistence_errors = [s["erreur_persistance"] for s in scored if s["erreur_persistance"] is not None]
    return {
        "n": len(scored),
        "mae": round(sum(s["erreur"] for s in scored) / len(scored), 2),
        "mae_persistance": (
            round(sum(persistence_errors) / len(persistence_errors), 2)
            if persistence_errors else None
        ),
        # Un intervalle à 95 % qui ne couvre que 60 % des cas est mal calibré, et c'est
        # une information à afficher plutôt qu'à laisser deviner.
        "couverture": round(sum(1 for c in covered if c) / len(covered), 2) if covered else None,
        "detail": scored[:30],
    }
