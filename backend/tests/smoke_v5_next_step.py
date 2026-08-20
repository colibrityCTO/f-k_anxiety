"""Test de fumée du classeur : « il y a toujours quelque chose à faire ».

    cd backend && PYTHONPATH=. python tests/smoke_v5_next_step.py

Huit garanties, et chacune répare un comportement précis qui existait avant :

1. **Le classeur ne rend jamais la main vide.** Trois messages en dur disaient
   l'inverse — « rien à faire aujourd'hui », « tu veux faire quoi ? ». Ils venaient
   d'une cascade dont chaque branche devait prévoir son propre repli.
2. **Le socle est proposé dans le fil.** L'ancienne sélection ne regardait que deux
   créneaux du programme sur quatre : respiration et journal quotidiens n'étaient
   jamais proposés, alors qu'ils étaient calculés chaque matin.
3. **Valider ne ferme pas la journée.** Tous les gestionnaires renvoyaient
   `widget: None`, deux d'entre eux `suggestions: []`. Comme l'ouverture proactive
   est verrouillée à un dépôt par créneau, valider à 8 h fermait tout jusqu'à 17 h.
4. **Le questionnaire initial enchaîne** au lieu de renvoyer à demain.
5. **Les propositions dépendent de l'état.** Elles étaient constantes, donc fausses :
   « Mes chiffres » au premier jour ouvre une courbe de deux points.
6. **`noter` est résolu par le serveur.** La grille laissait ouvrir « Ce soir » à
   dix heures, ce que `_moment_due` interdit côté serveur depuis toujours.
7. **L'assiduité a un dénominateur réel.** Seuls des `fait` étaient écrits : la part
   des activités réalisées valait 1.0 en permanence, y compris pour quelqu'un qui
   n'avait rien fait.
8. **Les widgets morts ne sont plus ouvrables** par le modèle.
"""

from __future__ import annotations

import datetime as dt

from fastapi.testclient import TestClient

from app import chat as chat_mod, db, next_step, program
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
    return body["items"]


