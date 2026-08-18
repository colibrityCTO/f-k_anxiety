"""Test de fumée de la V3 : intéroceptif, entretien, bilan hebdo, rapport.

    cd backend && PYTHONPATH=. python tests/smoke_v3.py

Vérifie contre une vraie base : la porte de contre-indications qui bloque
réellement, l'exposition intéroceptive qui alimente les signaux, le passage
automatique en régime d'entretien au critère de sortie (et le retour en actif à
la rechute), la proposition de bilan hebdomadaire déposée dans le fil au plus une
fois par semaine, et le contenu du rapport imprimable.
"""

from __future__ import annotations

import datetime as dt

from fastapi.testclient import TestClient

from app import db, program
from app.main import app


def show(label, response, keys=None):
    ok = "OK " if response.status_code < 400 else "ERR"
    print(f"[{ok}] {response.status_code} {label}")
    if response.status_code >= 400:
        print("     ", response.text[:260])
        return None
    body = response.json()
    if keys:
        target = body[0] if isinstance(body, list) and body else body
        print("     ", {k: target.get(k) for k in keys})
    return body


def open_widget(client, headers, kind):
    items = client.post("/chat/widget", headers=headers, json={"type": kind}).json()["items"]
    return next(i for i in items if i.get("widget_type") == kind)


