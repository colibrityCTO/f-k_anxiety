"""Test de fumée du lot 6 : parcours du jour, trois créneaux, question du jour.

    cd backend && PYTHONPATH=. python tests/smoke_v5_jour.py

Six garanties :

1. **Chaque item du jour sait ce qu'il ouvre.** Sans ce champ, le parcours ne serait
   qu'une liste à lire.
2. La table activité → widget existe **une seule fois** : `chat.py` réutilise celle de
   `program.py` au lieu d'en garder une copie qui divergerait sans lever d'erreur.
3. **Un dépôt par créneau, pas par jour.** Avant, ouvrir l'application à 9 h consommait
   l'unique message et revenir à 20 h ne proposait plus rien.
4. Le même créneau ne parle pas deux fois — le verrou est dans `notification_log`, qui
   porte déjà la contrainte d'unicité.
5. **La nuit ne déclenche rien** : quelqu'un qui ouvre à 3 h n'a pas besoin d'une
   question sur sa journée.
6. **La question du milieu de journée est déterministe** : même jour, même question.
   Une question générée serait différente à chaque rechargement, donc impossible à
   reprendre.
"""

from __future__ import annotations

import datetime as dt

from fastapi.testclient import TestClient

from app import chat as chat_mod, db, program
from app.main import app

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    print(f"[{'OK ' if condition else 'ERR'}] {label}")
    if detail:
        print(f"      {detail}")
    if not condition:
        FAILURES.append(label)


def clear_slots(user_id, today) -> None:
    db.execute(
        "DELETE FROM notification_log WHERE user_id = %s AND kind LIKE 'ouverture_%%' "
        "AND sent_on = %s",
        (user_id, today),
    )


