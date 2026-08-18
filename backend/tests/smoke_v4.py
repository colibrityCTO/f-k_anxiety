"""Test de fumée de la V4 : push, planificateur, export, suppression, correction.

    cd backend && PYTHONPATH=. python tests/smoke_v4.py

Ce qui est vérifié contre une vraie base :

- l'abonnement push est idempotent sur l'endpoint ;
- le planificateur ne retient un compte qu'à **son** heure locale, et seulement si
  le check-in manque ;
- le journal des notifications rend l'envoi idempotent (deuxième tic : rien) ;
- une entrée de journal corrigée garde sa date d'origine ;
- l'export contient bien toutes les sections ;
- la suppression exige l'adresse exacte, puis n'épargne rien.

L'envoi réel vers un service de push n'est pas testé : il n'y a pas de navigateur.
L'endpoint fictif fait échouer `webpush`, ce qui désactive l'abonnement — c'est
exactement le comportement attendu pour un abonnement mort, et le test le vérifie.
"""

from __future__ import annotations

import datetime as dt
import json

from fastapi.testclient import TestClient

from app import db, push, scheduler
from app.main import app


def show(label, response, keys=None):
    ok = "OK " if response.status_code < 400 else "ERR"
    print(f"[{ok}] {response.status_code} {label}")
    if response.status_code >= 400:
        print("     ", response.text[:240])
        return None
    body = response.json()
    if keys:
        print("     ", {k: body.get(k) for k in keys})
    return body