with TestClient(app) as client:
    email = f"v3{dt.datetime.now().strftime('%H%M%S')}@exemple.fr"
    auth = client.post(
        "/auth/register", json={"email": email, "password": "motdepasse-tres-long-2026"}
    ).json()
    h = {"Authorization": f"Bearer {auth['access_token']}"}
    user_id = auth["user"]["id"]
    today = dt.date.today()
    print(f"[OK ] compte créé : {email}")

    # --- Exposition intéroceptive : la porte bloque -------------------------
    catalogue = show(
        "GET /chat/interoceptif",
        client.get("/chat/interoceptif", headers=h),
        ["valide_le"],
    )
    print(f"      {len(catalogue['exercices'])} exercices · "
          f"{len(catalogue['contre_indications'])} contre-indications")

    item = open_widget(client, h, "interoceptif")
    blocked = client.post(
        f"/chat/widget/{item['id']}/submit",
        headers=h,
        json={"values": {"slug": "hyperventilation", "prediction": "je vais m'évanouir"}},
    )
    print(f"[{'OK ' if blocked.status_code == 422 else 'ERR'}] "
          f"bloqué sans validation des contre-indications ({blocked.status_code})")
    print("     ", blocked.json().get("detail", "")[:110])

    # --- Puis passe, une fois validée --------------------------------------
    done = show(
        "POST submit interoceptif (contre-indications validées)",
        client.post(
            f"/chat/widget/{item['id']}/submit",
            headers=h,
            json={
                "values": {
                    "confirm_contraindications": True,
                    "slug": "hyperventilation",
                    "prediction": "Je vais m'évanouir",
                    "prediction_probability": 70,
                    "actual_outcome": "Vertige et picotements pendant 90 s, aucun évanouissement",
                    "learning": "Le vertige passe seul, je ne tombe pas",
                    "anxiety_max": 8,
                    "anxiety_after": 3,
                }
            },
        ),
    )
    print("      relance :", (done["items"][1].get("content") or "")[:190])

    profile = db.query_one("SELECT profile FROM users WHERE id = %s", (user_id,))
    print(f"[{'OK ' if profile['profile'].get('interoceptif_valide_le') else 'ERR'}] "
          f"validation datée dans le profil : {profile['profile'].get('interoceptif_valide_le')}")

    catalogue = client.get("/chat/interoceptif", headers=h).json()
    count = catalogue["compte_par_exercice"].get("Exposition intéroceptive — Hyperventilation volontaire")
    print(f"[{'OK ' if count == 1 else 'ERR'}] répétitions comptées : {count}")

    sig = client.get("/insights/signals?days=30", headers=h).json()
    expo = next(s for s in sig["signaux"] if s["id"] == "expositions")
    print(f"[{'OK ' if expo['value'] == 1 else 'ERR'}] signal expositions alimenté : {expo['value']}")

    # --- Régime d'entretien : critère de sortie ----------------------------
    state = program.remission_state(user_id)
    print(f"[OK ] critère au départ : rémission={state['remission']} "
          f"(gad7_ok={state['gad7_ok']}, expositions_ok={state['expositions_ok']})")

    for weeks_ago in (3, 2, 1, 0):
        db.execute(
            """
            INSERT INTO assessments (user_id, instrument, taken_on, items, total, severity)
            VALUES (%s, 'gad7', %s, %s, %s, 'minimale')
            ON CONFLICT (user_id, instrument, taken_on) DO UPDATE SET total = EXCLUDED.total
            """,
            (user_id, today - dt.timedelta(days=7 * weeks_ago), [1, 1, 0, 0, 1, 0, 0], 3),
        )
    state = program.remission_state(user_id)
    print(f"[{'OK ' if state['gad7_ok'] and state['remission'] else 'ERR'}] "
          f"4 GAD-7 ≤ 5 → rémission={state['remission']}")

    thread = client.get("/chat/thread", headers=h).json()
    print(f"[{'OK ' if thread['state']['status'] == 'entretien' else 'ERR'}] "
          f"statut du programme : {thread['state']['status']}")
    print(f"      exposition due : {thread['state']['exposition_due']} · "
          f"GAD-7 due : {thread['state']['gad7_due']} (mensuel en entretien)")

    # Une exposition non maîtrisée doit faire retomber le critère.
    db.execute(
        """
        INSERT INTO exposure_items (user_id, label, kind, anticipated_anxiety)
        VALUES (%s, 'Prendre la parole en réunion', 'in_vivo', 6)
        """,
        (user_id,),
    )
    state = program.remission_state(user_id)
    print(f"[{'OK ' if not state['remission'] else 'ERR'}] "
          f"un item non maîtrisé fait retomber le critère : rémission={state['remission']} "
          f"({state['expositions_restantes']} restant)")

    # Rechute : GAD-7 à 5 + 4 points ramène en actif.
    db.execute(
        """
        INSERT INTO assessments (user_id, instrument, taken_on, items, total, severity)
        VALUES (%s, 'gad7', %s, %s, %s, 'modérée')
        ON CONFLICT (user_id, instrument, taken_on) DO UPDATE SET total = EXCLUDED.total
        """,
        (user_id, today, [2, 2, 2, 2, 2, 1, 1], 12),
    )
    state = program.remission_state(user_id)
    print(f"[{'OK ' if state['rechute_probable'] else 'ERR'}] "
          f"rechute probable détectée (≥ 5 + DMCI) : {state['rechute_probable']}")
    refreshed = program.recompute_week(user_id, today)
    print(f"[{'OK ' if refreshed['status'] == 'actif' else 'ERR'}] "
          f"retour en programme actif : {refreshed['status']}")

    # --- Bilan hebdomadaire automatique ------------------------------------
    for offset in range(12, 0, -1):
        day = today - dt.timedelta(days=offset)
        client.post(
            "/checkins",
            headers=h,
            json={"entry_date": str(day), "moment": "soir", "anxiety_0_10": 5, "mood_0_10": 5},
        )
    db.execute("DELETE FROM thread_items WHERE user_id = %s AND created_at::date = %s", (user_id, today))
    thread = client.get("/chat/thread", headers=h).json()
    weekly = [
        i for i in thread["items"]
        if i.get("widget_type") == "analysis" and i["payload"].get("prefill", {}).get("scope") == "hebdomadaire"
    ]
    print(f"[{'OK ' if weekly else 'ERR'}] bilan hebdomadaire déposé dans le fil : {len(weekly)}")

    # Pour isoler le garde-fou des 7 jours, on ne supprime que les messages du
    # jour : l'ouverture proactive se rejoue, mais la proposition de bilan doit
    # rester unique puisque sa trace (le widget) est toujours là.
    db.execute(
        "DELETE FROM thread_items WHERE user_id = %s AND created_at::date = %s AND kind = 'text'",
        (user_id, today),
    )
    thread = client.get("/chat/thread", headers=h).json()
    weekly_again = [
        i for i in thread["items"]
        if i.get("widget_type") == "analysis" and i["payload"].get("prefill", {}).get("scope") == "hebdomadaire"
    ]
    print(f"[{'OK ' if len(weekly_again) == 1 else 'ERR'}] pas de doublon dans les 7 jours "
          f"({len(weekly_again)} proposition, ouverture rejouée)")

    # --- Rapport imprimable ------------------------------------------------
    report = show("GET /chat/rapport", client.get("/chat/rapport?days=90", headers=h), ["genere_le"])
    print("      sections :", {
        "signaux": len(report["signaux"]),
        "quotidien": len(report["quotidien"]),
        "echelles": len(report["echelles"]),
        "expositions": len(report["expositions"]),
        "apprentissages": len(report["apprentissages"]),
        "activites": len(report["activites"]),
    })
    print(f"[{'OK ' if report['cadre'] and 'diagnostic' in report['cadre'] else 'ERR'}] "
          "le cadre et les limites figurent en tête du rapport")
    learnings = [row["learning"] for row in report["apprentissages"] if row["learning"]]
    print(f"[{'OK ' if learnings else 'ERR'}] apprentissages repris :", learnings[:2])

    # --- Intentions V3 ------------------------------------------------------
    for text, expected in (
        ("j'ai peur de mes sensations physiques", "interoceptif"),
        ("je veux un rapport pour mon psy", "rapport"),
    ):
        body = client.post("/chat/message", headers=h, json={"text": text}).json()
        widget = next((i["widget_type"] for i in body["items"] if i["kind"] == "widget"), None)
        print(f"[{'OK ' if widget == expected else 'ERR'}] « {text[:34]} » → {widget}")

    final = client.get("/chat/thread", headers=h).json()
    print(f"[OK ] fil final : {final['total']} items · statut {final['state']['status']} · "
          f"mémoire {final['memoire']['total']} souvenirs")
