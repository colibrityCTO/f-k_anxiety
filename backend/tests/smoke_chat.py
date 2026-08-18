"""Test de fumée du fil : la boucle complète de la V1.

    cd backend && PYTHONPATH=. python tests/smoke_chat.py

Vérifie, contre une vraie base : l'ouverture proactive du jour, le texte libre
transformé en widget pré-rempli (sans écriture en base avant validation), la
validation qui enregistre et fige, la relance bâtie sur les signaux, le GAD-7 et
sa DMCI, la mémoire personnelle vectorisée, et la détection de drapeau rouge.
"""

from __future__ import annotations

import datetime as dt
import json

from fastapi.testclient import TestClient

from app import db
from app.main import app

def _skip_onboarding(user_id: str) -> None:
    """Marque le questionnaire initial comme rempli.

    Ces tests portent sur l'ouverture proactive et la capture de texte libre, pas sur
    le questionnaire — qui a sa propre suite (`smoke_v5_onboarding.py`). Sans ce
    court-circuit, la première ouverture du fil dépose le questionnaire **à la place**
    de l'ouverture du jour, ce qui est le comportement voulu mais rend ces tests
    inopérants.
    """
    db.execute(
        """
        UPDATE users
        SET profile = profile || jsonb_build_object(
            'onboarding', jsonb_build_object('version', 1, 'done_at', CURRENT_DATE::text)
        )
        WHERE id = %s
        """,
        (user_id,),
    )



def show(label: str, response, keys: list[str] | None = None):
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


def items_summary(items):
    out = []
    for item in items:
        if item["kind"] == "widget":
            out.append(f"widget:{item['widget_type']}({item.get('status')})")
        else:
            out.append(f"{item['role']}:{(item.get('content') or '')[:70]}")
    return out


