"""Test de fumée du lot 2 : QUICK CHILL et le log d'attaque.

    cd backend && PYTHONPATH=. python tests/smoke_v5_panique.py

Six garanties :

1. **Le contexte est récupérable avant la crise** — l'écran ne doit rien attendre au
   moment du pic.
2. **La porte du froid bloque réellement.** Elle n'est pas un avertissement
   décoratif : l'API refuse d'enregistrer un épisode qui déclare l'avoir utilisé.
3. **Un épisode déposé alimente le fil et la mémoire.**
4. **Le compteur de paniques du jour suit les épisodes**, et c'est lui que le
   check-in du soir affiche en lecture seule.
5. **L'agrégat est honnête** : « ce que tu redoutais est arrivé 0 fois » s'appuie sur
   les réponses de l'utilisateur, jamais sur une lecture du texte libre.
6. **Le garde-fou anti-comportement de sécurité** ne se déclenche qu'avec ses deux
   conditions : usage élevé **et** GAD-7 stable sous sa DMCI.
"""

from __future__ import annotations

import datetime as dt

from fastapi.testclient import TestClient

from app import db
from app.main import app

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    print(f"[{'OK ' if condition else 'ERR'}] {label}")
    if detail:
        print(f"      {detail}")
    if not condition:
        FAILURES.append(label)


