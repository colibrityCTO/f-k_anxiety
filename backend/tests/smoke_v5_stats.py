"""Test de fumée du lot 3 : les statistiques honnêtes.

    cd backend && PYTHONPATH=. python tests/smoke_v5_stats.py

Le test le plus important de la série, et le seul qui vérifie une **absence** :
qu'on ne trouve rien dans du bruit. C'est ce qui manquait. L'ancienne version
déclenchait une corrélation dès 6 paires et affichait « association marquée » à
partir de |r| ≥ 0,6 — à ce volume, elle présentait donc régulièrement du hasard
comme un fait, avec ses chiffres et son panneau de traçabilité.

Cinq blocs :

1. Les outils de `stats.py` : intervalle de Fisher, Benjamini-Hochberg, différences
   premières, différence de proportions.
2. **Bruit pur sur 40 jours** → aucune corrélation retenue, aucune hypothèse retenue.
3. **Effet planté** (nuit courte → anxiété plus haute) → détecté et retenu.
4. **Petit échantillon** → non concluant même quand r est élevé.
5. Les règles adaptatives ne se déclenchent plus sur une corrélation non retenue.
"""

from __future__ import annotations

import datetime as dt
import random

from fastapi.testclient import TestClient

from app import db, hypotheses, program, signals as signals_mod, stats
from app.main import app

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    print(f"[{'OK ' if condition else 'ERR'}] {label}")
    if detail:
        print(f"      {detail}")
    if not condition:
        FAILURES.append(label)


def seed(client, headers, user_id, rows):
    """Écrit une série de jours. `rows` : (offset, anxiete, sommeil, cafeine, paniques)."""
    today = dt.date.today()
    for offset, anxiety, sleep, caffeine, panic in rows:
        db.execute(
            """
            INSERT INTO daily_checkins
                (user_id, entry_date, moment, anxiety_0_10, sleep_hours, caffeine_units,
                 alcohol_units, exercise_min, avoidance_0_10, panic_attacks)
            VALUES (%s, %s, 'soir', %s, %s, %s, 0, 0, 4, %s)
            ON CONFLICT (user_id, entry_date, moment) DO UPDATE SET
                anxiety_0_10 = EXCLUDED.anxiety_0_10,
                sleep_hours = EXCLUDED.sleep_hours,
                caffeine_units = EXCLUDED.caffeine_units,
                panic_attacks = EXCLUDED.panic_attacks
            """,
            (user_id, today - dt.timedelta(days=offset), anxiety, sleep, caffeine, panic),
        )


def register(client, tag):
    email = f"{tag}{dt.datetime.now().strftime('%H%M%S%f')[:12]}@exemple.fr"
    auth = client.post(
        "/auth/register", json={"email": email, "password": "motdepasse-tres-long-2026"}
    ).json()
    return {"Authorization": f"Bearer {auth['access_token']}"}, auth["user"]["id"]


# --- 1. Les outils ---------------------------------------------------------
print("=== stats.py ===")

perfect = stats.correlation([(float(i), float(i)) for i in range(20)])
check(
    "une corrélation parfaite est reconnue comme telle",
    perfect["r"] == 1.0 and perfect["ic_bas"] is None,
    "r = 1 exactement : la transformée de Fisher n'est pas définie, "
    "donc pas d'intervalle inventé",
)

strong = stats.correlation([(float(i), float(i) + (i % 3)) for i in range(20)])
check(
    "un intervalle de confiance encadre le coefficient",
    strong["ic_bas"] is not None and strong["ic_bas"] < strong["r"] < strong["ic_haut"],
    f"r = {strong['r']}, intervalle {strong['ic_bas']} à {strong['ic_haut']}, p = {strong['p']}",
)

small = stats.correlation([(1.0, 2.0), (2.0, 3.5), (3.0, 5.0), (4.0, 7.0), (5.0, 9.0), (6.0, 11.0)])
check(
    "6 paires ne suffisent pas, même avec un r proche de 1",
    small["r"] is not None and small["r"] > 0.98 and not small["concluant"],
    f"r = {small['r']} sur 6 paires → concluant = {small['concluant']} "
    f"(seuil : {stats.MIN_PAIRS} paires)",
)