with TestClient(app) as client:
    email = f"fil{dt.datetime.now().strftime('%H%M%S')}@exemple.fr"
    auth = client.post(
        "/auth/register", json={"email": email, "password": "motdepasse-tres-long-2026", "display_name": "Cam"}
    ).json()
    token = auth["access_token"]
    user_id = auth["user"]["id"]
    _skip_onboarding(user_id)
    h = {"Authorization": f"Bearer {token}"}
    print(f"[OK ] compte créé : {email}")

    # --- Ouverture proactive du jour ---------------------------------------
    thread = show("GET /chat/thread (ouverture proactive)", client.get("/chat/thread", headers=h))
    print("      fil :", items_summary(thread["items"]))
    print("      état :", {k: thread["state"][k] for k in ("checkin_done", "week", "streak", "gad7_due")})
    # V5 : l'ouverture propose désormais le moment dû (matin avant 17 h, soir après),
    # et non plus le formulaire unique. `checkin` reste accepté par l'API.
    checkin_item = next(
        i for i in thread["items"] if i.get("widget_type") in {"matin", "soir", "checkin"}
    )

    # Deuxième appel : l'ouverture ne doit pas être dupliquée.
    again = client.get("/chat/thread", headers=h).json()
    print(f"[{'OK ' if len(again['items']) == len(thread['items']) else 'ERR'}] ouverture non dupliquée "
          f"({len(thread['items'])} → {len(again['items'])} items)")

    # --- Texte libre → widget pré-rempli ----------------------------------
    msg = show(
        "POST /chat/message (texte libre)",
        client.post(
            "/chat/message",
            headers=h,
            json={"text": "nuit pourrie, anxiété 8, j'ai eu une crise dans le métro et j'ai annulé mon dîner"},
        ),
    )
    print("      fil :", items_summary(msg["items"]))
    # « nuit pourrie, anxiété 8… » porte l'anxiété **et** la nuit : ça part donc
    # vers le soir. Seule une phrase qui ne parle que de sommeil viserait le matin.
    proposed = next(
        (i for i in msg["items"] if i.get("widget_type") in {"soir", "matin", "checkin"}), None
    )
    if proposed:
        print("      pré-remplissage :", proposed["payload"].get("prefill"))
        print("      à vérifier :", proposed["payload"].get("a_verifier"))

    # Rien ne doit être écrit avant validation.
    before = db.query_one(
        "SELECT count(*) AS n FROM daily_checkins WHERE user_id = %s", (user_id,)
    )
    print(f"[{'OK ' if before['n'] == 0 else 'ERR'}] aucun check-in en base avant validation (n={before['n']})")

    # --- Validation du widget ---------------------------------------------
    submitted = show(
        "POST /chat/widget/{id}/submit (check-in)",
        client.post(
            f"/chat/widget/{proposed['id']}/submit",
            headers=h,
            json={"values": {**(proposed["payload"].get("prefill") or {}), "mood_0_10": 3, "avoidance_0_10": 7}},
        ),
    )
    print("      fil :", items_summary(submitted["items"]))
    frozen = submitted["items"][0]
    print(f"[{'OK ' if frozen['status'] == 'valide' else 'ERR'}] widget figé : status={frozen['status']}, "
          f"valeurs={ {k: v for k, v in frozen['saved_values'].items() if k in ('anxiety_0_10','sleep_hours','panic_attacks')} }")

    after = db.query_one(
        "SELECT anxiety_0_10, sleep_hours, panic_attacks FROM daily_checkins WHERE user_id = %s", (user_id,)
    )
    print("      en base :", after)

    # Revalider doit être refusé.
    replay = client.post(
        f"/chat/widget/{proposed['id']}/submit", headers=h, json={"values": {"anxiety_0_10": 1}}
    )
    print(f"[{'OK ' if replay.status_code == 409 else 'ERR'}] revalidation refusée ({replay.status_code})")

    # --- Widget lancé depuis la grille ------------------------------------
    opened = show(
        "POST /chat/widget (lancé depuis la grille)",
        client.post("/chat/widget", headers=h, json={"type": "gad7", "label": "GAD-7"}),
    )
    print("      fil :", items_summary(opened["items"]))
    gad_item = next(i for i in opened["items"] if i.get("widget_type") == "gad7")
    gad = show(
        "POST /chat/widget/{id}/submit (GAD-7)",
        client.post(
            f"/chat/widget/{gad_item['id']}/submit",
            headers=h,
            json={"values": {"items": [3, 3, 2, 2, 1, 2, 2]}},
        ),
    )
    print("      relance :", items_summary(gad["items"])[1:])

    # --- Respiration -------------------------------------------------------
    breath_item = next(
        i for i in client.post("/chat/widget", headers=h, json={"type": "breath"}).json()["items"]
        if i.get("widget_type") == "breath"
    )
    breath = show(
        "POST /chat/widget/{id}/submit (respiration)",
        client.post(
            f"/chat/widget/{breath_item['id']}/submit",
            headers=h,
            json={"values": {"anxiety_before": 8, "anxiety_after": 5, "duration_min": 5, "status": "fait"}},
        ),
    )
    print("      relance :", items_summary(breath["items"])[1:])

    # --- « Pas maintenant » ------------------------------------------------
    journal_item = next(
        i for i in client.post("/chat/widget", headers=h, json={"type": "journal"}).json()["items"]
        if i.get("widget_type") == "journal"
    )
    skipped = show("POST /chat/widget/{id}/skip", client.post(f"/chat/widget/{journal_item['id']}/skip", headers=h))
    print("      fil :", items_summary(skipped["items"]))

    # --- Mémoire personnelle ----------------------------------------------
    mem = show("GET /chat/memory", client.get("/chat/memory", headers=h))
    print("      stats :", mem["stats"]["total"], "souvenirs ·", mem["stats"]["vectorises"], "vectorisés")
    print("      par source :", [(r["source_kind"], r["n"]) for r in mem["stats"]["par_source"]])
    found = show(
        "GET /chat/memory?q=…",
        client.get("/chat/memory?q=crise%20dans%20le%20metro%20nuit%20courte", headers=h),
    )
    for row in (found.get("resultats") or [])[:3]:
        print(f"      · [{row['source_kind']} {row['entry_date']}] {row['content'][:110]}")

    # --- Drapeau rouge -----------------------------------------------------
    risky = show(
        "POST /chat/message (drapeau rouge)",
        client.post("/chat/message", headers=h, json={"text": "j'en peux plus, j'ai envie de mourir"}),
    )
    print(f"[{'OK ' if risky['risk'] else 'ERR'}] risque détecté :", risky["risk"])
    print("      réponse :", (risky["items"][1].get("content") or "")[:160].replace("\n", " "))
    print(f"[{'OK ' if not any(i['kind'] == 'widget' for i in risky['items']) else 'ERR'}] aucun widget proposé en situation de risque")

    # --- Fil complet -------------------------------------------------------
    final = client.get("/chat/thread", headers=h).json()
    print(f"[OK ] fil final : {final['total']} items, mémoire {final['memoire']['total']} souvenirs")
    print(json.dumps({"état": final["state"]}, ensure_ascii=False, indent=2, default=str))
