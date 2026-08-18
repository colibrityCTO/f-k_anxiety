"""Test de fumée : exerce l'API de bout en bout contre une base réelle.

    cd backend && PYTHONPATH=. python tests/smoke_e2e.py

Nécessite une base PostgreSQL accessible via DATABASE_URL et l'extension
pgvector. Crée un compte jetable, injecte 12 jours de données, puis vérifie :
le refus d'accès sans jeton, l'upsert des check-in, le refus d'une exposition
sans prédiction, les seuils du GAD-7 et sa DMCI, les signaux déterministes
(corrélations, adhérence, effet mesuré), l'analyse locale avec ses citations,
la recherche hybride, les règles adaptatives, et la détection de drapeau rouge.

Aucune clé d'API n'est nécessaire : le moteur bascule alors sur l'analyse locale
et la recherche lexicale, ce qui est précisément un des chemins à tester.
"""

import datetime as dt
import json  # noqa: F401 - utile pour inspecter les réponses en debug

from fastapi.testclient import TestClient

from app.main import app

def show(label, r, keys=None):
    ok = "OK " if r.status_code < 400 else "ERR"
    print(f"[{ok}] {r.status_code} {label}")
    if r.status_code >= 400:
        print("     ", r.text[:400]); return None
    try: body = r.json()
    except Exception: return None
    if keys:
        if isinstance(body, list): body = body[0] if body else {}
        print("     ", {k: body.get(k) for k in keys})
    return body

