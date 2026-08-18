"""Test de fumée du lot 1 de la V5 : le check-in éclaté en trois moments.

    cd backend && PYTHONPATH=. python tests/smoke_v5_moments.py

Ce que ça vérifie, et pourquoi chaque point compte :

1. **Matin et soir sont deux lignes distinctes**, pas deux écritures sur la même.
2. **Le sommeil porte sa provenance.** Sans `sleep_source`, une corrélation
   sommeil → anxiété mélangerait déclaratif et capteur, et son coefficient ne
   voudrait rien dire.
3. **Les mesures instantanées s'empilent.** C'est ce que `daily_checkins` ne peut
   pas faire : sa clé unique interdit huit valeurs dans la journée.
4. **Le soir arrive pré-rempli, calculé.** Pic et moyenne viennent des mesures du
   jour au lieu d'être reconstruits de mémoire.
5. **L'anxiété du jour n'est pas une moyenne des moments.** C'est le piège du
   découpage : le matin mesure un instant, le soir mesure une journée. Les
   additionner produirait un chiffre qui ne mesure rien — et toutes les
   corrélations en dépendent.
6. **Les paniques sont dérivées des épisodes déclarés**, pas du souvenir du soir.
7. **La résolution intra-journée existe** : le signal des tranches horaires.
"""

from __future__ import annotations

import datetime as dt

from fastapi.testclient import TestClient

from app import db, signals as signals_mod
from app.main import app

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    print(f"[{'OK ' if condition else 'ERR'}] {label}")
    if detail:
        print(f"      {detail}")
    if not condition:
        FAILURES.append(label)


def open_widget(client, headers, kind):
    body = client.post("/chat/widget", headers=headers, json={"type": kind}).json()
    return next(i for i in body["items"] if i.get("widget_type") == kind)


def submit(client, headers, item, values):
    return client.post(
        f"/chat/widget/{item['id']}/submit", headers=headers, json={"values": values}
    )