rejected = stats.benjamini_hochberg([0.001, 0.04, 0.30, 0.80, None])
check(
    "Benjamini-Hochberg retient les plus petits p et écarte le reste",
    rejected == [True, True, False, False, False],
    f"p = [0.001, 0.04, 0.30, 0.80, non calculable] → {rejected}",
)

series = {dt.date(2026, 1, d): float(d * 2) for d in (1, 2, 3, 5)}
deltas = stats.first_differences(series)
check(
    "les différences premières ne sautent pas les jours manquants",
    sorted(str(d) for d in deltas) == ["2026-01-02", "2026-01-03"],
    f"jours présents 1, 2, 3, 5 → variations calculées pour {sorted(str(d) for d in deltas)} "
    "(le 5 n'a pas de veille)",
)

prop = stats.proportion_difference(8, 10, 2, 10)
check(
    "la différence de proportions porte son intervalle",
    prop["difference"] == 0.6 and prop["concluant"],
    f"80 % contre 20 % → {prop['difference']:+} "
    f"(intervalle {prop['ic_bas']} à {prop['ic_haut']}, p = {prop['p']})",
)
tiny = stats.proportion_difference(2, 2, 0, 3)
check(
    "deux jours exposés ne concluent rien",
    not tiny["concluant"],
    f"n_expose = {tiny['n_expose']} < {stats.MIN_GROUP}",
)