with TestClient(app) as client:
    email = f"v5p{dt.datetime.now().strftime('%H%M%S')}@exemple.fr"
    auth = client.post(
        "/auth/register", json={"email": email, "password": "motdepasse-tres-long-2026"}
    ).json()
    h = {"Authorization": f"Bearer {auth['access_token']}"}
    user_id = auth["user"]["id"]
    today = dt.date.today()
    print(f"[OK ] compte créé : {email}")

    # --- 1. Le contexte, récupéré à froid ---------------------------------
    ctx = client.get("/chat/panique", headers=h).json()
    steps = [t["step"] for t in ctx["outils"]]
    check(
        "le contexte porte les outils, dans l'ordre de proposition",
        steps == ["respirer", "respirer", "ancrer", "froid", "jeu"],
        f"étapes : {steps}",
    )
    check(
        "le cadrage ne promet pas d'arrêter la crise",
        "ne va pas empêcher" in ctx["cadrage"],
        f"« {ctx['cadrage'][:80]}… »",
    )
    check("la porte du froid n'est pas encore validée", ctx["froid_valide_le"] is None)
    check(
        "le jeu porte sa réserve de preuve, explicitement",
        "n'est **pas** démontré" in (next(t for t in ctx["outils"] if t["step"] == "jeu")["caveat"]),
        "le transfert souvenirs intrusifs → panique n'est pas établi, et c'est dit",
    )
    check("aucun épisode au départ", ctx["bilan"]["episodes"] == 0 and ctx["bilan"]["phrase"] is None)

    # --- 2. La porte du froid bloque --------------------------------------
    blocked = client.post(
        "/chat/panique",
        headers=h,
        json={
            "body_symptoms": ["poitrine"],
            "tools_used": [{"slug": "froid", "seconds": 45}],
            "anxiety_after": 4,
            "time_to_relief_min": 9,
        },
    )
    check(
        "un épisode utilisant le froid est refusé sans la porte",
        blocked.status_code == 422,
        f"HTTP {blocked.status_code} — {blocked.json().get('detail', '')[:90]}",
    )
    check(
        "et rien n'a été enregistré",
        int(db.query_one("SELECT count(*) AS n FROM panic_episodes WHERE user_id = %s", (user_id,))["n"]) == 0,
    )

    # --- 3. Un épisode complet --------------------------------------------
    first = client.post(
        "/chat/panique",
        headers=h,
        json={
            "what_preceded": "métro bondé, trois cafés",
            "body_symptoms": ["poitrine", "gorge"],
            "thought_in_moment": "Je vais mourir",
            "tools_used": [
                {"slug": "expiration-longue", "seconds": 180},
                {"slug": "froid", "seconds": 45},
            ],
            "anxiety_peak": 10,
            "anxiety_after": 3,
            "time_to_relief_min": 11,
            "what_actually_happened": "rien, je suis descendu à la station suivante",
            "feared_outcome_happened": False,
            "confirm_cold_contraindications": True,
        },
    )
    check("l'épisode passe une fois la porte confirmée", first.status_code == 200,
          f"HTTP {first.status_code}")
    body = first.json()
    recap = next((i for i in body["items"] if i.get("widget_type") == "panique"), None)
    check(
        "un récapitulatif est déposé dans le fil, déjà figé",
        recap is not None and recap["status"] == "valide",
        f"status={recap['status'] if recap else '—'} · "
        f"outils={(recap or {}).get('saved_values', {}).get('outils')}",
    )
    memory_row = db.query_one(
        "SELECT content FROM user_chunks WHERE user_id = %s AND source_kind = 'panique'",
        (user_id,),
    )
    check(
        "l'épisode entre en mémoire vectorisée, avec ce qui s'est réellement passé",
        memory_row is not None and "réellement passé" in memory_row["content"],
        f"« {(memory_row or {}).get('content', '—')[:120]}… »",
    )

    # --- 4. Le compteur du jour -------------------------------------------
    counter = db.query_one(
        "SELECT panic_attacks FROM daily_checkins WHERE user_id = %s AND entry_date = %s AND moment = 'soir'",
        (user_id, today),
    )
    check(
        "le compteur de paniques du jour est incrémenté",
        counter is not None and counter["panic_attacks"] == 1,
        f"panic_attacks={(counter or {}).get('panic_attacks')}",
    )
    soir = client.post("/chat/widget", headers=h, json={"type": "soir"}).json()
    prefill = next(i for i in soir["items"] if i.get("widget_type") == "soir")["payload"]["prefill"]
    check(
        "le check-in du soir l'affiche en lecture seule",
        prefill.get("panic_attacks") == 1 and "panic_attacks" in (prefill.get("_derive") or []),
        f"panic_attacks={prefill.get('panic_attacks')} · _derive={prefill.get('_derive')}",
    )

    # --- 5. L'agrégat, honnête -------------------------------------------
    for minutes, feared in ((7, False), (20, False), (4, False)):
        client.post(
            "/chat/panique",
            headers=h,
            json={
                "body_symptoms": ["ventre"],
                "tools_used": [{"slug": "ancrage", "seconds": 60}],
                "anxiety_peak": 9,
                "anxiety_after": 4,
                "time_to_relief_min": minutes,
                "feared_outcome_happened": feared,
            },
        )
    bilan = client.get("/chat/panique", headers=h).json()["bilan"]
    check(
        "durée médiane et non moyenne : un épisode long ne déforme pas le chiffre",
        bilan["duree_mediane_min"] == 9,
        f"durées 4, 7, 11, 20 → médiane {bilan['duree_mediane_min']} "
        f"(la moyenne serait 10.5) · max {bilan['duree_max_min']}",
    )
    check(
        "« ce que tu redoutais est arrivé 0 fois » s'appuie sur les réponses données",
        bilan["redoute_renseigne"] == 4 and bilan["redoute_arrive"] == 0,
        f"{bilan['redoute_arrive']} sur {bilan['redoute_renseigne']} réponses",
    )
    check(
        "la phrase du bilan est composée côté serveur",
        bilan["phrase"] is not None and "0 fois" in bilan["phrase"],
        f"« {bilan['phrase']} »",
    )
    check(
        "les outils utilisés sont comptés",
        dict(bilan["outils"]).get("ancrage") == 3,
        f"{bilan['outils']}",
    )

    # --- 6. Le garde-fou : deux conditions, pas une ----------------------
    check(
        "pas d'alerte à 4 usages : en dessous du seuil",
        client.get("/chat/panique", headers=h).json()["alerte_usage"] is None,
        f"usage_7j=4, seuil={ctx['seuil_usage']}",
    )
    for _ in range(8):
        client.post(
            "/chat/panique", headers=h,
            json={"body_symptoms": [], "tools_used": [], "time_to_relief_min": 5},
        )
    after_many = client.get("/chat/panique", headers=h).json()
    check(
        "toujours pas d'alerte sans GAD-7 : un usage élevé seul serait un reproche",
        after_many["alerte_usage"] is None and after_many["usage_7j"] >= 12,
        f"usage_7j={after_many['usage_7j']}, aucune mesure GAD-7 disponible",
    )
    for offset, total in ((14, 12), (7, 13)):
        db.execute(
            """
            INSERT INTO assessments (user_id, instrument, taken_on, items, total, severity)
            VALUES (%s, 'gad7', %s, '{2,2,2,2,2,1,1}', %s, 'modérée')
            ON CONFLICT (user_id, instrument, taken_on) DO NOTHING
            """,
            (user_id, today - dt.timedelta(days=offset), total),
        )
    alerted = client.get("/chat/panique", headers=h).json()
    check(
        "alerte quand les deux conditions sont réunies : usage élevé ET GAD-7 stable",
        alerted["alerte_usage"] is not None,
        f"« {(alerted['alerte_usage'] or '—')[:130]}… »",
    )

    print()
    if FAILURES:
        print(f"[ERR] {len(FAILURES)} vérification(s) en échec :")
        for name in FAILURES:
            print(f"       - {name}")
        raise SystemExit(1)
    print("[OK ] lot 2 : toutes les vérifications passent")
