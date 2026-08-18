"""Statistiques élémentaires, en Python pur, avec leurs bornes d'incertitude.

Pourquoi ce module existe, et ce qu'il corrige.

`signals.py` déclenchait une corrélation de Pearson dès **6 paires** et affichait
« association marquée » à partir de |r| ≥ 0,6. À n = 6, un r de 0,7 n'est pas
significatif : l'application présentait donc du bruit comme un fait. Chez quelqu'un
d'anxieux, un faux motif coûte plus cher qu'une absence de motif — il devient une
croyance, et la croyance oriente les décisions.

Quatre corrections, et chacune répond à un problème précis :

1. **Un seuil de n honnête** (`MIN_PAIRS`) et un **intervalle de confiance** plutôt
   qu'un adjectif. « r = 0,52, intervalle −0,05 à 0,84 » dit quelque chose de vrai ;
   « association modérée » ne dit rien de son incertitude.
2. **La correction de multiplicité** (Benjamini-Hochberg). Cinq corrélations, deux
   décalages, plusieurs fenêtres : on trouvera toujours *quelque chose*. Sans
   correction, l'application fabrique des motifs.
3. **Les différences premières.** L'anxiété est fortement autocorrélée d'un jour sur
   l'autre. Deux séries qui dérivent ensemble sur trois semaines corrèlent fortement
   sans aucun lien : corréler les *variations* jour à jour retire cette dérive.
4. **Des comparaisons de proportions avec leur incertitude**, pour les hypothèses du
   type « les jours où X, une crise le lendemain est-elle plus fréquente ? ».

Aucune dépendance externe : `math.erf` suffit pour la loi normale, et toutes les
statistiques d'ici s'y ramènent. C'est le même choix que le reste du projet — un
chiffre de santé ne doit pas dépendre d'une version de bibliothèque.
"""

from __future__ import annotations

import datetime as dt
import math
from typing import Any

# Minimum de paires avant d'afficher un verdict de corrélation. 14 et non 6 : sous
# une quinzaine de points, l'intervalle de confiance couvre presque tout l'intervalle
# possible, donc le chiffre ne permet aucune conclusion. On continue de montrer les
# données brutes en dessous — c'est le *verdict* qu'on retient, pas l'observation.
MIN_PAIRS = 14

# Minimum d'observations dans chaque groupe pour comparer deux proportions.
MIN_GROUP = 5

# Seuil de la correction de multiplicité. 0,10 et non 0,05 : à cette échelle de
# données, un seuil plus strict ne laisserait jamais rien passer, et l'objectif ici
# n'est pas de publier mais de proposer une piste à tester sur deux semaines.
FDR_ALPHA = 0.10