with TestClient(app) as client:
    # --- 2. Du bruit ne doit rien produire --------------------------------
    print("\n=== bruit pur, 40 jours ===")
    rng = random.Random(20260818)
    h_noise, id_noise = register(client, "stnoise")
    noise_rows = [
        (
            offset,
            rng.randint(0, 10),
            round(rng.uniform(4.0, 9.0), 1),
            rng.randint(0, 4),
            1 if rng.random() < 0.2 else 0,
        )
        for offset in range(1, 41)
    ]
    seed(client, h_noise, id_noise, noise_rows)

    sig = signals_mod.compute(id_noise, days=60)
    by_id = {s["id"]: s for s in sig["signaux"]}
    corr_ids = [k for k in by_id if k.startswith("correlation")]
    retained_corr = [k for k in corr_ids if by_id[k].get("retenu")]
    check(
        "aucune corrélation retenue sur du bruit",
        not retained_corr,
        f"{len(corr_ids)} associations testées sur 40 jours de données aléatoires, "
        f"{len(retained_corr)} retenue(s) — "
        + ", ".join(f"{k.split('_')[1]} r={by_id[k]['value_variations']}" for k in corr_ids),
    )
    hypo = by_id["hypotheses"]
    check(
        "aucune hypothèse retenue sur du bruit",
        hypo["n"] > 0 and len(hypo["value"]) == 0,
        f"{hypo['verdict']} — et il y avait bien de quoi tester, "
        "donc c'est une absence, pas un manque de données",
    )
    check(
        "les hypothèses non retenues disent pourquoi elles ont été testées",
        all(o["pourquoi_testee"] for o in hypo["observations"]),
        "chaque hypothèse porte sa justification clinique : c'est ce qui empêche la "
        "liste de grossir sans raison",
    )

    # --- 3. Un effet réel doit être vu ------------------------------------
    print("\n=== effet planté : nuit courte → anxiété plus haute ===")
    h_real, id_real = register(client, "streal")
    rng2 = random.Random(4242)
    real_rows = []
    for offset in range(1, 45):
        short = offset % 2 == 0
        sleep = round(rng2.uniform(4.0, 5.5), 1) if short else round(rng2.uniform(7.0, 8.5), 1)
        # L'effet est planté sur le **lendemain** de la nuit, donc sur l'anxiété du jour
        # suivant : c'est la direction que l'hypothèse teste.
        base = 7 if (offset - 1) % 2 == 0 else 3
        real_rows.append((offset, max(0, min(10, base + rng2.randint(-1, 1))), sleep, 1, 0))
    seed(client, h_real, id_real, real_rows)

    sig2 = signals_mod.compute(id_real, days=60)
    by2 = {s["id"]: s for s in sig2["signaux"]}
    sleep_corr = by2["correlation_sommeil_anxiete"]
    check(
        "l'association sommeil → anxiété du lendemain est détectée",
        sleep_corr["retenu"] is True,
        f"variations r = {sleep_corr['value_variations']}, "
        f"intervalle {sleep_corr['ic'][0]} à {sleep_corr['ic'][1]}, p = {sleep_corr['p']}",
    )
    check(
        "le verdict cite l'intervalle et refuse la causalité",
        "intervalle" in sleep_corr["verdict"] and "causalit" in sleep_corr["verdict"],
        f"« {sleep_corr['verdict'][:130]} »",
    )
    hypo2 = by2["hypotheses"]
    kept = [h["id"] for h in hypo2["value"]]
    check(
        "l'hypothèse pré-enregistrée correspondante est retenue",
        "nuit_courte_anxiete" in kept,
        f"retenues : {kept or 'aucune'} — {hypo2['verdict']}",
    )

    # --- 4. Le brut et les variations peuvent divergier -------------------
    print("\n=== dérive commune ===")
    h_drift, id_drift = register(client, "stdrift")
    # Deux séries qui montent ensemble sans lien jour à jour : c'est exactement ce que
    # la corrélation en niveau brut confond avec une association.
    drift_rows = [
        (45 - offset, min(10, offset // 4), round(9.0 - offset * 0.08, 1), 1, 0)
        for offset in range(1, 41)
    ]
    seed(client, h_drift, id_drift, drift_rows)
    sig3 = signals_mod.compute(id_drift, days=60)
    by3 = {s["id"]: s for s in sig3["signaux"]}
    drift = by3["correlation_sommeil_anxiete"]
    check(
        "la dérive commune est visible dans l'écart brut / variations",
        drift["value"] is not None
        and drift["value_variations"] is not None
        and abs(drift["value"]) > abs(drift["value_variations"]),
        f"brut r = {drift['value']} (deux séries qui dérivent ensemble) → "
        f"variations r = {drift['value_variations']} : la dérive expliquait l'essentiel",
    )

    # --- 5. Les règles adaptatives respectent la correction --------------
    print("\n=== couche adaptative ===")
    items = program.adaptive_items(sig, {})
    slugs = [i["slug"] for i in items]
    check(
        "rien de déclenché par une corrélation non retenue (compte « bruit »)",
        "regularite-sommeil" not in slugs and "reduction-cafeine" not in slugs,
        f"items adaptatifs proposés : {slugs or 'aucun'} — aucun ne vient d'une "
        "corrélation, alors que l'ancienne version en aurait déclenché",
    )
    items_real = program.adaptive_items(sig2, {})
    check(
        "et déclenché quand l'association tient (compte « effet planté »)",
        "regularite-sommeil" in [i["slug"] for i in items_real],
        f"items : {[i['slug'] for i in items_real]}",
    )
    why = next((i["why"] for i in items_real if i["slug"] == "regularite-sommeil"), "")
    check(
        "la justification affichée porte l'intervalle de confiance",
        "intervalle" in why,
        f"« {why[:150]} »",
    )

    # --- La liste des hypothèses reste fermée ---------------------------
    check(
        "la liste des hypothèses est fermée et documentée",
        all(h.get("rationale") for h in hypotheses.HYPOTHESES)
        and len(hypotheses.HYPOTHESES) == len({h["id"] for h in hypotheses.HYPOTHESES}),
        f"{len(hypotheses.HYPOTHESES)} hypothèses, identifiants uniques, "
        "toutes justifiées — aucune fouille automatique",
    )

print()
if FAILURES:
    print(f"[ERR] {len(FAILURES)} vérification(s) en échec :")
    for name in FAILURES:
        print(f"       - {name}")
    raise SystemExit(1)
print("[OK ] lot 3 : toutes les vérifications passent")
