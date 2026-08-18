"""Injecte 4 semaines de données de démonstration dans un compte existant.

    cd backend && python tests/seed_demo.py

Utile pour voir les courbes, les corrélations et les règles adaptatives sans
attendre un mois. Adaptez l'e-mail et le mot de passe ci-dessous à un compte
créé depuis l'interface. Les données simulent une amélioration progressive avec
des nuits courtes et des journées caféinées associées aux pics d'anxiété.
"""

import datetime as dt
import json
import urllib.request

BASE = "http://127.0.0.1:8000"
EMAIL = "demo.navigateur@exemple.fr"
PASSWORD = "demo-mot-de-passe-2026"
def call(method, path, body=None, token=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
        headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read() or b"{}")

tok = call("POST", "/auth/login", {"email": EMAIL, "password": PASSWORD})["access_token"]
today = dt.date.today()
for i in range(27, 0, -1):
    d = today - dt.timedelta(days=i)
    # tendance à la baisse avec du bruit, sommeil corrélé
    base = 8 - (27 - i) * 0.12
    anx = max(1, min(10, round(base + (2 if i % 5 == 0 else 0) - (1 if i % 4 == 0 else 0))))
    sleep = 5.5 if i % 5 == 0 else 7.5 + (0.5 if i % 3 == 0 else 0)
    call("POST", "/checkins", {"entry_date": str(d), "moment": "soir", "anxiety_0_10": anx,
        "mood_0_10": max(0, 10 - anx - 1), "sleep_hours": sleep, "sleep_quality_0_10": 4 if sleep < 6 else 7,
        "caffeine_units": 4 if i % 5 == 0 else 1, "alcohol_units": 2 if i % 7 == 0 else 0,
        "exercise_min": 0 if i % 3 else 35, "panic_attacks": 1 if i in (22, 9) else 0,
        "avoidance_0_10": max(0, 7 - (27 - i) // 6), "contexts": ["travail", "social"],
        "main_trigger": "réunion" if i % 2 else "transports"}, tok)
    for slug, ok in (("respiration-lente-10", i % 4 != 0), ("journal-libre", i % 3 != 0), ("checkin-quotidien", True)):
        call("POST", "/activities/logs", {"activity_slug": slug, "entry_date": str(d),
            "status": "fait" if ok else "pas_fait", "skip_reason": None if ok else "trop long le soir",
            "anxiety_before": anx if slug == "respiration-lente-10" and ok else None,
            "anxiety_after": max(0, anx - 2) if slug == "respiration-lente-10" and ok else None}, tok)

for weeks, items in [(4, [3,3,2,3,2,2,2]), (3, [3,2,2,2,2,2,2]), (2, [2,2,2,1,1,2,1]), (1, [2,1,1,1,1,1,1]), (0, [1,1,1,0,1,1,0])]:
    call("POST", "/assessments", {"instrument": "gad7", "items": items,
        "taken_on": str(today - dt.timedelta(days=weeks * 7))}, tok)

for label, anx in [("Prendre le métro à l'heure de pointe", 6), ("Téléphoner à un inconnu", 5),
                   ("Boire un café serré et rester avec les sensations", 4), ("Prendre la parole en réunion", 8)]:
    call("POST", "/exposures", {"label": label, "kind": "in_vivo", "anticipated_anxiety": anx,
        "safety_behaviors": ["rester près de la sortie"]}, tok)

call("POST", "/journal", {"kind": "exposition", "situation": "Métro bondé, ligne 13",
    "prediction": "Je vais faire une crise et devoir sortir à la station suivante",
    "prediction_probability": 75, "actual_outcome": "Anxiété à 7 pendant 4 minutes puis descente à 3. Je suis resté.",
    "learning": "Les sensations montent puis redescendent seules, sans que je fasse rien",
    "intensity_before": 7, "intensity_after": 3, "emotions": ["peur"], "body_sensations": ["cœur rapide"],
    "safety_behaviors_dropped": ["téléphone en main"]}, tok)
call("POST", "/journal", {"kind": "pensee", "situation": "Réunion d'équipe",
    "automatic_thought": "Je vais bafouiller et ils vont penser que je ne suis pas à la hauteur",
    "thinking_trap": "surestimation", "evidence_for": "Ça m'est arrivé une fois en 2024",
    "evidence_against": "J'ai pris la parole 30 fois cette année sans problème",
    "coping_plan": "Même si je bafouille, je reprends ma phrase. Personne n'en meurt.",
    "alternative_thought": "Je risque d'être tendu au début, et ça passera après deux phrases",
    "intensity_before": 8, "intensity_after": 4, "emotions": ["honte"], "body_sensations": ["gorge serrée"],
    "safety_behaviors_dropped": []}, tok)
print("données de démonstration injectées")
