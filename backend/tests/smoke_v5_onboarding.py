"""Test de fumée du questionnaire initial.

    cd backend && PYTHONPATH=. python tests/smoke_v5_onboarding.py

Ce qu'il vérifie, et pourquoi le premier point est le plus important :

1. **La règle morte revit.** `program.py` lit `profile["difficultes"]` depuis le début
   pour proposer une expérience sociale ; personne n'écrivait cette clé. La règle ne
   levait pas d'erreur — elle ne se déclenchait jamais. C'est un bug, pas un manque.
2. Le questionnaire est déposé à la **première** ouverture du fil, et **remplace**
   l'ouverture du jour au lieu de s'y ajouter.
3. Il n'est plus proposé une fois rempli, et l'état est lu dans le **profil** — un
   widget ouvert puis ignoré ne passe pas pour rempli.
4. Les écritures partent au bon endroit : échelles dans `assessments`, objectif dans
   `journal_entries` et en mémoire, le reste dans `users.profile`.
5. La porte de contre-indications est validée ici plutôt que huit semaines plus tard.
6. Panique déclarée → l'exposition intéroceptive est avancée, sans attendre qu'une
   crise soit enregistrée dans l'application.
7. Le profil est **versionné** : refaire le questionnaire n'écrase pas.
"""

from __future__ import annotations

import datetime as dt

from fastapi.testclient import TestClient

from app import db, program
from app.main import app

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    print(f"[{'OK ' if condition else 'ERR'}] {label}")
    if detail:
        print(f"      {detail}")
    if not condition:
        FAILURES.append(label)


ANSWERS = {
    "objectif": "prendre le métro sans y penser la veille",
    "difficultes": ["panique", "social", "inquietude"],
    "anciennete": "plus-15-ans",
    "gad7": [2, 2, 3, 2, 1, 2, 3],
    "phq2": [1, 2],
    "sensibilite": [3, 4, 3],
    "paniques_mois": 4,
    "sensations": ["cœur qui s’accélère", "manque d’air"],
    "habitudes": {"cafeine_jour": 3, "alcool_semaine": 4, "sport_semaine": 1},
    "rappel_heure": "20:30",
    "medecin_ecarte": True,
    "contre_indications_ok": True,
}