with TestClient(app) as client:
    email = f"v5m{dt.datetime.now().strftime('%H%M%S')}@exemple.fr"
    auth = client.post(
        "/auth/register", json={"email": email, "password": "motdepasse-tres-long-2026"}
    ).json()
    h = {"Authorization": f"Bearer {auth['access_token']}"}
    user_id = auth["user"]["id"]
    today = dt.date.today()
    print(f"[OK ] compte créé : {email}")

    # --- 1 & 2. Le matin : la nuit, l'instant, l'intention -----------------
    matin = open_widget(client, h, "matin")
    response = submit(
        client, h, matin,
        {
            "sleep_hours": 5.5, "sleep_quality_0_10": 3, "sleep_source": "declare",
            "anxiety_0_10": 7, "main_trigger": "la réunion de 15 h",
            "intention": "y aller sans préparer mes phrases",
        },
    )
    check("le matin s'enregistre", response.status_code == 200, f"HTTP {response.status_code}")

    rows = {
        r["moment"]: r
        for r in db.query_all(
            """
            SELECT moment, anxiety_0_10, anxiety_peak_0_10, sleep_hours, sleep_source
            FROM daily_checkins WHERE user_id = %s AND entry_date = %s
            """,
            (user_id, today),
        )
    }
    check(
        "le matin écrit sa propre ligne, sur le moment « matin »",
        "matin" in rows and rows["matin"]["sleep_hours"] is not None,
        f"moments en base : {sorted(rows)}",
    )
    check(
        "le sommeil porte sa provenance",
        rows.get("matin", {}).get("sleep_source") == "declare",
        f"sleep_source={rows.get('matin', {}).get('sleep_source')!r}",
    )

    # L'intention du matin devient une entrée de journal, donc de la mémoire.
    intention = db.query_one(
        """
        SELECT free_text FROM journal_entries
        WHERE user_id = %s AND entry_date = %s AND kind = 'libre'
        ORDER BY created_at DESC LIMIT 1
        """,
        (user_id, today),
    )
    check(
        "la phrase du matin est écrite en clair dans le journal",
        intention is not None and "malgré ça" in (intention["free_text"] or ""),
        f"« {(intention or {}).get('free_text', '—')} »",
    )

    # --- 3. Les mesures instantanées s'empilent ---------------------------
    for value in (4, 9, 6, 8, 5):
        spot = open_widget(client, h, "maintenant")
        submit(client, h, spot, {"anxiety_0_10": value, "contexts": ["transports", "seul"]})
    count = db.query_one(
        "SELECT count(*) AS n, max(anxiety_0_10) AS pic FROM momentary_ratings WHERE user_id = %s",
        (user_id,),
    )
    check(
        "cinq mesures dans la même journée cohabitent",
        int(count["n"]) == 5,
        f"{count['n']} mesure(s) · pic {count['pic']} — impossible dans daily_checkins, "
        "dont la clé est (user, jour, moment)",
    )

    refused = submit(client, h, open_widget(client, h, "maintenant"), {"note": "sans chiffre"})
    check(
        "une mesure sans chiffre est refusée",
        refused.status_code == 422,
        f"HTTP {refused.status_code}",
    )

    # --- 6. Un épisode de panique déclaré ---------------------------------
    db.execute(
        """
        INSERT INTO panic_episodes
            (user_id, entry_date, what_preceded, thought_in_moment, anxiety_peak,
             time_to_relief_min, what_actually_happened)
        VALUES (%s, %s, 'métro bondé', 'je vais m''évanouir', 9, 12, 'rien')
        """,
        (user_id, today),
    )

    # --- 4. Le soir arrive pré-rempli, calculé ----------------------------
    soir = open_widget(client, h, "soir")
    prefill = soir["payload"]["prefill"]
    check(
        "le soir est pré-rempli avec le pic et la moyenne calculés",
        prefill.get("anxiety_peak_0_10") == 9 and prefill.get("anxiety_0_10") == 6,
        f"pic={prefill.get('anxiety_peak_0_10')} · moyenne={prefill.get('anxiety_0_10')} "
        f"(mesures : 4, 9, 6, 8, 5 → pic 9, moyenne 6.4 arrondie à 6)",
    )
    check(
        "le pré-rempli est signalé comme calculé, pas comme une saisie",
        set(prefill.get("_derive") or []) >= {"anxiety_peak_0_10", "anxiety_0_10", "panic_attacks"},
        f"_derive={prefill.get('_derive')}",
    )
    check(
        "les paniques sont comptées sur les épisodes déclarés",
        prefill.get("panic_attacks") == 1,
        f"panic_attacks={prefill.get('panic_attacks')}",
    )

    submit(
        client, h, soir,
        {
            "anxiety_0_10": 6, "anxiety_peak_0_10": 9, "avoidance_0_10": 7,
            "caffeine_units": 4, "alcohol_units": 2, "exercise_min": 0,
            # Volontairement faux : le compte réel doit gagner.
            "panic_attacks": 0,
        },
    )
    evening = db.query_one(
        """
        SELECT anxiety_0_10, anxiety_peak_0_10, panic_attacks, sleep_hours
        FROM daily_checkins WHERE user_id = %s AND entry_date = %s AND moment = 'soir'
        """,
        (user_id, today),
    )
    check(
        "le soir garde le pic et la moyenne séparés",
        evening["anxiety_0_10"] == 6 and evening["anxiety_peak_0_10"] == 9,
        f"moyenne {evening['anxiety_0_10']} · pic {evening['anxiety_peak_0_10']}",
    )
    check(
        "le compte réel de paniques écrase ce qu'on croyait se rappeler le soir",
        evening["panic_attacks"] == 1,
        f"envoyé 0, enregistré {evening['panic_attacks']} (1 épisode déclaré)",
    )
    check(
        "le soir n'écrase pas le sommeil du matin : ce sont deux lignes",
        evening["sleep_hours"] is None and rows["matin"]["sleep_hours"] is not None,
        f"soir.sleep_hours={evening['sleep_hours']} · matin.sleep_hours={rows['matin']['sleep_hours']}",
    )

    # --- 5. L'anxiété du jour n'est pas une moyenne des moments -----------
    sig = signals_mod.compute(user_id, today, 21)
    by_id = {s["id"]: s for s in sig["signaux"]}
    assiduite = by_id["assiduite_checkin"]
    day_value = next(
        (o["anxiete"] for o in assiduite["observations"] if o["date"] == str(today)), None
    )
    check(
        "l'anxiété du jour est celle du soir (6), pas la moyenne matin+soir (6.5)",
        day_value == 6,
        f"retenu {day_value} · matin 7, soir 6 — une moyenne aurait donné 6.5, "
        "ce qui mélange un instant et une journée",
    )

    # --- 7. Résolution intra-journée --------------------------------------
    tranches = by_id.get("tranches_horaires")
    check(
        "le signal des tranches horaires existe et reste prudent",
        tranches is not None and tranches["n"] == 5,
        f"{tranches['verdict'] if tranches else '—'}",
    )
    check(
        "les mesures instantanées sont comptées dans le volume brut",
        sig["brut"].get("mesures_instantanees") == 5,
        f"brut.mesures_instantanees={sig['brut'].get('mesures_instantanees')}",
    )

    # --- L'état du jour distingue les deux moments ------------------------
    state = client.get("/chat/thread", headers=h).json()["state"]
    check(
        "l'état du jour sait quel moment est fait",
        state["matin_done"] and state["soir_done"] and state["mesures_instantanees"] == 5,
        f"matin={state['matin_done']} · soir={state['soir_done']} · "
        f"mesures={state['mesures_instantanees']} · pic={state['pic_instantane']}",
    )

    print()
    if FAILURES:
        print(f"[ERR] {len(FAILURES)} vérification(s) en échec :")
        for name in FAILURES:
            print(f"       - {name}")
        raise SystemExit(1)
    print("[OK ] lot 1 : toutes les vérifications passent")
