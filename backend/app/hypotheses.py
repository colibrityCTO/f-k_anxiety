"""Hypothèses **pré-enregistrées** : la liste est fermée, et c'est tout l'intérêt.

Le problème que ce module résout. La demande était de repérer des combinaisons —
« une activité intense avec un niveau d'anxiété donné, suivie d'une crise le
lendemain ». Techniquement, rien de plus facile : on croise toutes les variables
deux à deux, on garde ce qui ressort. Et c'est exactement ce qu'il ne faut pas faire.

Avec six variables, trois décalages et deux seuils par variable, on teste des
centaines de combinaisons sur une trentaine de jours. On en trouvera toujours
plusieurs « significatives », et elles seront fausses. Pire : elles arriveront avec
leurs chiffres, leur intervalle de confiance et leur panneau de traçabilité, donc
sous la forme la plus crédible possible. Chez quelqu'un d'anxieux, une fausse
régularité ne reste pas une ligne dans un tableau — elle devient une règle de vie.

La réponse est méthodologique, pas algorithmique : **on écrit les hypothèses à
l'avance**, on en écrit peu, chacune pour une raison clinique documentée, et on les
teste toutes en corrigeant la multiplicité. Une hypothèse pré-enregistrée qui
survit veut dire quelque chose. Une règle trouvée par fouille libre ne vaut rien,
quel que soit son p.

Conséquence assumée : ce module ne « découvrira » jamais un motif auquel personne
n'avait pensé. C'est le prix, et il est moins élevé que l'alternative.

Chaque hypothèse porte :

- `condition` : ce qui définit un jour « exposé », à partir des données du jour ;
- `outcome`   : ce qu'on regarde, sur le jour J + `lag` ;
- `kind`      : `proportion` (l'issue est un événement) ou `moyenne` (l'issue est un
                niveau) — le test statistique en découle ;
- `rationale` : pourquoi cette hypothèse est dans la liste. C'est ce champ qui
                empêche la liste de grossir sans raison.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Callable

from . import stats

# Un « jour » agrégé, tel que `signals.py` le construit déjà.
Day = dict[str, Any]


def _has(day: Day, key: str) -> bool:
    return day.get(key) is not None


HYPOTHESES: list[dict[str, Any]] = [
    # --- Sommeil ------------------------------------------------------------
    {
        "id": "nuit_courte_anxiete",
        "label": "Une nuit de moins de 6 h est suivie d'une journée plus anxieuse",
        "kind": "moyenne",
        "lag": 1,
        "condition": lambda d: d["sommeil"] < 6 if _has(d, "sommeil") else None,
        "outcome": lambda d: d.get("anxiete"),
        "rationale": (
            "La médiation sommeil → anxiété est documentée, et le sommeil est le levier "
            "le plus concret à modifier. Le seuil de 6 h est fixé à l'avance pour ne pas "
            "être déplacé après avoir vu les données."
        ),
    },
    {
        "id": "nuit_courte_panique",
        "label": "Une nuit de moins de 6 h est suivie d'une crise",
        "kind": "proportion",
        "lag": 1,
        "condition": lambda d: d["sommeil"] < 6 if _has(d, "sommeil") else None,
        "outcome": lambda d: (d.get("paniques") or 0) > 0,
        "rationale": (
            "Le manque de sommeil augmente la réactivité autonome, ce qui est le "
            "substrat d'une attaque de panique. Hypothèse distincte de la précédente : "
            "l'anxiété moyenne et la survenue d'une crise ne sont pas la même chose."
        ),
    },
    # --- Caféine ------------------------------------------------------------
    {
        "id": "cafeine_forte_anxiete",
        "label": "Les jours à 3 cafés ou plus sont plus anxieux",
        "kind": "moyenne",
        "lag": 0,
        "condition": lambda d: d["cafeine"] >= 3 if _has(d, "cafeine") else None,
        "outcome": lambda d: d.get("anxiete"),
        "rationale": (
            "La caféine est un agoniste connu des symptômes de panique à dose élevée, et "
            "c'est le changement le moins coûteux à tester : deux semaines suffisent."
        ),
    },
    {
        "id": "cafeine_forte_panique",
        "label": "Les jours à 3 cafés ou plus comptent plus de crises",
        "kind": "proportion",
        "lag": 0,
        "condition": lambda d: d["cafeine"] >= 3 if _has(d, "cafeine") else None,
        "outcome": lambda d: (d.get("paniques") or 0) > 0,
        "rationale": "Même mécanisme, mais sur l'événement plutôt que sur le niveau.",
    },
    # --- Alcool -------------------------------------------------------------
    {
        "id": "alcool_veille_anxiete",
        "label": "L'alcool de la veille rend le lendemain plus anxieux",
        "kind": "moyenne",
        "lag": 1,
        "condition": lambda d: d["alcool"] >= 2 if _has(d, "alcool") else None,
        "outcome": lambda d: d.get("anxiete"),
        "rationale": (
            "Le rebond anxieux post-alcool intervient à distance : le décalage d'un jour "
            "est ce qui distingue cette hypothèse d'une simple corrélation du jour."
        ),
    },
    # --- Activité physique : les deux directions, séparément ---------------
    {
        "id": "sport_modere_anxiete",
        "label": "Une activité physique de 20 min ou plus rend la journée moins anxieuse",
        "kind": "moyenne",
        "lag": 0,
        "condition": lambda d: d["sport"] >= 20 if _has(d, "sport") else None,
        "outcome": lambda d: d.get("anxiete"),
        "rationale": (
            "Effet propre de l'exercice sur l'anxiété. Testé séparément de l'activité "
            "intense : ce ne sont pas les mêmes doses, et pas forcément le même signe."
        ),
    },
    {
        "id": "sport_intense_panique_lendemain",
        "label": "Une activité intense (60 min ou plus) est suivie d'une crise le lendemain",
        "kind": "proportion",
        "lag": 1,
        "condition": lambda d: d["sport"] >= 60 if _has(d, "sport") else None,
        "outcome": lambda d: (d.get("paniques") or 0) > 0,
        "rationale": (
            "C'est l'hypothèse explicitement demandée. Elle est plausible et rarement "
            "regardée : un effort intense produit les sensations que redoute la personne "
            "(cœur rapide, essoufflement, chaleur), ce qui peut agir comme une exposition "
            "involontaire — bénéfique chez certains, déclenchante chez d'autres. Le "
            "signe n'est pas décidé à l'avance, et c'est volontaire. Le seuil basculera "
            "sur la fréquence cardiaque maximale quand un bracelet sera branché."
        ),
    },
    # --- Bracelet -----------------------------------------------------------
    #
    # Ces deux hypothèses n'étaient pas testables sans capteur. La seconde est la
    # reformulation exacte de la demande initiale, dans la seule version que l'API
    # permet : un maximum par séance, pas une série temporelle.
    {
        "id": "vfc_basse_anxiete",
        "label": "Une variabilité cardiaque basse annonce une journée plus anxieuse",
        "kind": "moyenne",
        "lag": 0,
        "condition": lambda d: d["vfc"] < 40 if _has(d, "vfc") else None,
        "outcome": lambda d: d.get("anxiete"),
        "rationale": (
            "La VFC nocturne reflète le tonus parasympathique, et sa chute précède "
            "souvent la journée difficile plutôt qu'elle ne la suit. C'est le meilleur "
            "usage réel du bracelet : un signal de risque journalier, disponible avant "
            "que la journée commence. Le seuil de 40 ms est grossier et fixé à l'avance ; "
            "il passera à un percentile personnel quand il y aura assez de nuits."
        ),
    },
    {
        "id": "fc_max_seance_panique_lendemain",
        "label": "Une séance au-dessus de 150 battements est suivie d'une crise le lendemain",
        "kind": "proportion",
        "lag": 1,
        "condition": lambda d: d["fc_max_seance"] >= 150 if _has(d, "fc_max_seance") else None,
        "outcome": lambda d: (d.get("paniques") or 0) > 0,
        "rationale": (
            "La formulation littérale de la demande, et la seule que l'API rende "
            "possible : elle donne le maximum d'une séance, pas la fréquence à la "
            "minute. Un effort intense produit les sensations redoutées — cœur rapide, "
            "essoufflement, chaleur — ce qui peut agir comme une exposition "
            "involontaire, bénéfique chez certains et déclenchante chez d'autres. Le "
            "signe n'est pas décidé à l'avance."
        ),
    },
    # --- Évitement ----------------------------------------------------------
    {
        "id": "evitement_eleve_lendemain",
        "label": "Une journée d'évitement élevé est suivie d'une journée plus anxieuse",
        "kind": "moyenne",
        "lag": 1,
        "condition": lambda d: d["evitement"] >= 7 if _has(d, "evitement") else None,
        "outcome": lambda d: d.get("anxiete"),
        "rationale": (
            "C'est le cycle de maintien, testé sur les propres données de la personne : "
            "l'évitement soulage sur le moment et coûte ensuite. Si l'hypothèse tient "
            "chez elle, c'est l'argument le plus solide pour commencer les expositions."
        ),
    },
    # --- Ce qui devrait aller dans le bon sens -----------------------------
    {
        "id": "exposition_lendemain",
        "label": "Le lendemain d'une exposition est moins anxieux",
        "kind": "moyenne",
        "lag": 1,
        "condition": lambda d: bool(d.get("exposition")),
        "outcome": lambda d: d.get("anxiete"),
        "rationale": (
            "Hypothèse de contrôle, et elle a une fonction précise : si les expositions "
            "n'améliorent rien chez cette personne sur la durée, il faut le voir plutôt "
            "que de continuer à en proposer parce que la littérature le recommande."
        ),
    },
    {
        "id": "pratique_respiratoire_jour",
        "label": "Les jours avec une pratique respiratoire sont moins anxieux",
        "kind": "moyenne",
        "lag": 0,
        "condition": lambda d: bool(d.get("respiration")),
        "outcome": lambda d: d.get("anxiete"),
        "rationale": (
            "Vérifie sur ses propres données ce que le programme lui demande tous les "
            "jours. Le sens de l'effet est ambigu par construction — on respire *parce "
            "qu'on va mal* — et ce piège est signalé dans le résultat."
        ),
    },
    # --- Combinaisons : deux conditions, et pas plus -----------------------
    #
    # Deux conditions au maximum, jamais trois. Au-delà, l'effectif du groupe exposé
    # tombe sous cinq jours et le résultat devient une anecdote avec un intervalle de
    # confiance — la pire des présentations.
    {
        "id": "nuit_courte_et_cafeine",
        "label": "Nuit courte **et** 3 cafés ou plus : la journée est-elle pire que l'un ou l'autre seul ?",
        "kind": "moyenne",
        "lag": 0,
        "condition": lambda d: (
            (d["sommeil"] < 6 and d["cafeine"] >= 3)
            if _has(d, "sommeil") and _has(d, "cafeine")
            else None
        ),
        "outcome": lambda d: d.get("anxiete"),
        "rationale": (
            "La combinaison la plus courante, et celle sur laquelle une décision simple "
            "est possible : décaler le café les lendemains de mauvaise nuit."
        ),
    },
    {
        "id": "anxiete_haute_et_sport_intense",
        "label": "Anxiété déjà haute (7+) **et** activité intense : crise le lendemain ?",
        "kind": "proportion",
        "lag": 1,
        "condition": lambda d: (
            (d["anxiete"] >= 7 and d["sport"] >= 60)
            if _has(d, "anxiete") and _has(d, "sport")
            else None
        ),
        "outcome": lambda d: (d.get("paniques") or 0) > 0,
        "rationale": (
            "La formulation exacte de la demande initiale. Elle demande beaucoup de "
            "données — il faut des jours où les deux sont vrais — et restera longtemps "
            "non concluante. C'est dit dans le résultat plutôt que contourné."
        ),
    },
]


def _evaluate(
    hypothesis: dict[str, Any], days: dict[dt.date, Day]
) -> dict[str, Any]:
    """Teste une hypothèse. Ne conclut jamais toute seule : la correction vient après."""
    condition: Callable[[Day], bool | None] = hypothesis["condition"]
    outcome: Callable[[Day], Any] = hypothesis["outcome"]
    lag: int = hypothesis["lag"]

    exposed: list[Any] = []
    control: list[Any] = []
    examples: list[dict[str, Any]] = []

    for day in sorted(days):
        source = days[day]
        target = days.get(day + dt.timedelta(days=lag))
        if target is None:
            continue
        try:
            flag = condition(source)
        except (TypeError, KeyError):
            flag = None
        if flag is None:
            continue
        value = outcome(target)
        if value is None:
            continue
        (exposed if flag else control).append(value)
        if flag and len(examples) < 10:
            examples.append(
                {
                    "date": str(day),
                    "issue_le": str(day + dt.timedelta(days=lag)),
                    "issue": value,
                }
            )

    if hypothesis["kind"] == "proportion":
        result = stats.proportion_difference(
            sum(1 for v in exposed if v), len(exposed),
            sum(1 for v in control if v), len(control),
        )
    else:
        result = stats.mean_difference(
            [float(v) for v in exposed], [float(v) for v in control]
        )

    return {
        "id": hypothesis["id"],
        "label": hypothesis["label"],
        "kind": hypothesis["kind"],
        "lag": lag,
        "pourquoi": hypothesis["rationale"],
        "resultat": result,
        "observations": examples,
    }


def evaluate_all(days: dict[dt.date, Day]) -> dict[str, Any]:
    """Teste la liste entière et applique la correction de multiplicité.

    Le compte des hypothèses **testables** (celles dont les deux groupes atteignent
    l'effectif minimal) fait partie du résultat : dire « 2 retenues » sans dire
    « sur 4 testables et 12 écrites » serait trompeur, parce que le lecteur ne pourrait
    pas juger de la sévérité du filtre.
    """
    evaluated = [_evaluate(h, days) for h in HYPOTHESES]
    survivors = stats.benjamini_hochberg(
        [e["resultat"]["p"] if e["resultat"]["concluant"] else None for e in evaluated]
    )
    for entry, survives in zip(evaluated, survivors, strict=True):
        entry["retenu"] = bool(survives)
        entry["verdict"] = _verdict(entry)

    testable = [e for e in evaluated if e["resultat"]["concluant"]]
    retained = [e for e in evaluated if e["retenu"]]
    return {
        "methode": (
            f"{len(HYPOTHESES)} hypothèses écrites **à l'avance**, jamais choisies après "
            "avoir vu les données. Chacune compare les jours qui remplissent la condition "
            "aux autres, avec son intervalle de confiance à 95 %. Correction de "
            f"Benjamini-Hochberg sur l'ensemble (seuil {stats.FDR_ALPHA}), et minimum "
            f"{stats.MIN_GROUP} jours dans chaque groupe. Aucune fouille automatique : une "
            "règle trouvée en croisant tout avec tout ne vaut rien, quel que soit son p."
        ),
        "ecrites": len(HYPOTHESES),
        "testables": len(testable),
        "retenues": len(retained),
        "hypotheses": evaluated,
    }


def _verdict(entry: dict[str, Any]) -> str:
    result = entry["resultat"]
    n1, n0 = result["n_expose"], result["n_controle"]

    if not result["concluant"]:
        return (
            f"pas encore testable : {n1} jour(s) avec la condition, {n0} sans "
            f"({stats.MIN_GROUP} minimum de chaque côté)"
        )

    if entry["kind"] == "proportion":
        gap = result["difference"]
        span = f"intervalle {result['ic_bas']} à {result['ic_haut']}"
        body = (
            f"{round(result['taux_expose'] * 100)} % contre "
            f"{round(result['taux_controle'] * 100)} %, soit {gap:+.0%} "
            f"({span}, p = {result['p']}, {n1} vs {n0} jours)"
        )
    else:
        gap = result["difference"]
        span = f"intervalle {result['ic_bas']} à {result['ic_haut']}"
        body = (
            f"{result['moyenne_expose']} contre {result['moyenne_controle']}, soit "
            f"{gap:+.2f} point ({span}, p = {result['p']}, {n1} vs {n0} jours)"
        )

    if not entry["retenu"]:
        return f"{body} — ne survit pas à la correction de multiplicité"
    return f"{body} — **retenue**. Association, pas causalité : à tester en changeant une seule chose."