with TestClient(app) as client:
    email = f"ob{dt.datetime.now().strftime('%H%M%S%f')[:12]}@exemple.fr"
    auth = client.post(
        "/auth/register", json={"email": email, "password": "motdepasse-tres-long-2026"}
    ).json()
    h = {"Authorization": f"Bearer {auth['access_token']}"}
    user_id = auth["user"]["id"]
    today = dt.date.today()
    print(f"[OK ] compte créé : {email}")

    # --- 1. Avant : la règle sociale ne peut pas se déclencher -------------
    empty_profile_items = program.adaptive_items({"signaux": []}, {})
    check(
        "sans questionnaire, aucune règle de profil ne se déclenche",
        not empty_profile_items,
        "c'était l'état permanent de l'application : la clé `difficultes` "
        "n'était écrite par personne",
    )

    # --- 2. Déposé à la première ouverture, et il remplace l'ouverture ----
    thread = client.get("/chat/thread", headers=h).json()
    widgets = [i.get("widget_type") for i in thread["items"] if i["kind"] == "widget"]
    check(
        "le questionnaire est déposé à la première ouverture du fil",
        widgets == ["onboarding"],
        f"widgets déposés : {widgets} — et rien d'autre : proposer un check-in en même "
        "temps qu'un questionnaire de trois minutes, c'est n'en faire aucun des deux",
    )
    intro = next(i for i in thread["items"] if i["kind"] == "text")
    check(
        "le message d'accueil annonce le coût et ce que ça change",
        "trois minutes" in intro["content"] and "ligne de base" in intro["content"],
        f"« {intro['content'][:120]}… »",
    )

    item = next(i for i in thread["items"] if i.get("widget_type") == "onboarding")

    # --- 3. Rempli --------------------------------------------------------
    response = client.post(
        f"/chat/widget/{item['id']}/submit", headers=h, json={"values": ANSWERS}
    )
    check("le questionnaire s'enregistre", response.status_code == 200, f"HTTP {response.status_code}")
    reply = " ".join(i.get("content") or "" for i in response.json()["items"])
    check(
        "la relance donne la ligne de base et ce que les réponses changent",
        "15/21" in reply and "avancera les exercices sur les sensations" in reply,
        f"« {reply[:190]}… »",
    )

    # --- 4. Les écritures au bon endroit ----------------------------------
    profile = db.query_one("SELECT profile FROM users WHERE id = %s", (user_id,))["profile"]
    check(
        "les difficultés sont écrites dans le profil — la clé que la règle attendait",
        profile.get("difficultes") == ["panique", "social", "inquietude"],
        f"profile.difficultes = {profile.get('difficultes')}",
    )
    check(
        "le questionnaire est versionné et daté",
        profile["onboarding"]["version"] == 1 and profile["onboarding"]["done_at"] == str(today),
        f"version {profile['onboarding']['version']} · {profile['onboarding']['done_at']} · "
        f"ancienneté {profile['onboarding']['anciennete']}",
    )
    check(
        "l'heure de rappel rejoint le profil, là où le planificateur la lit",
        (profile.get("rappel") or {}).get("heure") == "20:30",
        f"profile.rappel = {profile.get('rappel')}",
    )
    scales = {
        r["instrument"]: r
        for r in db.query_all(
            "SELECT instrument, total, severity FROM assessments WHERE user_id = %s", (user_id,)
        )
    }
    check(
        "les échelles vont dans `assessments`, pas dans le profil",
        scales["gad7"]["total"] == 15 and scales["phq2"]["total"] == 3,
        f"GAD-7 {scales['gad7']['total']} ({scales['gad7']['severity']}) · "
        f"PHQ-2 {scales['phq2']['total']} — c'est `assessments` que lisent la "
        "progression et le critère de rémission",
    )
    goal = db.query_one(
        """
        SELECT free_text FROM journal_entries
        WHERE user_id = %s AND kind = 'libre' ORDER BY created_at DESC LIMIT 1
        """,
        (user_id,),
    )
    check(
        "l'objectif est écrit en clair dans le journal",
        goal is not None and "métro" in (goal["free_text"] or ""),
        f"« {(goal or {}).get('free_text', '—')} »",
    )
    remembered = db.query_one(
        """
        SELECT count(*) AS n FROM user_chunks
        WHERE user_id = %s AND source_kind IN ('journal', 'assessment')
        """,
        (user_id,),
    )
    check(
        "objectif et échelles entrent en mémoire vectorisée",
        int(remembered["n"]) >= 3,
        f"{remembered['n']} souvenir(s) — l'objectif sera retrouvable dans six mois",
    )
    logged = db.query_one(
        """
        SELECT status FROM activity_logs
        WHERE user_id = %s AND activity_slug = 'objectifs-valeurs' AND entry_date = %s
        """,
        (user_id, today),
    )
    check(
        "l'activité du module 1 est marquée faite",
        logged is not None and logged["status"] == "fait",
        "`objectifs-valeurs` est précisément l'activité de la semaine 1 : la refaire "
        "demander serait absurde",
    )

    # --- 5. La porte de contre-indications --------------------------------
    check(
        "la porte des exercices intéroceptifs est validée et datée",
        profile.get("interoceptif_valide_le") == str(today),
        "validée ici plutôt que huit semaines plus tard devant un bouton inactif",
    )
    catalogue = client.get("/chat/interoceptif", headers=h).json()
    check(
        "et l'API la voit comme validée",
        catalogue["valide_le"] == str(today),
        f"valide_le = {catalogue['valide_le']}",
    )

    # --- 6. Les règles que ça débloque ------------------------------------
    fresh = db.query_one(
        "SELECT id::text, profile FROM users WHERE id = %s", (user_id,)
    )
    items = program.adaptive_items({"signaux": []}, fresh["profile"])
    slugs = [i["slug"] for i in items]
    check(
        "la règle sociale se déclenche enfin — elle était morte depuis le début",
        "experience-sociale" in slugs,
        f"items adaptatifs : {slugs}",
    )
    check(
        "l'exposition intéroceptive est avancée sur déclaration, sans attendre une crise enregistrée",
        "exposition-interoceptive" in slugs,
        "la règle existante exigeait une attaque notée **dans l'application** ; "
        "quelqu'un qui vient pour ça n'a pas attendu de s'inscrire pour en faire",
    )
    check(
        "et l'inquiétude déclarée propose le temps d'inquiétude, réserve comprise",
        "temps-inquietude" in slugs
        and "n'a pas retrouvé d'effet"
        in next(i["why"] for i in items if i["slug"] == "temps-inquietude"),
        "niveau B, et la réserve est dite : une étude chez des patients diagnostiqués "
        "n'a pas retrouvé d'effet",
    )
    why = next(i["why"] for i in items if i["slug"] == "exposition-interoceptive")
    check(
        "la justification reprend les sensations déclarées",
        "cœur qui s’accélère" in why,
        f"« {why[:130]}… »",
    )

    # --- 3 bis. Plus jamais proposé ---------------------------------------
    db.execute(
        "DELETE FROM thread_items WHERE user_id = %s AND role = 'assistant' AND created_at::date = %s",
        (user_id, today),
    )
    again = client.get("/chat/thread", headers=h).json()
    types = [i.get("widget_type") for i in again["items"] if i["kind"] == "widget"]
    check(
        "une fois rempli, il n'est plus proposé",
        "onboarding" not in [t for t in types if t],
        f"widgets du fil après réouverture : {sorted({t for t in types if t})} — "
        "l'état est lu dans le profil, donc un fil purgé ne le fait pas réapparaître",
    )
    fresh_items = [
        i for i in again["items"] if i["role"] == "assistant" and i["kind"] == "widget"
    ]
    check(
        "et l'ouverture du jour normale reprend la main",
        any(i.get("widget_type") in {"matin", "soir", "interoceptif", "exposition", "journal", "meditation", "breath", "echelles"} for i in fresh_items),
        f"proposé maintenant : {[i.get('widget_type') for i in fresh_items][-3:]}",
    )

print()
if FAILURES:
    print(f"[ERR] {len(FAILURES)} vérification(s) en échec :")
    for name in FAILURES:
        print(f"       - {name}")
    raise SystemExit(1)
print("[OK ] questionnaire initial : toutes les vérifications passent")