with TestClient(app) as client:
    email = f"v4{dt.datetime.now().strftime('%H%M%S')}@exemple.fr"
    auth = client.post(
        "/auth/register", json={"email": email, "password": "motdepasse-tres-long-2026"}
    ).json()
    h = {"Authorization": f"Bearer {auth['access_token']}"}
    user_id = auth["user"]["id"]
    today = dt.date.today()
    print(f"[OK ] compte créé : {email}")

    # --- Clé publique et état ----------------------------------------------
    key = show("GET /push/key", client.get("/push/key", headers=h), ["disponible"])
    print(f"[{'OK ' if key['disponible'] == push.available() else 'ERR'}] "
          f"état du push cohérent avec la configuration : {key['disponible']}")

    # --- Abonnement --------------------------------------------------------
    subscription = {
        "endpoint": "https://push.example.invalid/abcdef123456",
        "p256dh": "BEl62iUYgUivxIkv69yViEuiBIa-Ib9-SkFZwd8SgnV6vJm8h1nUj0LqBTHqPXjK6mZ9Q1kM",
        "auth": "k8JV6sjdzhbRoTBK9dGvVA",
        "user_agent": "test-suite",
    }
    if key["disponible"]:
        show("POST /push/subscribe", client.post("/push/subscribe", headers=h, json=subscription))
        client.post("/push/subscribe", headers=h, json=subscription)  # ré-abonnement
        rows = db.query_all("SELECT endpoint FROM push_subscriptions WHERE user_id = %s", (user_id,))
        print(f"[{'OK ' if len(rows) == 1 else 'ERR'}] abonnement idempotent : {len(rows)} ligne(s)")
    else:
        refused = client.post("/push/subscribe", headers=h, json=subscription)
        print(f"[{'OK ' if refused.status_code == 503 else 'ERR'}] "
              f"abonnement refusé sans clé VAPID ({refused.status_code})")

    # --- Réglage du rappel -------------------------------------------------
    show("POST /push/reminder (10:30)",
         client.post("/push/reminder", headers=h, json={"enabled": True, "time": "10:30"}), ["rappel"])
    bad = client.post("/push/reminder", headers=h, json={"enabled": True, "time": "25:00"})
    print(f"[{'OK ' if bad.status_code == 422 else 'ERR'}] heure invalide refusée ({bad.status_code})")

    # --- Planificateur : à la mauvaise heure, rien ne part ------------------
    db.execute("UPDATE users SET timezone = 'Europe/Paris' WHERE id = %s", (user_id,))
    paris = __import__("zoneinfo").ZoneInfo("Europe/Paris")

    def utc_for(hour: int, minute: int) -> dt.datetime:
        local = dt.datetime.combine(today, dt.time(hour, minute), tzinfo=paris)
        return local.astimezone(dt.timezone.utc)

    off_hour = scheduler.tick(utc_for(3, 0))
    print(f"[{'OK ' if off_hour['rappels'] == 0 else 'ERR'}] hors de l'heure choisie : "
          f"{off_hour['rappels']} rappel (candidats vus : {off_hour['candidats']})")

    on_hour = scheduler.tick(utc_for(10, 31))
    sent = db.query_all(
        "SELECT kind, sent_on FROM notification_log WHERE user_id = %s", (user_id,)
    )
    print(f"[{'OK ' if on_hour['rappels'] == (1 if key['disponible'] else 0) else 'ERR'}] "
          f"à 10:31 heure de Paris : {on_hour['rappels']} rappel · journal : {sent}")

    again = scheduler.tick(utc_for(10, 32))
    print(f"[{'OK ' if again['rappels'] == 0 else 'ERR'}] deuxième tic le même jour : "
          f"{again['rappels']} rappel (journal des notifications idempotent)")

    if key["disponible"]:
        state = db.query_one(
            "SELECT active, last_error FROM push_subscriptions WHERE user_id = %s", (user_id,)
        )
        print(f"[{'OK ' if state and not state['active'] else 'ERR'}] "
              f"abonnement fictif désactivé après échec : {state}")

    # --- Le rappel ne part pas si le check-in est déjà fait -----------------
    db.execute("DELETE FROM notification_log WHERE user_id = %s", (user_id,))
    client.post("/checkins", headers=h, json={"moment": "soir", "anxiety_0_10": 4})
    with_checkin = scheduler.tick(utc_for(10, 31))
    print(f"[{'OK ' if with_checkin['rappels'] == 0 else 'ERR'}] check-in déjà fait : "
          f"{with_checkin['rappels']} rappel — on ne notifie pas pour rien")

    # --- Correction d'une entrée de journal passée -------------------------
    old_day = today - dt.timedelta(days=5)
    created = db.execute_returning(
        """
        INSERT INTO journal_entries (user_id, entry_date, kind, free_text)
        VALUES (%s, %s, 'libre', %s) RETURNING id::text, entry_date
        """,
        (user_id, old_day, "version initiale"),
    )
    opened = client.post("/chat/widget", headers=h, json={"type": "journal"}).json()["items"]
    widget = next(i for i in opened if i.get("widget_type") == "journal")
    corrected = show(
        "POST submit journal (correction)",
        client.post(
            f"/chat/widget/{widget['id']}/submit",
            headers=h,
            json={"values": {"kind": "libre", "free_text": "version corrigée", "edit_id": created["id"]}},
        ),
    )
    row = db.query_one(
        "SELECT entry_date, free_text FROM journal_entries WHERE id = %s", (created["id"],)
    )
    print(f"[{'OK ' if row['free_text'] == 'version corrigée' else 'ERR'}] texte mis à jour")
    print(f"[{'OK ' if row['entry_date'] == old_day else 'ERR'}] "
          f"date d'origine conservée : {row['entry_date']} (et non {today})")
    count = db.query_one(
        "SELECT count(*) AS n FROM journal_entries WHERE user_id = %s", (user_id,)
    )
    print(f"[{'OK ' if int(count['n']) == 1 else 'ERR'}] pas de doublon créé : {count['n']} entrée")
    print("      relance :", (corrected["items"][1].get("content") or "")[:140])

    # --- Export -------------------------------------------------------------
    export = show("GET /auth/export", client.get("/auth/export", headers=h), ["exporte_le"])
    sections = {
        k: len(v) for k, v in export.items() if isinstance(v, list)
    }
    print("      sections :", sections)
    expected = {"check_ins", "journal", "fil", "memoire", "appareils", "notifications_envoyees"}
    print(f"[{'OK ' if expected <= set(export) else 'ERR'}] toutes les sections attendues présentes")
    print(f"[{'OK ' if 'password' not in json.dumps(export) else 'ERR'}] "
          "aucun mot de passe dans l'export")

    # --- Suppression --------------------------------------------------------
    wrong = client.post("/auth/delete", headers=h, json={"email": "autre@exemple.fr"})
    print(f"[{'OK ' if wrong.status_code == 422 else 'ERR'}] "
          f"suppression refusée avec la mauvaise adresse ({wrong.status_code})")

    removed = show("POST /auth/delete", client.post("/auth/delete", headers=h, json={"email": email}))
    print("      lignes effacées :", removed["lignes_effacees"])
    left = db.query_one("SELECT count(*) AS n FROM users WHERE id = %s", (user_id,))
    orphans = {
        table: int(
            db.query_one(f"SELECT count(*) AS n FROM {table} WHERE user_id = %s", (user_id,))["n"]  # noqa: S608
        )
        for table in ("daily_checkins", "journal_entries", "thread_items", "user_chunks", "push_subscriptions")
    }
    print(f"[{'OK ' if int(left['n']) == 0 else 'ERR'}] compte supprimé")
    print(f"[{'OK ' if all(v == 0 for v in orphans.values()) else 'ERR'}] "
          f"aucune donnée orpheline : {orphans}")

    expired = client.get("/chat/thread", headers=h)
    print(f"[{'OK ' if expired.status_code == 401 else 'ERR'}] "
          f"le jeton ne vaut plus rien après suppression ({expired.status_code})")