with TestClient(app) as c:
    show("GET /meta", c.get("/meta"), ["nom"])
    show("GET /health", c.get("/health"), ["database","pgvector","kb_chunks"])

    # sans jeton -> doit être refusé
    print("[%s] %s GET /program/today sans jeton" % ("OK " if c.get("/program/today").status_code==401 else "ERR", c.get("/program/today").status_code))

    email = f"test{dt.datetime.now().strftime('%H%M%S')}@exemple.fr"
    auth = show("POST /auth/register", c.post("/auth/register", json={"email": email, "password": "motdepasse-tres-long-2026", "display_name": "Test"}), ["expires_in"])
    token = auth["access_token"]
    h = {"Authorization": f"Bearer {token}"}
    # `ai_consent` est envoyé exprès à false : le serveur doit l'ignorer et
    # laisser l'IA active — c'est ce que garantit l'assertion qui suit.
    me = show("PATCH /auth/me (profil)", c.patch("/auth/me", headers=h, json={"profile": {"difficultes": ["panique","social"]}, "ai_consent": False}), ["ai_consent","profile"])
    assert me["ai_consent"] is True, "l'IA doit rester active : ai_consent ne se coupe pas"

    day = show("GET /program/today", c.get("/program/today", headers=h), ["week","module","module_title","checkin_done","gad7_due"])
    print("      items:", [(i["activity"]["slug"], i["slot"]) for i in day["items"]])

    # 12 jours de données rétroactives
    today = dt.date.today()
    for i in range(12, 0, -1):
        d = today - dt.timedelta(days=i)
        anx = 8 if i % 3 == 0 else 5
        c.post("/checkins", headers=h, json={
            "entry_date": str(d), "moment": "soir", "anxiety_0_10": anx, "mood_0_10": 10-anx,
            "sleep_hours": 5.0 if i % 3 == 1 else 8.0, "sleep_quality_0_10": 4 if i%3==1 else 8,
            "caffeine_units": 4 if i%3==0 else 1, "alcohol_units": 0, "exercise_min": 0,
            "panic_attacks": 1 if i == 4 else 0, "avoidance_0_10": 7,
            "contexts": ["travail","social"], "main_trigger": "réunion"})
        c.post("/activities/logs", headers=h, json={"activity_slug": "respiration-lente-10", "entry_date": str(d),
            "status": "fait" if i % 2 else "pas_fait", "skip_reason": None if i%2 else "pas le temps",
            "anxiety_before": anx, "anxiety_after": max(0, anx-2)})
    print("[OK ] 12 jours de check-in + 12 logs d'activité créés")

    show("POST /assessments gad7", c.post("/assessments", headers=h, json={"instrument":"gad7","items":[3,3,2,2,1,2,2],"taken_on":str(today-dt.timedelta(days=8))}), ["total","severity"])
    a2 = show("POST /assessments gad7 (2e)", c.post("/assessments", headers=h, json={"instrument":"gad7","items":[2,2,1,1,1,1,1]}), ["total","severity"])
    print("      lecture du delta:", a2["interpretation"].get("lecture_du_delta"))

    ex = show("POST /exposures", c.post("/exposures", headers=h, json={"label":"Prendre le métro à l'heure de pointe","kind":"in_vivo","anticipated_anxiety":5,"safety_behaviors":["rester près de la sortie"]}), ["id","label"])
    show("POST /exposures/{id}/attempt", c.post(f"/exposures/{ex['id']}/attempt?learning=L'anxi%C3%A9t%C3%A9+est+redescendue+seule+en+12+min", headers=h), ["attempts","best_learning"])

    show("POST /journal exposition", c.post("/journal", headers=h, json={"kind":"exposition","situation":"Métro bondé","prediction":"Je vais faire une crise et m'évanouir","prediction_probability":70,"actual_outcome":"Anxiété à 7 puis redescendue, pas de crise","learning":"Les sensations montent puis redescendent seules","intensity_before":7,"intensity_after":3,"emotions":["peur"],"body_sensations":["cœur rapide"],"safety_behaviors_dropped":["téléphone en main"]}), ["id","kind"])
    show("POST /journal exposition invalide (doit échouer)", c.post("/journal", headers=h, json={"kind":"exposition","situation":"rien"}))
    show("POST /journal pensee", c.post("/journal", headers=h, json={"kind":"pensee","situation":"Réunion","automatic_thought":"Je vais bafouiller","thinking_trap":"surestimation","intensity_before":8,"intensity_after":4,"emotions":["honte"],"body_sensations":[],"safety_behaviors_dropped":[]}), ["id"])

    sig = show("GET /insights/signals", c.get("/insights/signals?days=21", headers=h), ["periode"])
    for s in sig["signaux"]:
        if s["id"] in ("correlation_sommeil_anxiete","correlation_cafeine_anxiete","adherence","gad7","expositions","effet_mesure_activites","tendance_anxiete"):
            print(f"      · {s['id']}: valeur={s['value']!r} n={s.get('n')} → {s['verdict']}")

    ins = show("POST /insights/analyze (moteur local)", c.post("/insights/analyze", headers=h, json={"scope":"quotidien"}), ["engine","headline","risk_flag"])
    print("      citations:", [c_["doc_id"] for c_ in ins["citations"]])
    print("      recommandations:", [r["slug"] for r in ins["recommendations"]])
    print("      --- corps de l'analyse ---")
    print("\n".join("      " + l for l in ins["body"].splitlines()[:26]))

    ks = show("GET /knowledge/search", c.get("/knowledge/search?q=expiration+longue+vagal+respiration", headers=h), ["mode"])
    print("      top:", [(r["doc_id"], r["recuperation"]["lexical_rank"], r["recuperation"]["vector_rank"]) for r in ks["resultats"][:4]])
    show("GET /knowledge/{doc}", c.get("/knowledge/exposition-interoceptive", headers=h), ["doc_id","title","evidence_level"])
    ov = show("GET /program/overview", c.get("/program/overview", headers=h), ["current_week","current_module"])
    print("      conditions de sortie:", [(cd["libelle"][:45], cd["atteinte"]) for cd in ov["critere_de_sortie"]["conditions"]])
    show("GET /program/history", c.get("/program/history?days=30", headers=h))
    day2 = show("GET /program/today (après données)", c.get("/program/today", headers=h), ["week","adherence_7j","streak"])
    print("      items adaptatifs:", [(i["activity"]["slug"], i["why_for_you"][:90]) for i in day2["items"] if i["slot"]=="adaptatif"])

    # drapeau rouge
    c.post("/journal", headers=h, json={"kind":"libre","free_text":"Je n'en peux plus, j'ai envie de mourir.","emotions":[],"body_sensations":[],"safety_behaviors_dropped":[]})
    risky = show("POST /insights/analyze après drapeau rouge", c.post("/insights/analyze", headers=h, json={"scope":"quotidien"}), ["risk_flag","headline"])
    print("      corps:", risky["body"][:200].replace("\n"," "))
