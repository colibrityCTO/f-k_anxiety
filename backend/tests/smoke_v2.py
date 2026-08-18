"""Test de fumée de la V2 : exposition, méditation, échelles, streaming, rétroactif.

    cd backend && PYTHONPATH=. python tests/smoke_v2.py

Vérifie contre une vraie base : l'ajout d'un item à l'échelle d'expositions, la
tentative qui crée aussi l'entrée de journal alimentant le signal de violation
d'attente, la méditation, les trois échelles (dont la DMCI absente pour
l'évitement), la correction d'un jour antérieur et le refus d'une date future,
puis le streaming SSE du fil.
"""

from __future__ import annotations

import datetime as dt
import json

from fastapi.testclient import TestClient

from app import db
from app.main import app


def show(label, response, keys=None):
    ok = "OK " if response.status_code < 400 else "ERR"
    print(f"[{ok}] {response.status_code} {label}")
    if response.status_code >= 400:
        print("     ", response.text[:300])
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
    email = f"v2{dt.datetime.now().strftime('%H%M%S')}@exemple.fr"
    auth = client.post(
        "/auth/register", json={"email": email, "password": "motdepasse-tres-long-2026"}
    ).json()
    h = {"Authorization": f"Bearer {auth['access_token']}"}
    user_id = auth["user"]["id"]
    print(f"[OK ] compte créé : {email}")

    # --- Exposition : ajout d'un item --------------------------------------
    item = open_widget(client, h, "exposition")
    added = show(
        "POST submit exposition (ajout d'un item)",
        client.post(
            f"/chat/widget/{item['id']}/submit",
            headers=h,
            json={
                "values": {
                    "mode": "add",
                    "label": "Prendre le métro à l'heure de pointe",
                    "kind": "in_vivo",
                    "anticipated_anxiety": 5,
                    "safety_behaviors": ["rester près de la sortie"],
                }
            },
        ),
    )
    print("      relance :", (added["items"][1].get("content") or "")[:120])
    ladder = show("GET /exposures", client.get("/exposures", headers=h), ["label", "anticipated_anxiety"])
    expo_id = ladder[0]["id"]

    # --- Exposition : tentative -------------------------------------------
    item = open_widget(client, h, "exposition")
    attempt = show(
        "POST submit exposition (tentative)",
        client.post(
            f"/chat/widget/{item['id']}/submit",
            headers=h,
            json={
                "values": {
                    "mode": "attempt",
                    "item_id": expo_id,
                    "prediction": "Je vais faire une crise et devoir sortir",
                    "prediction_probability": 75,
                    "actual_outcome": "Anxiété à 7 pendant 4 minutes puis descente à 3, je suis resté",
                    "learning": "Les sensations montent puis redescendent seules",
                    "anxiety_max": 7,
                    "anxiety_after": 3,
                    "safety_behaviors_dropped": ["téléphone en main"],
                }
            },
        ),
    )
    print("      relance :", (attempt["items"][1].get("content") or "")[:200])
    journal = db.query_one(
        """
        SELECT kind, prediction_probability, learning FROM journal_entries
        WHERE user_id = %s AND kind = 'exposition' ORDER BY created_at DESC LIMIT 1
        """,
        (user_id,),
    )
    print(f"[{'OK ' if journal else 'ERR'}] entrée de journal créée pour alimenter les signaux :", journal)

    sig = client.get("/insights/signals?days=30", headers=h).json()
    expo_signal = next(s for s in sig["signaux"] if s["id"] == "expositions")
    print(f"[{'OK ' if expo_signal['value'] == 1 else 'ERR'}] signal expositions :",
          expo_signal["value"], "—", expo_signal["verdict"][:80])

    # --- Refus d'une tentative sans prédiction ni résultat -----------------
    item = open_widget(client, h, "exposition")
    bad = client.post(
        f"/chat/widget/{item['id']}/submit",
        headers=h,
        json={"values": {"mode": "attempt", "item_id": expo_id}},
    )
    print(f"[{'OK ' if bad.status_code == 422 else 'ERR'}] tentative sans prédiction refusée ({bad.status_code})")

    # --- Méditation --------------------------------------------------------
    item = open_widget(client, h, "meditation")
    med = show(
        "POST submit meditation",
        client.post(
            f"/chat/widget/{item['id']}/submit",
            headers=h,
            json={
                "values": {
                    "slug": "scan-corporel", "duration_min": 20,
                    "anxiety_before": 7, "anxiety_after": 4, "status": "fait",
                }
            },
        ),
    )
    print("      relance :", (med["items"][1].get("content") or "")[:160])

    # --- Échelles : les trois instruments ----------------------------------
    for instrument, answers in (
        ("gad7", [3, 3, 2, 2, 1, 2, 2]),
        ("phq2", [2, 2]),
        ("avoidance", [3, 2, 2, 1, 2]),
    ):
        item = open_widget(client, h, "echelles")
        result = client.post(
            f"/chat/widget/{item['id']}/submit",
            headers=h,
            json={"values": {"instrument": instrument, "items": answers}},
        )
        ok = "OK " if result.status_code < 400 else "ERR"
        print(f"[{ok}] {result.status_code} échelle {instrument}")
        if result.status_code < 400:
            print("     ", (result.json()["items"][1].get("content") or "")[:180])

    # Mauvais nombre de réponses
    item = open_widget(client, h, "echelles")
    bad = client.post(
        f"/chat/widget/{item['id']}/submit",
        headers=h,
        json={"values": {"instrument": "phq2", "items": [1, 2, 3]}},
    )
    print(f"[{'OK ' if bad.status_code == 422 else 'ERR'}] nombre de réponses invalide refusé ({bad.status_code})")

    # --- Correction d'un jour antérieur ------------------------------------
    yesterday = (dt.date.today() - dt.timedelta(days=3)).isoformat()
    item = open_widget(client, h, "checkin")
    back = show(
        "POST submit checkin (jour antérieur)",
        client.post(
            f"/chat/widget/{item['id']}/submit",
            headers=h,
            json={"values": {"entry_date": yesterday, "anxiety_0_10": 6, "sleep_hours": 6}},
        ),
    )
    stored = db.query_one(
        "SELECT entry_date, anxiety_0_10 FROM daily_checkins WHERE user_id = %s AND entry_date = %s",
        (user_id, yesterday),
    )
    print(f"[{'OK ' if stored else 'ERR'}] check-in rétroactif en base :", stored)

    item = open_widget(client, h, "checkin")
    future = client.post(
        f"/chat/widget/{item['id']}/submit",
        headers=h,
        json={"values": {"entry_date": (dt.date.today() + dt.timedelta(days=1)).isoformat(), "anxiety_0_10": 3}},
    )
    print(f"[{'OK ' if future.status_code == 422 else 'ERR'}] date future refusée ({future.status_code})")
    old = client.post(
        f"/chat/widget/{open_widget(client, h, 'checkin')['id']}/submit",
        headers=h,
        json={"values": {"entry_date": (dt.date.today() - dt.timedelta(days=90)).isoformat(), "anxiety_0_10": 3}},
    )
    print(f"[{'OK ' if old.status_code == 422 else 'ERR'}] date au-delà de 60 jours refusée ({old.status_code})")

    # --- Intentions du texte libre ----------------------------------------
    for text, expected in (
        ("j'ai osé prendre le métro", "exposition"),
        ("je veux méditer", "meditation"),
        ("qu'est-ce que j'avais noté il y a deux mois ?", "memoire"),
    ):
        body = client.post("/chat/message", headers=h, json={"text": text}).json()
        widget = next((i["widget_type"] for i in body["items"] if i["kind"] == "widget"), None)
        ok = "OK " if widget == expected else "ERR"
        print(f"[{ok}] « {text[:38]} » → widget {widget} (attendu {expected})")

    # --- Streaming SSE -----------------------------------------------------
    events: list[str] = []
    with client.stream(
        "POST", "/chat/message/stream", headers=h, json={"text": "comment je vais ?"}
    ) as response:
        print(f"[{'OK ' if response.status_code == 200 else 'ERR'}] {response.status_code} "
              f"POST /chat/message/stream · {response.headers.get('content-type')}")
        for line in response.iter_lines():
            if line.startswith("event:"):
                events.append(line.split(":", 1)[1].strip())
    print("      séquence d'événements :", events)
    expected_order = ["item", "engine", "token", "items", "done"]
    print(f"[{'OK ' if all(e in events for e in expected_order) else 'ERR'}] "
          f"tous les événements attendus présents")

    final = client.get("/chat/thread", headers=h).json()
    print(f"[OK ] fil final : {final['total']} items · mémoire {final['memoire']['total']} souvenirs")
    print(json.dumps({"memoire_par_source": final["memoire"]["par_source"]}, ensure_ascii=False, default=str))