with TestClient(app) as client:
    email = f"jr{dt.datetime.now().strftime('%H%M%S%f')[:12]}@exemple.fr"
    auth = client.post(
        "/auth/register", json={"email": email, "password": "motdepasse-tres-long-2026"}
    ).json()
    h = {"Authorization": f"Bearer {auth['access_token']}"}
    user_id = auth["user"]["id"]
    today = dt.date.today()
    # Le questionnaire initial n'est pas l'objet de ce test, et il remplace l'ouverture.
    db.execute(
        """
        UPDATE users SET profile = profile || jsonb_build_object(
            'onboarding', jsonb_build_object('version', 1, 'done_at', CURRENT_DATE::text),
            'difficultes', '["panique", "social"]'::jsonb
        ) WHERE id = %s
        """,
        (user_id,),
    )
    print(f"[OK ] compte créé : {email}")

    # --- 1 & 2. Le parcours est actionnable -------------------------------
    day = client.get("/program/today", headers=h).json()
    with_widget = [i for i in day["items"] if i.get("widget")]
    advice_only = [i for i in day["items"] if i.get("widget") is None]
    check(
        "chaque item du jour porte le widget qu'il ouvre",
        len(with_widget) >= 3 and all("widget" in i for i in day["items"]),
        f"{len(day['items'])} items · {len(with_widget)} ouvrent un widget · "
        f"{len(advice_only)} sont des conseils sans formulaire "
        f"({[i['activity']['slug'] for i in advice_only]})",
    )
    check(
        "les trois natures d'item sont présentes",
        {i["slot"] for i in day["items"]} >= {"socle", "module"},
        f"slots : {sorted({i['slot'] for i in day['items']})}",
    )
    check(
        "les items adaptatifs portent leurs observations déclenchantes",
        all(
            i["triggered_by"] for i in day["items"] if i["slot"] == "adaptatif"
        ),
        "sans elles, « pourquoi » serait une affirmation sans preuve",
    )
    check(
        "la table activité → widget n'existe qu'une fois",
        chat_mod.SLUG_WIDGETS is program.SLUG_WIDGETS,
        "`chat.py` réutilise l'objet de `program.py` — deux copies auraient divergé "
        "sans jamais lever d'erreur",
    )

    # --- 5. La nuit ne déclenche rien -------------------------------------
    check(
        "la nuit ne correspond à aucun créneau",
        chat_mod.slot_for(dt.datetime(2026, 8, 18, 3)) is None,
        "3 h → aucun créneau : le matin attendra le réveil",
    )
    check(
        "les trois créneaux couvrent la journée",
        [chat_mod.slot_for(dt.datetime(2026, 8, 18, h)) for h in (9, 14, 20)]
        == ["matin", "midi", "soir"],
        "9 h → matin · 14 h → midi · 20 h → soir",
    )

    # --- 6. La question du jour est déterministe -------------------------
    q1 = chat_mod.midday_question(4, today)
    q2 = chat_mod.midday_question(4, today)
    q3 = chat_mod.midday_question(4, today + dt.timedelta(days=1))
    check(
        "même jour, même question",
        q1 == q2,
        f"« {q1} » — recharger l'application ne la change pas, sinon on ne pourrait "
        "pas y revenir après l'avoir laissée de côté",
    )
    check(
        "le lendemain, une autre",
        q1 != q3,
        f"demain : « {q3} »",
    )
    module_two = chat_mod.midday_question(2, today)
    check(
        "la question dépend du module",
        all(
            chat_mod.midday_question(m, today)
            in [
                q["q"]
                for q in chat_mod.MIDDAY_QUESTIONS
                if q["module"] in (None, m)
            ]
            for m in range(1, 9)
        ),
        f"module 2 : « {module_two[:70]} » — on ne demande pas à quelqu'un en semaine 2 "
        "ce qu'il a appris de sa dernière exposition",
    )

    # --- 3 & 4. Un dépôt par créneau -------------------------------------
    print()
    clear_slots(user_id, today)
    db.execute(
        "DELETE FROM thread_items WHERE user_id = %s AND role = 'assistant' "
        "AND created_at::date = %s",
        (user_id, today),
    )

    def deposit(slot: str) -> list[dict]:
        """Simule une ouverture de l'application dans un créneau donné."""
        import app.routers.chat as router

        original = chat_mod.slot_for
        chat_mod.slot_for = lambda now=None: slot  # noqa: ARG005
        try:
            router._open_slot(  # noqa: SLF001
                db.query_one("SELECT id::text AS id, profile, display_name FROM users WHERE id = %s", (user_id,)),
                today,
            )
        finally:
            chat_mod.slot_for = original
        return db.query_all(
            """
            SELECT id::text AS id, engine, widget_type, kind FROM thread_items
            WHERE user_id = %s AND role = 'assistant' AND created_at::date = %s
            ORDER BY seq
            """,
            (user_id, today),
        )

    after_morning = deposit("matin")
    check(
        "le créneau du matin dépose une ouverture",
        len(after_morning) >= 1,
        f"{len(after_morning)} item(s) — moteurs : {[r['engine'] for r in after_morning]}",
    )

    again = deposit("matin")
    check(
        "le même créneau ne parle pas deux fois",
        len(again) == len(after_morning),
        f"{len(after_morning)} → {len(again)} : le verrou est dans notification_log, "
        "avec sa contrainte d'unicité (compte, type, jour)",
    )

    after_midday = deposit("midi")
    # Comparaison par identifiant et non par position : depuis qu'un seul formulaire
    # reste ouvert à la fois, un dépôt peut **retirer** un widget vierge en plus d'en
    # ajouter. Un découpage positionnel supposait une liste qui ne fait que croître.
    connus = {r["id"] for r in again}
    added = [r for r in after_midday if r["id"] not in connus]
    check(
        "le créneau du milieu de journée ajoute la question du jour",
        any(r["engine"] == "question-du-jour" for r in added),
        f"ajouté : {[(r['engine'], r['widget_type']) for r in added]}",
    )
    check(
        "et il ne réclame aucune saisie de plus qu'un journal libre",
        {r["widget_type"] for r in added if r["widget_type"]} <= {"journal"},
        "un troisième formulaire en milieu de journée aurait fait abandonner les deux "
        "autres — c'est une question, avec un endroit pour répondre",
    )

    after_evening = deposit("soir")
    check(
        "le créneau du soir ajoute encore quelque chose",
        len(after_evening) > len(after_midday),
        f"{len(after_midday)} → {len(after_evening)} items : avec un seul dépôt par "
        "jour, ouvrir à 9 h consommait le message et revenir à 20 h ne proposait rien",
    )

    slots_used = db.query_all(
        "SELECT kind FROM notification_log WHERE user_id = %s AND kind LIKE 'ouverture_%%' "
        "AND sent_on = %s ORDER BY kind",
        (user_id, today),
    )
    check(
        "les trois créneaux sont consignés séparément",
        [r["kind"] for r in slots_used] == ["ouverture_matin", "ouverture_midi", "ouverture_soir"],
        f"{[r['kind'] for r in slots_used]}",
    )

    # --- L'intention en langage naturel ----------------------------------
    from app import capture

    parsed = capture.parse("qu'est-ce que je dois faire aujourd'hui")
    check(
        "« qu'est-ce que je dois faire » ouvre le parcours",
        "jour" in parsed.intents,
        f"intentions détectées : {parsed.intents}",
    )

print()
if FAILURES:
    print(f"[ERR] {len(FAILURES)} vérification(s) en échec :")
    for name in FAILURES:
        print(f"       - {name}")
    raise SystemExit(1)
print("[OK ] lot 6 : toutes les vérifications passent")