def normal_cdf(z: float) -> float:
    """Fonction de répartition de la loi normale centrée réduite."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def two_sided_p(z: float) -> float:
    return 2.0 * (1.0 - normal_cdf(abs(z)))


def mean(values: list[float]) -> float | None:
    clean = [v for v in values if v is not None]
    return sum(clean) / len(clean) if clean else None


def median(values: list[float]) -> float | None:
    clean = sorted(v for v in values if v is not None)
    if not clean:
        return None
    middle = len(clean) // 2
    if len(clean) % 2:
        return float(clean[middle])
    return (clean[middle - 1] + clean[middle]) / 2


def pearson(pairs: list[tuple[float, float]]) -> float | None:
    """Coefficient de Pearson. `None` si le calcul est impossible (variance nulle)."""
    n = len(pairs)
    if n < 3:
        return None
    mx = sum(p[0] for p in pairs) / n
    my = sum(p[1] for p in pairs) / n
    num = sum((x - mx) * (y - my) for x, y in pairs)
    dx = math.sqrt(sum((x - mx) ** 2 for x, _ in pairs))
    dy = math.sqrt(sum((y - my) ** 2 for _, y in pairs))
    if dx == 0 or dy == 0:
        return None
    return max(-1.0, min(1.0, num / (dx * dy)))


def correlation(pairs: list[tuple[float, float]]) -> dict[str, Any]:
    """Corrélation **avec son incertitude**, par la transformée de Fisher.

    `z = atanh(r)` est approximativement normal d'écart-type `1/√(n−3)`, ce qui donne
    un intervalle de confiance et une valeur p sans table de Student ni dépendance.
    L'approximation est bonne dès une quinzaine de points — c'est-à-dire exactement à
    partir de `MIN_PAIRS`, ce qui n'est pas une coïncidence.

    `concluant` est faux quand l'échantillon est trop petit : dans ce cas `r` est tout
    de même renvoyé, mais l'appelant ne doit pas en tirer de verdict.
    """
    n = len(pairs)
    r = pearson(pairs)
    out: dict[str, Any] = {
        "r": None if r is None else round(r, 3),
        "n": n,
        "ic_bas": None,
        "ic_haut": None,
        "p": None,
        "concluant": False,
    }
    if r is None or n < 4 or abs(r) >= 1.0:
        return out

    z = math.atanh(r)
    se = 1.0 / math.sqrt(max(1, n - 3))
    out["ic_bas"] = round(math.tanh(z - 1.96 * se), 3)
    out["ic_haut"] = round(math.tanh(z + 1.96 * se), 3)
    out["p"] = round(two_sided_p(z / se), 4)
    out["concluant"] = n >= MIN_PAIRS
    return out


def first_differences(series: dict[dt.date, float]) -> dict[dt.date, float]:
    """Variation d'un jour sur l'autre, uniquement entre jours **consécutifs**.

    Le contrôle sur la consécutivité est ce qui rend l'opération honnête : soustraire
    la valeur d'il y a cinq jours ne produit pas une « variation quotidienne », ça
    produit un chiffre qui n'a pas de nom.
    """
    out: dict[dt.date, float] = {}
    for day, value in series.items():
        previous = day - dt.timedelta(days=1)
        if previous in series:
            out[day] = value - series[previous]
    return out


def benjamini_hochberg(pvalues: list[float | None], alpha: float = FDR_ALPHA) -> list[bool]:
    """Contrôle du taux de faux positifs sur une famille de tests.

    Sans cette correction, tester cinq associations à 5 % donne environ une chance
    sur quatre de trouver au moins un « résultat » sur des données sans aucun lien.
    L'application afficherait alors une régularité inventée, avec ses chiffres et son
    panneau de traçabilité — c'est-à-dire de manière parfaitement convaincante.

    Les `None` (tests non calculables) ne comptent pas dans la famille : les inclure
    diluerait la correction et rendrait le seuil trop permissif.
    """
    indexed = [(i, p) for i, p in enumerate(pvalues) if p is not None]
    rejected = [False] * len(pvalues)
    if not indexed:
        return rejected

    indexed.sort(key=lambda item: item[1])
    m = len(indexed)
    threshold_rank = 0
    for rank, (_, p) in enumerate(indexed, start=1):
        if p <= alpha * rank / m:
            threshold_rank = rank
    for rank, (index, _) in enumerate(indexed, start=1):
        if rank <= threshold_rank:
            rejected[index] = True
    return rejected


def proportion_difference(
    exposed_events: int, exposed_total: int, control_events: int, control_total: int
) -> dict[str, Any]:
    """Différence de deux proportions, avec intervalle de confiance et valeur p.

    Sert aux hypothèses de la forme « les jours où X, la probabilité de Y est-elle
    plus élevée ? ». La différence de risque est préférée au rapport de cotes : elle
    se lit directement (« 18 points de plus ») là où un rapport de cotes de 3,2 sur
    un événement rare est systématiquement surinterprété.

    `concluant` exige `MIN_GROUP` observations **dans chaque groupe** : une différence
    calculée sur deux jours exposés n'est pas une différence, c'est une anecdote.
    """
    out: dict[str, Any] = {
        "taux_expose": None,
        "taux_controle": None,
        "difference": None,
        "ic_bas": None,
        "ic_haut": None,
        "p": None,
        "n_expose": exposed_total,
        "n_controle": control_total,
        "concluant": False,
    }
    if exposed_total == 0 or control_total == 0:
        return out

    p1 = exposed_events / exposed_total
    p0 = control_events / control_total
    out["taux_expose"] = round(p1, 3)
    out["taux_controle"] = round(p0, 3)
    out["difference"] = round(p1 - p0, 3)

    variance = p1 * (1 - p1) / exposed_total + p0 * (1 - p0) / control_total
    if variance <= 0:
        return out
    se = math.sqrt(variance)
    out["ic_bas"] = round((p1 - p0) - 1.96 * se, 3)
    out["ic_haut"] = round((p1 - p0) + 1.96 * se, 3)
    out["p"] = round(two_sided_p((p1 - p0) / se), 4)
    out["concluant"] = exposed_total >= MIN_GROUP and control_total >= MIN_GROUP
    return out


def mean_difference(exposed: list[float], control: list[float]) -> dict[str, Any]:
    """Différence de deux moyennes (Welch, variances non supposées égales).

    Welch et non Student : les deux groupes n'ont aucune raison d'avoir la même
    dispersion — les jours à forte caféine peuvent être plus variables que les autres,
    et supposer le contraire fabriquerait de la précision qui n'existe pas.
    """
    out: dict[str, Any] = {
        "moyenne_expose": None,
        "moyenne_controle": None,
        "difference": None,
        "ic_bas": None,
        "ic_haut": None,
        "p": None,
        "n_expose": len(exposed),
        "n_controle": len(control),
        "concluant": False,
    }
    if len(exposed) < 2 or len(control) < 2:
        return out

    m1, m0 = sum(exposed) / len(exposed), sum(control) / len(control)
    v1 = sum((x - m1) ** 2 for x in exposed) / (len(exposed) - 1)
    v0 = sum((x - m0) ** 2 for x in control) / (len(control) - 1)
    out["moyenne_expose"] = round(m1, 2)
    out["moyenne_controle"] = round(m0, 2)
    out["difference"] = round(m1 - m0, 2)

    se = math.sqrt(v1 / len(exposed) + v0 / len(control))
    if se <= 0:
        return out
    out["ic_bas"] = round((m1 - m0) - 1.96 * se, 2)
    out["ic_haut"] = round((m1 - m0) + 1.96 * se, 2)
    out["p"] = round(two_sided_p((m1 - m0) / se), 4)
    out["concluant"] = len(exposed) >= MIN_GROUP and len(control) >= MIN_GROUP
    return out


def describe_correlation(result: dict[str, Any], survives: bool) -> str:
    """Le verdict en français, incertitude comprise, sans adjectif trompeur.

    Trois cas distincts que l'ancienne version confondait : pas assez de données,
    assez de données mais rien qui survive à la correction, et une association qui
    tient. Le deuxième cas est le plus important à formuler correctement — « rien
    trouvé » n'est pas « il n'y a rien », c'est « pas avec ce volume de données ».
    """
    n = result["n"]
    if result["r"] is None:
        return f"non calculable ({n} paire(s))"
    if not result["concluant"]:
        return (
            f"r = {result['r']} sur {n} paire(s) — en dessous de {MIN_PAIRS}, "
            "l'incertitude est trop large pour conclure quoi que ce soit"
        )
    span = f"intervalle {result['ic_bas']} à {result['ic_haut']}"
    if not survives:
        return (
            f"r = {result['r']} ({span}, p = {result['p']}) — ne survit pas à la "
            f"correction de multiplicité : à ce stade, indistinguable du hasard"
        )
    direction = "plus" if result["r"] > 0 else "moins"
    return (
        f"r = {result['r']} ({span}, p = {result['p']}) — association retenue : "
        f"quand l'un monte, l'autre est {direction} élevé. Ce n'est pas une causalité."
    )