with TestClient(app) as client:
    email = f"v5ns{dt.datetime.now().strftime('%H%M%S')}@exemple.fr"
    auth = client.post(
        "/auth/register", json={"email": email, "password": "motdepasse-tres-long-2026"}
    ).json()
    h = {"Authorization": f"Bearer {auth['access_token']}"}
    user_id = auth["user"]["id"]
    today = dt.date.today()
    print(f"[OK ] compte créé : {email}")

    # --- 8. La liste blanche ------------------------------------------------
    morts = {"account", "logout", "checkin", "onboarding", "panique"}
    check(
        "les widgets morts ne sont plus ouvrables par le modèle",
        not (morts & chat_mod.WIDGET_TYPES),
        f"encore ouvrables : {sorted(morts & chat_mod.WIDGET_TYPES) or 'aucun'} — "
        "le front sait toujours les rendre, plus rien n'en crée",
    )
    refuse = client.post("/chat/widget", headers=h, json={"type": "account"})
    check(
        "et l'API refuse de les ouvrir",
        refuse.status_code == 422,
        f"HTTP {refuse.status_code} sur POST /chat/widget type=account",
    )

    # --- 4. Le questionnaire initial n'est plus une impasse ------------------
    ouverture = client.get("/chat/thread", headers=h).json()
    onboarding = next(
        (i for i in ouverture["items"] if i.get("widget_type") == "onboarding"), None
    )
    check("le questionnaire initial est déposé", onboarding is not None)

    reponse = client.post(
        f"/chat/widget/{onboarding['id']}/submit",
        headers=h,
        json={
            "values": {
                "objectif": "reprendre le métro",
                "difficultes": ["panique"],
                "anciennete": "1-3 ans",
                "gad7": [2, 2, 2, 2, 2, 2, 2],
                "phq2": [1, 1],
                "sensibilite": [2, 2, 2],
                "paniques_30j": 3,
                "sensations": ["coeur"],
                "cafeine_par_jour": 3,
                "alcool_par_semaine": 2,
                "sport_par_semaine": 1,
                "heure_rappel": "21:00",
                "medecin_ecarte": True,
                "contre_indications": False,
            }
        },
    ).json()
    textes = [i.get("content") or "" for i in reponse["items"] if i["kind"] == "text"]
    suite = " ".join(textes)
    check(
        "et il n'annonce plus qu'il n'y a rien d'autre à faire",
        "rien d'autre à faire" not in suite.lower() and "revenir demain" not in suite.lower(),
        f"« …{suite[-160:].strip()} »",
    )
    enchaine = [i.get("widget_type") for i in reponse["items"] if i["kind"] == "widget"]
    check(
        "il enchaîne directement sur l'étape suivante",
        any(enchaine),
        f"widget proposé dans la foulée : {enchaine}",
    )

    # --- 1 & 2. Le classeur, à froid puis à chaud ---------------------------
    state = chat_mod.day_state(user_id, today)
    step = next_step.choose({"id": user_id, "profile": {}}, state)
    check(
        "le classeur propose quelque chose dès le premier jour",
        bool(step["reply"]),
        f"[{step['engine']}] {step['reply'][:110]}…",
    )

    # On remplit le socle en entier, puis on redemande. C'est le cas qui produisait
    # « rien à faire aujourd'hui ».
    #
    # Les deux moments sont saisis, pas seulement le matin : la ligne « Noter » de la
    # barre suit le créneau en cours, donc un test lancé le soir doit noter le soir.
    # C'est volontaire — afficher « fait » à vingt heures pendant que le fil réclame
    # la journée était précisément la contradiction à supprimer.
    saisies = [("matin", {"sleep_hours": 7.0, "anxiety_0_10": 5})]
    if dt.datetime.now().hour >= chat_mod.EVENING_FROM:
        saisies.append(("soir", {"anxiety_0_10": 5, "anxiety_peak_0_10": 7, "avoidance_0_10": 3}))
    for kind, values in (
        *saisies,
        ("breath", {"anxiety_before": 6, "anxiety_after": 4, "duration_min": 5}),
        ("journal", {"kind": "libre", "free_text": "journée correcte"}),
    ):
        items = open_widget(client, h, kind)
        widget = next(i for i in items if i.get("widget_type") == kind)
        client.post(f"/chat/widget/{widget['id']}/submit", headers=h, json={"values": values})

    state = chat_mod.day_state(user_id, today)
    check(
        "le socle est complet",
        state["socle"]["fait"] == state["socle"]["total"],
        f"{state['socle']['fait']}/{state['socle']['total']} — "
        + " · ".join(f"{i['label']}={'✓' if i['fait'] else '·'}" for i in state["socle"]["items"]),
    )

    step = next_step.choose({"id": user_id, "profile": {"difficultes": ["panique"]}}, state)
    check(
        "et il reste quelque chose à proposer une fois le socle tenu",
        bool(step["reply"]) and step["engine"] != "vide",
        f"[{step['engine']}] {step['reply'][:140]}…",
    )
    check(
        "avec un endroit où répondre, pas seulement un texte",
        step["widget"] is not None or step["engine"] == "programme",
        f"widget : {step['widget']['type'] if step['widget'] else 'aucun'}",
    )

    # --- 3. Valider ne ferme pas la journée ---------------------------------
    items = open_widget(client, h, "maintenant")
    widget = next(i for i in items if i.get("widget_type") == "maintenant")
    apres = client.post(
        f"/chat/widget/{widget['id']}/submit", headers=h, json={"values": {"anxiety_0_10": 4}}
    ).json()
    suites = [i for i in apres["items"] if i["kind"] == "widget" and i["status"] == "ouvert"]
    messages = [i for i in apres["items"] if i["kind"] == "text"]
    check(
        "valider une mesure propose la suite",
        bool(suites) or any(i["suggestions"] for i in messages),
        f"widget suivant : {[i['widget_type'] for i in suites]} · "
        f"propositions : {[s for i in messages for s in i['suggestions']]}",
    )
    check(
        "et ne repropose pas ce qui vient d'être fait",
        all(i["widget_type"] != "maintenant" for i in suites),
        "« maintenant » validé ne doit pas rouvrir « maintenant »",
    )

    # --- 5. Les propositions dépendent de l'état ----------------------------
    labels = [s for i in messages for s in i["suggestions"]]
    check(
        "« Mes chiffres » n'est pas proposé avant dix jours de données",
        "Mes chiffres" not in labels,
        f"jours notés : {state['jours_notes']} · propositions : {labels}",
    )
    check(
        "« Respirer 5 min » n'est pas proposé quand la séance du jour est faite",
        "Respirer 5 min" not in labels,
        f"propositions : {labels}",
    )

    # --- 6. `noter` est résolu par le serveur -------------------------------
    resolu = open_widget(client, h, "noter")
    types = [i.get("widget_type") for i in resolu if i["kind"] == "widget"]
    # La saisie du créneau est faite : « noter » doit tomber sur la mesure
    # instantanée, la seule qui n'ait ni heure ni quota. C'est ce qui remplace le
    # doublon d'avant, où la grille proposait de re-remplir un formulaire déjà rempli.
    check(
        "« noter » ouvre le bon formulaire, décidé côté serveur",
        types == ["maintenant"],
        f"saisie du créneau déjà faite à {dt.datetime.now().hour} h → ouvert : {types} "
        "(attendu maintenant, jamais un formulaire déjà rempli)",
    )

    # --- 3 bis. Un refus explicite n'est pas remis en avant ------------------
    #
    # Reporter le check-in puis se l'entendre reproposer à l'action suivante n'est pas
    # de l'insistance utile. Le report est déjà enregistré comme donnée ; la saisie
    # reste atteignable par « Noter », qui est un geste volontaire.
    #
    # Vérifié sur `_moment` directement plutôt que par un aller-retour HTTP : la
    # branche à couvrir dépend de l'heure qu'il est, et un test dont le résultat
    # change selon le moment où on le lance ne prouve rien.
    vierge = dict(state, matin_done=False, soir_done=False, saisie_reportee=False)
    check(
        "une saisie manquante est bien réclamée",
        next_step._moment(vierge, set(), dt.datetime.now()) is not None,
    )
    check(
        "mais une saisie refusée aujourd'hui ne l'est plus",
        next_step._moment(dict(vierge, saisie_reportee=True), set(), dt.datetime.now()) is None,
        "le report est déjà une donnée ; « Noter » reste disponible à la demande",
    )

    # Et le refus doit laisser une trace là où les signaux la cherchent. Le matin est
    # le cas piégeux : la table activité → widget fait pointer le check-in quotidien
    # sur le formulaire du soir, donc sans traitement explicite un matin refusé ne
    # laissait rien.
    import app.routers.chat as router

    hier = today - dt.timedelta(days=1)
    db.execute(
        """
        INSERT INTO activity_logs (user_id, activity_slug, entry_date, status)
        VALUES (%s, 'checkin-quotidien', %s, 'propose')
        ON CONFLICT (user_id, activity_slug, entry_date) DO UPDATE SET status = 'propose'
        """,
        (user_id, today),
    )
    router._log_skip(user_id, "matin")
    trace = db.query_one(
        """
        SELECT status FROM activity_logs
        WHERE user_id = %s AND entry_date = %s AND activity_slug = 'checkin-quotidien'
        """,
        (user_id, today),
    )
    check(
        "refuser le matin laisse une trace dans le journal des activités",
        trace is not None and trace["status"] == "reporte",
        f"statut : {trace['status'] if trace else 'aucun'} — les refus vivaient dans "
        "`thread_items`, alors que l'assiduité se calcule sur `activity_logs`",
    )
    # On remet la donnée réelle : le check-in a bien été fait plus haut.
    db.execute(
        """
        UPDATE activity_logs SET status = 'fait'
        WHERE user_id = %s AND entry_date = %s AND activity_slug = 'checkin-quotidien'
        """,
        (user_id, today),
    )

    # --- 6 bis. Les explications ne se répètent pas --------------------------
    #
    # La justification du module était reproposée à l'identique chaque jour pendant
    # une à trois semaines. Une phrase répétée quinze fois cesse d'être lue, puis fait
    # soupçonner que rien n'est personnalisé. Ce registre-là se dit une fois.
    #
    # Testé sur un compte neuf : celui du dessus a déjà consommé ses explications au
    # fil des validations, et une assertion sur une liste vide ne prouve rien.
    frais = client.post(
        "/auth/register",
        json={
            "email": f"v5nsx{dt.datetime.now().strftime('%H%M%S')}@exemple.fr",
            "password": "motdepasse-tres-long-2026",
        },
    ).json()
    fid = frais["user"]["id"]
    fuser = {"id": fid, "profile": {"difficultes": ["panique"]}}
    vus: list[str] = []
    for _ in range(6):
        etape = next_step.choose(fuser, chat_mod.day_state(fid, today))
        expl = etape.get("explication")
        if expl:
            vus.append(expl["titre"])
    check(
        "un compte neuf reçoit bien des explications",
        len(vus) >= 2,
        f"{len(vus)} servie(s) sur 6 tours : {vus}",
    )
    check(
        "et aucune n'est servie deux fois",
        len(vus) == len(set(vus)),
        "module, fiche du corpus, mécanisme de l'exercice — chacune une fois",
    )
    check(
        "les contre-indications, elles, se rappellent au bout d'un mois",
        next_step.EXPLANATION_TTL["securite"] == 30
        and next_step.EXPLANATION_TTL["module"] is None,
        "un exercice d'hyperventilation n'a pas les mêmes réserves selon l'état du "
        "moment — « tu l'as lu il y a six mois » n'est pas une garantie",
    )

    # --- 7. L'assiduité a un dénominateur ------------------------------------
    program.build_day(user_id, {}, today)
    statuts = {
        r["status"]: int(r["n"])
        for r in db.query_all(
            """
            SELECT status, count(*) AS n FROM activity_logs
            WHERE user_id = %s AND entry_date = %s GROUP BY status
            """,
            (user_id, today),
        )
    }
    check(
        "les activités proposées sont enregistrées comme telles",
        statuts.get("propose", 0) > 0,
        f"statuts du jour : {statuts} — sans « propose », le dénominateur de "
        "l'assiduité ne contenait que des réussites",
    )

    # La veille : des proposées jamais faites doivent faire baisser l'assiduité.
    hier = today - dt.timedelta(days=1)
    db.execute(
        """
        INSERT INTO activity_logs (user_id, activity_slug, entry_date, status)
        VALUES (%s, 'scan-corporel', %s, 'propose'), (%s, 'yoga-doux', %s, 'propose')
        ON CONFLICT (user_id, activity_slug, entry_date) DO NOTHING
        """,
        (user_id, hier, user_id, hier),
    )
    plan = program.build_day(user_id, {}, today)
    check(
        "et une journée passée sans rien faire fait baisser l'assiduité",
        plan["adherence_7j"] < 1.0,
        f"assiduité 7 j = {plan['adherence_7j']} — elle valait 1.0 en permanence avant, "
        "quel que soit ce qui avait été fait",
    )

print()
if FAILURES:
    print(f"[ERR] {len(FAILURES)} vérification(s) en échec : {FAILURES}")
    raise SystemExit(1)
print("[OK ] classeur : toutes les vérifications passent")
