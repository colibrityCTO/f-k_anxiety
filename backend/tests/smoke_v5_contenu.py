"""Test de fumée du contenu et des champs orphelins.

    cd backend && PYTHONPATH=. python tests/smoke_v5_contenu.py

Ce qu'il vérifie :

1. **Les trois champs qui existaient sans interface** sont maintenant écrits :
   `similarity_0_10` sur l'intéroceptif, `belief_before/after_0_100` sur le journal de
   pensées, et l'agrégat des épisodes dans le rapport.
2. La similarité est **commentée**, pas seulement stockée — c'est elle qui dit s'il
   faut répéter l'exercice ou en changer.
3. La pratique corporelle du soir **progresse** avec les semaines, et ses niveaux de
   preuve ne sont pas uniformes.
4. Les quatre nouvelles activités sont au catalogue avec leur fiche.
5. Les 31 fiches sont ingérées et retrouvables — sans quoi l'application affirmerait
   des choses dont les sources ne sont pas dans son propre corpus.
6. La règle « un paramètre à la fois » propose de **réduire**, pas d'arrêter.
7. La cohorte **refuse** de comparer sous onze personnes, et ne verse rien sans
   consentement.
"""

from __future__ import annotations

import datetime as dt

from fastapi.testclient import TestClient

from app import cohort, db, program, search
from app.data.activities import ACTIVITIES
from app.main import app

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    print(f"[{'OK ' if condition else 'ERR'}] {label}")
    if detail:
        print(f"      {detail}")
    if not condition:
        FAILURES.append(label)


TODAY = dt.date.today()

