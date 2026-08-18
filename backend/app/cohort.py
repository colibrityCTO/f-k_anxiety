"""Statistiques collectives : la table de faits, et le garde-fou qui empêche de publier.

## Pourquoi ce module ne montre rien

La demande d'origine était de repérer des régularités sur l'ensemble des utilisateurs —
« les personnes de 28 ans en Europe avec ce niveau d'anxiété qui font une activité
intense ont plus souvent une crise le lendemain ». Techniquement, c'est une requête
d'agrégation. Juridiquement et statistiquement, c'est autre chose.

**Trois contraintes, toutes les trois tenues ici :**

1. **Consentement séparé.** Une ligne n'existe que si `profile.consentements.cohorte`
   vaut `true`. Les données de santé relèvent de l'article 9 du RGPD : le consentement
   doit être explicite, spécifique, distinct de celui du service, et refusable sans
   perte de fonction. C'est le cas — refuser ne retire rien.

2. **Pseudonyme, et pas anonymat.** `user_key` est un HMAC-SHA256 du compte avec le
   secret serveur. Ça réduit le risque ; ça ne rend pas la donnée anonyme. Une donnée
   pseudonymisée reste une donnée personnelle au sens de l'article 4(5), et prétendre
   le contraire serait exactement le genre de confusion qui fait passer un traitement
   pour légal alors qu'il ne l'est pas.

3. **Onze personnes minimum par cellule, sinon rien.** C'est la pratique de référence
   en santé : la politique de suppression de cellules du CMS interdit de publier sous
   onze, et le seuil correspond à un risque de ré-identification d'environ 9 %. Onze
   **personnes distinctes**, pas onze observations — une personne qui contribue trente
   jours ne fait pas une cohorte.

## Ce qui reste à faire quand les effectifs seront là

`compare()` renvoie déjà le refus documenté. Le jour où une strate atteint le seuil,
elle renverra une comparaison — et il faudra alors la faire relire avant de l'afficher,
parce qu'une régularité de cohorte affichée trop tôt devient une croyance chez la
personne qui la lit. Rien dans l'interface ne consomme ce module aujourd'hui.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
from typing import Any

from . import db, stats
from .config import settings

# Onze personnes distinctes par cellule. Le nombre n'est pas choisi par prudence vague :
# c'est le seuil de la politique CMS et il correspond à un risque de ré-identification
# d'environ 9 %.
MIN_CELL = 11


def user_key(user_id: str) -> str:
    """HMAC du compte. Le même compte donne toujours la même clé, sur ce serveur seul.

    Dérivé du secret serveur : deux instances produisent des clés différentes pour le
    même compte, ce qui empêche de recouper deux bases. Et changer le secret rend la
    table inexploitable — c'est un coût réel, assumé pour ne pas avoir un second secret
    à gérer et à oublier.
    """
    return hmac.new(
        settings.jwt_secret.encode("utf-8"),
        f"cohort:{user_id}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def age_band(birth_year: int | None) -> str | None:
    """Tranche de dix ans. Volontairement grossier : « 28 ans » est ré-identifiant."""
    if not birth_year:
        return None
    age = dt.date.today().year - int(birth_year)
    if age < 18 or age > 100:
        return None
    decade = (age // 10) * 10
    return f"{decade}-{decade + 9}"


def consented(profile: dict[str, Any]) -> bool:
    return bool((profile.get("consentements") or {}).get("cohorte") is True)


def contribute(user_id: str, profile: dict[str, Any], day: dt.date, record: dict[str, Any]) -> bool:
    """Verse une journée dans la table de faits. Retourne `False` si non consenti.

    Appelée après la validation du soir. `ON CONFLICT DO UPDATE` plutôt que
    `DO NOTHING` : une correction du check-in doit se propager, sinon la table
    diverge silencieusement de la source.
    """
    if not consented(profile):
        return False

    onboarding = profile.get("onboarding") or {}
    db.execute(
        """
        INSERT INTO cohort_facts
            (user_key, entry_date, age_band, region, difficulties, anxiety_0_10,
             anxiety_peak_0_10, sleep_hours, caffeine_units, alcohol_units, exercise_min,
             avoidance_0_10, panic_attacks, hrv_rmssd_milli, resting_heart_rate,
             session_max_hr)
        VALUES (%(key)s, %(day)s, %(age)s, %(region)s, %(difficulties)s, %(anxiety)s,
                %(peak)s, %(sleep)s, %(caffeine)s, %(alcohol)s, %(exercise)s,
                %(avoidance)s, %(panic)s, %(hrv)s, %(rhr)s, %(session_hr)s)
        ON CONFLICT (user_key, entry_date) DO UPDATE SET
            anxiety_0_10 = EXCLUDED.anxiety_0_10,
            anxiety_peak_0_10 = EXCLUDED.anxiety_peak_0_10,
            sleep_hours = EXCLUDED.sleep_hours,
            caffeine_units = EXCLUDED.caffeine_units,
            alcohol_units = EXCLUDED.alcohol_units,
            exercise_min = EXCLUDED.exercise_min,
            avoidance_0_10 = EXCLUDED.avoidance_0_10,
            panic_attacks = EXCLUDED.panic_attacks,
            hrv_rmssd_milli = EXCLUDED.hrv_rmssd_milli,
            resting_heart_rate = EXCLUDED.resting_heart_rate,
            session_max_hr = EXCLUDED.session_max_hr
        """,
        {
            "key": user_key(user_id),
            "day": day,
            "age": age_band(onboarding.get("annee_naissance")),
            # Le fuseau est le plus fin que l'application connaisse, et il est déjà trop
            # fin : on n'en garde que le continent.
            "region": (profile.get("region") or "").strip() or None,
            "difficulties": profile.get("difficultes") or [],
            "anxiety": record.get("anxiete"),
            "peak": record.get("pic"),
            "sleep": record.get("sommeil"),
            "caffeine": record.get("cafeine"),
            "alcohol": record.get("alcool"),
            "exercise": record.get("sport"),
            "avoidance": record.get("evitement"),
            "panic": record.get("paniques"),
            "hrv": record.get("vfc"),
            "rhr": record.get("fc_repos"),
            "session_hr": record.get("fc_max_seance"),
        },
    )
    return True


def volume() -> dict[str, Any]:
    """Combien de monde, et combien de strates atteignent le seuil.

    Sert à répondre honnêtement à « c'est pour quand ? » : le blocage n'est pas
    technique, il est d'effectif.
    """
    total = db.query_one(
        "SELECT count(DISTINCT user_key) AS personnes, count(*) AS jours FROM cohort_facts"
    )
    strata = db.query_all(
        f"""
        SELECT age_band, region, count(DISTINCT user_key) AS personnes
        FROM cohort_facts
        WHERE age_band IS NOT NULL
        GROUP BY age_band, region
        HAVING count(DISTINCT user_key) >= {MIN_CELL}
        """
    )
    return {
        "personnes": int(total["personnes"]) if total else 0,
        "jours": int(total["jours"]) if total else 0,
        "seuil": MIN_CELL,
        "strates_exploitables": len(strata),
        "message": (
            f"{int(total['personnes']) if total else 0} personne(s) contribuent. Aucune "
            f"comparaison ne sera affichée avant {MIN_CELL} personnes distinctes dans "
            "chaque groupe comparé : en dessous, le chiffre serait à la fois faux et "
            "ré-identifiant."
        ),
    }


def compare(condition_sql: str, params: dict[str, Any]) -> dict[str, Any]:
    """Compare une strate au reste, ou **refuse** si la cellule est trop petite.

    Le refus n'est pas un cas d'erreur : c'est le comportement normal aujourd'hui, et
    il renvoie de quoi l'expliquer. Le jour où le seuil sera franchi, la même fonction
    renverra une différence de proportions avec son intervalle — via `stats`, donc avec
    les mêmes exigences que les analyses individuelles.
    """
    rows = db.query_all(
        f"""
        SELECT ({condition_sql}) AS expose,
               count(DISTINCT user_key) AS personnes,
               count(*) AS jours,
               sum(CASE WHEN panic_attacks > 0 THEN 1 ELSE 0 END) AS avec_crise
        FROM cohort_facts
        GROUP BY 1
        """,
        params,
    )
    by_group = {bool(r["expose"]): r for r in rows}
    exposed, control = by_group.get(True), by_group.get(False)

    if not exposed or not control or min(
        int(exposed["personnes"]), int(control["personnes"])
    ) < MIN_CELL:
        return {
            "affichable": False,
            "personnes_exposees": int(exposed["personnes"]) if exposed else 0,
            "personnes_temoins": int(control["personnes"]) if control else 0,
            "seuil": MIN_CELL,
            "raison": (
                f"Moins de {MIN_CELL} personnes distinctes dans l'un des deux groupes. "
                "Rien n'est renvoyé : sous ce seuil, un chiffre collectif est à la fois "
                "faux et ré-identifiant."
            ),
        }

    result = stats.proportion_difference(
        int(exposed["avec_crise"]), int(exposed["jours"]),
        int(control["avec_crise"]), int(control["jours"]),
    )
    return {
        "affichable": True,
        "personnes_exposees": int(exposed["personnes"]),
        "personnes_temoins": int(control["personnes"]),
        "resultat": result,
        "methode": (
            "différence de proportions entre les jours qui remplissent la condition et "
            f"les autres, avec intervalle de confiance à 95 %. Minimum {MIN_CELL} "
            "personnes distinctes de chaque côté. Les jours d'une même personne ne sont "
            "pas indépendants : ce chiffre est une piste, pas une conclusion."
        ),
    }