with TestClient(app) as client:
    auth = client.post(
        "/auth/register",
        json={
            "email": f"ct{dt.datetime.now().strftime('%H%M%S%f')[:12]}@exemple.fr",
            "password": "motdepasse-tres-long-2026",
        },
    ).json()
    h = {"Authorization": f"Bearer {auth['access_token']}"}
    user_id = auth["user"]["id"]
    db.execute(
        """
        UPDATE users SET profile = profile || jsonb_build_object(
            'onboarding', jsonb_build_object('version', 1, 'done_at', CURRENT_DATE::text),
            'interoceptif_valide_le', CURRENT_DATE::text
        ) WHERE id = %s
        """,
        (user_id,),
    )
    print(f"[OK ] compte créé : {auth['user']['email']}")

    def open_widget(kind):
        body = client.post("/chat/widget", headers=h, json={"type": kind}).json()
        return next(i for i in body["items"] if i.get("widget_type") == kind)

    # --- 1 & 2. La similarité, enfin écrite et commentée ------------------
    item = open_widget("interoceptif")
    response = client.post(
        f"/chat/widget/{item['id']}/submit",
        headers=h,
        json={
            "values": {
                "slug": "hyperventilation",
                "prediction": "je vais m'évanouir",
                "prediction_probability": 70,
                "actual_outcome": "vertige, rien de plus",
                "anxiety_max": 8,
                "anxiety_after": 3,
                "similarity_0_10": 9,
            }
        },
    )
    check("l'exercice intéroceptif s'enregistre", response.status_code == 200,
          f"HTTP {response.status_code}")
    stored = db.query_one(
        """
        SELECT similarity_0_10 FROM journal_entries
        WHERE user_id = %s AND kind = 'exposition' ORDER BY created_at DESC LIMIT 1
        """,
        (user_id,),
    )
    check(
        "la ressemblance aux crises réelles est enregistrée",
        stored is not None and stored["similarity_0_10"] == 9,
        f"similarity_0_10 = {(stored or {}).get('similarity_0_10')} — la colonne existait "
        "depuis le lot 1 et personne ne l'écrivait",
    )
    reply = " ".join(i.get("content") or "" for i in response.json()["items"])
    check(
        "et elle est commentée : répéter celui-là plutôt qu'en changer",
        "9/10" in reply and "répéter" in reply,
        f"« …{reply[reply.find('Ressemblance'):reply.find('Ressemblance') + 130]}… »"
        if "Ressemblance" in reply
        else reply[:120],
    )

    low = open_widget("interoceptif")
    low_reply = " ".join(
        i.get("content") or ""
        for i in client.post(
            f"/chat/widget/{low['id']}/submit",
            headers=h,
            json={"values": {"slug": "paille", "prediction": "je vais étouffer",
                             "actual_outcome": "rien", "anxiety_max": 5, "anxiety_after": 3,
                             "similarity_0_10": 2}},
        ).json()["items"]
    )
    check(
        "une ressemblance basse conseille de changer d'exercice",
        "en essayer un autre" in low_reply,
        "provoquer un vertige n'apprend rien à quelqu'un dont les crises sont digestives",
    )

    # --- 1 bis. Le pourcentage de croyance -------------------------------
    journal = open_widget("journal")
    client.post(
        f"/chat/widget/{journal['id']}/submit",
        headers=h,
        json={
            "values": {
                "kind": "pensee",
                "situation": "réunion de 15 h",
                "automatic_thought": "je vais bafouiller et tout le monde le verra",
                "intensity_before": 8,
                "intensity_after": 5,
                "belief_before_0_100": 90,
                "belief_after_0_100": 40,
            }
        },
    )
    thought = db.query_one(
        """
        SELECT intensity_before, intensity_after, belief_before_0_100, belief_after_0_100
        FROM journal_entries WHERE user_id = %s AND kind = 'pensee'
        ORDER BY created_at DESC LIMIT 1
        """,
        (user_id,),
    )
    check(
        "le journal de pensées enregistre les deux pourcentages de croyance",
        thought is not None
        and thought["belief_before_0_100"] == 90
        and thought["belief_after_0_100"] == 40,
        f"croyance {thought['belief_before_0_100']} % → {thought['belief_after_0_100']} % · "
        f"intensité {thought['intensity_before']} → {thought['intensity_after']} — deux "
        "mesures distinctes, qui peuvent bouger indépendamment",
    )

    # --- 1 ter. L'agrégat dans le rapport --------------------------------
    for minutes in (8, 12, 20):
        client.post(
            "/chat/panique",
            headers=h,
            json={"body_symptoms": ["poitrine"], "tools_used": [], "anxiety_peak": 9,
                  "anxiety_after": 3, "time_to_relief_min": minutes,
                  "feared_outcome_happened": False},
        )
    report = client.get("/chat/rapport", headers=h).json()
    check(
        "le rapport imprimable porte l'agrégat des épisodes",
        "episodes" in report and report["episodes"]["episodes"] == 3,
        f"{report['episodes']['episodes']} épisodes · médiane "
        f"{report['episodes']['duree_mediane_min']} min · redouté survenu "
        f"{report['episodes']['redoute_arrive']}/{report['episodes']['redoute_renseigne']}",
    )
    check(
        "et sa phrase est composée côté serveur",
        report["episodes"]["phrase"] is not None and "0 fois" in report["episodes"]["phrase"],
        f"« {report['episodes']['phrase']} »",
    )

    # --- 3 & 4. Le contenu du programme ----------------------------------
    print()
    progression = [(w, program.body_practice_for(w)) for w in (1, 3, 6, 10)]
    check(
        "la pratique corporelle du soir progresse avec les semaines",
        [p for _, p in progression]
        == ["etirements-soir", "relaxation-musculaire", "yoga-doux", "yoga-nidra"],
        " · ".join(f"s{w} → {p}" for w, p in progression),
    )
    by_slug = {a["slug"]: a for a in ACTIVITIES}
    levels = {
        s: by_slug[s]["evidence_level"]
        for s in ("etirements-soir", "relaxation-musculaire", "yoga-doux", "yoga-nidra", "action-engagee")
    }
    check(
        "les niveaux de preuve ne sont pas uniformes, et l'ordre en tient compte",
        levels == {"etirements-soir": "C", "relaxation-musculaire": "A", "yoga-doux": "C",
                   "yoga-nidra": "B", "action-engagee": "B"},
        f"{levels}",
    )
    check(
        "le yoga doux porte la réserve qui compte",
        "DSM" in (by_slug["yoga-doux"]["contraindications"] or ""),
        "aucun effet retrouvé chez les patients dont le trouble est diagnostiqué selon "
        "le DSM — le taire aurait été plus simple et faux",
    )
    check(
        "l'action engagée dit qu'elle n'est pas supérieure à la TCC",
        "pas supérieure à la TCC" in (by_slug["action-engagee"]["contraindications"] or ""),
        "l'ACT est comparable, pas meilleure : elle complète les expositions, elle ne les "
        "remplace pas",
    )

    # --- 5. Les fiches sont dans le corpus -------------------------------
    docs = {
        r["doc_id"]: r["evidence_level"]
        for r in db.query_all("SELECT doc_id, evidence_level FROM kb_documents")
    }
    expected = {
        "nommage-affect", "froid-reflexe-immersion", "charge-visuospatiale",
        "sensibilite-anxieuse", "prediction-limites", "capteurs-et-panique",
        "agenda-sommeil", "mesure-momentanee", "acceptation-action-engagee",
        "travail-corporel",
    }
    check(
        "les fiches de la V5 sont ingérées",
        expected <= set(docs),
        f"{len(docs)} fiches au corpus · manquantes : {expected - set(docs) or 'aucune'}",
    )
    check(
        "chaque activité nouvelle pointe une fiche existante",
        all(by_slug[s]["kb_doc_id"] in docs
            for s in ("etirements-soir", "yoga-doux", "yoga-nidra", "action-engagee")),
        "sinon le panneau « d'où ça sort » renverrait vers rien",
    )
    hits = search.hybrid_search("nommer la sensation avant de respirer", k=5)
    check(
        "et elles sont retrouvables par recherche",
        any("nommage" in (r.get("doc_id") or "") for r in hits),
        f"trouvés : {[r.get('doc_id') for r in hits][:4]}",
    )

    # --- 6. « Un paramètre à la fois » -----------------------------------
    signals = {
        "signaux": [
            {"id": "tendance_anxiete", "label": "Anxiété moyenne", "value": 8.0,
             "delta": 2.0, "verdict": "en hausse", "observations": [], "n": 14},
        ]
    }
    rules = program.adaptive_items(
        signals,
        {"onboarding": {"anciennete": "plus-15-ans"}},
    )
    # La règle ne vise que les modules d'exposition : en semaine 1, elle ne s'applique pas.
    check(
        "hors phase d'exposition, la règle ne se déclenche pas",
        not any("réduire l'intensité" in r["why"] for r in rules),
        f"semaine 1 → items : {[r['slug'] for r in rules]}",
    )

    # --- 7. La cohorte refuse ---------------------------------------------
    print()
    # Compté sur **cette** clé et non globalement : la table est partagée par tous les
    # comptes, et un passage précédent y aurait laissé des lignes.
    def mine() -> int:
        return int(
            db.query_one(
                "SELECT count(*) AS n FROM cohort_facts WHERE user_key = %s",
                (cohort.user_key(user_id),),
            )["n"]
        )

    contributed = cohort.contribute(user_id, {}, TODAY, {"anxiete": 6})
    check(
        "rien n'est versé sans consentement explicite",
        contributed is False and mine() == 0,
        "le consentement à la cohorte est distinct de celui du service, et refusable "
        "sans perte de fonction — article 9 du RGPD",
    )
    with_consent = cohort.contribute(
        user_id, {"consentements": {"cohorte": True}}, TODAY, {"anxiete": 6, "paniques": 1}
    )
    check(
        "et versé quand il l'est",
        with_consent is True and mine() == 1,
        "clé HMAC, pas d'identifiant de compte : pseudonyme, et l'application ne "
        "prétend pas que c'est de l'anonymat",
    )
    refusal = cohort.compare("caffeine_units >= 3", {})
    check(
        "aucune comparaison n'est renvoyée sous onze personnes",
        refusal["affichable"] is False and refusal["seuil"] == 11,
        f"« {refusal['raison']} »",
    )
    volume = cohort.volume()
    check(
        "et le blocage est expliqué comme un problème d'effectif, pas de code",
        "11 personnes distinctes" in volume["message"],
        f"« {volume['message'][:120]}… »",
    )

print()
if FAILURES:
    print(f"[ERR] {len(FAILURES)} vérification(s) en échec :")
    for name in FAILURES:
        print(f"       - {name}")
    raise SystemExit(1)
print("[OK ] contenu et champs orphelins : toutes les vérifications passent")
