"""Test de fumée du lot 0 de la V5 : lisibilité et navigation du fil.

    cd backend && PYTHONPATH=. python tests/smoke_v5.py

Cinq garanties, vérifiées contre une vraie base :

1. **Une vue n'encombre pas.** Ouvrir trois fois « Mes chiffres » laisse un seul
   item dans le fil, et les identifiants retirés remontent au front.
2. **Une vue qui produit quelque chose cesse d'être une vue.** Un widget validé
   rejoint le registre et ne peut plus être retiré.
3. **Le bilan hebdomadaire survit.** C'est un widget `analysis`, donc une
   consultation — mais sa présence dans le fil est le verrou qui l'empêche d'être
   redéposé, donc il est durable.
4. **Un formulaire dont la journée est passée est périmé, pas reporté.**
   « Reporté » est une réponse de l'utilisateur ; la déduire serait l'inventer.
5. **Le fil se pagine, et remonter ne crée rien.** Seule la première page
   déclenche l'ouverture du jour.

Et la sixième, qui est le cœur du lot : **l'ouverture du fil parle du programme
du jour** — elle reprend la justification calculée par `program.py` et ses
observations, au lieu de s'arrêter à « tu veux faire quoi ? ».
"""

from __future__ import annotations

import datetime as dt

from fastapi.testclient import TestClient

from app import db
from app.main import app

def _reset_opening(user_id, today) -> None:
    """Remet le fil dans l'état « rien déposé aujourd'hui ».

    Deux effacements, parce qu'il y a deux mécanismes depuis la V5 : les items du fil,
    et le **verrou de créneau** dans `notification_log`. Depuis que l'ouverture est
    déposée une fois par créneau (matin / midi / soir) plutôt qu'une fois par jour, la
    présence d'un item ne fait plus office de verrou — purger le fil seul ne provoque
    donc plus de nouvelle ouverture, et c'est exactement le but du verrou.
    """
    db.execute(
        "DELETE FROM thread_items WHERE user_id = %s AND role = 'assistant' "
        "AND created_at::date = %s",
        (user_id, today),
    )
    db.execute(
        "DELETE FROM notification_log WHERE user_id = %s AND kind LIKE 'ouverture_%%' "
        "AND sent_on = %s",
        (user_id, today),
    )


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


FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    print(f"[{'OK ' if condition else 'ERR'}] {label}")
    if detail:
        print(f"      {detail}")
    if not condition:
        FAILURES.append(label)


def thread(client, headers, **params):
    return client.get("/chat/thread", headers=headers, params=params).json()


def widgets_of(body, kind):
    return [i for i in body["items"] if i.get("widget_type") == kind]


with TestClient(app) as client:
    email = f"v5{dt.datetime.now().strftime('%H%M%S')}@exemple.fr"
    auth = client.post(
        "/auth/register", json={"email": email, "password": "motdepasse-tres-long-2026"}
    ).json()
    h = {"Authorization": f"Bearer {auth['access_token']}"}
    user_id = auth["user"]["id"]
    _skip_onboarding(user_id)
    today = dt.date.today()
    print(f"[OK ] compte créé : {email}")

    first = thread(client, h)
    check(
        "première page : ouverture du jour déposée",
        len(first["items"]) > 0,
        f"{len(first['items'])} item(s) · has_more={first['has_more']}",
    )

    # --- 1. Une vue n'encombre pas ------------------------------------------
    retired_total = 0
    for _ in range(3):
        body = client.post("/chat/widget", headers=h, json={"type": "stats"}).json()
        retired_total += len(body.get("retired") or [])
    after = thread(client, h)
    stats_items = widgets_of(after, "stats")
    check(
        "trois ouvertures de « Mes chiffres » → un seul item dans le fil",
        len(stats_items) == 1,
        f"{len(stats_items)} item(s) · {retired_total} vue(s) retirée(s) et signalée(s) au front",
    )

    in_db = db.query_one(
        "SELECT count(*) AS n FROM thread_items WHERE user_id = %s AND widget_type = 'stats'",
        (user_id,),
    )
    check(
        "les vues retirées sont supprimées en base, pas seulement masquées",
        int(in_db["n"]) == 1,
        f"{in_db['n']} ligne(s) `stats` en base",
    )

    # Une vue ne s'annonce pas : son en-tête dit déjà ce qu'elle est.
    labels = [i for i in after["items"] if i["role"] == "user" and i.get("content") == "Mes chiffres"]
    check("une vue ne dépose pas de message d'annonce", not labels)

    # Deux types différents : l'invariant est « au plus une vue », tous types confondus.
    client.post("/chat/widget", headers=h, json={"type": "sources"})
    mixed = thread(client, h)
    views = [i for i in mixed["items"] if i.get("ephemeral")]
    check(
        "ouvrir « Sources » retire « Mes chiffres » : au plus une vue à la fois",
        len(views) == 1 and views[0]["widget_type"] == "sources",
        f"vue(s) présente(s) : {[v['widget_type'] for v in views]}",
    )

    # --- 2. Un widget de saisie reste, et son résumé est calculable ---------
    checkin = widgets_of(thread(client, h), "checkin")
    if not checkin:
        checkin = [
            i
            for i in client.post("/chat/widget", headers=h, json={"type": "checkin"}).json()["items"]
            if i.get("widget_type") == "checkin"
        ]
    submitted = client.post(
        f"/chat/widget/{checkin[-1]['id']}/submit",
        headers=h,
        json={"values": {"anxiety_0_10": 6, "sleep_hours": 6.5, "caffeine_units": 2}},
    ).json()
    frozen = next(i for i in submitted["items"] if i["id"] == checkin[-1]["id"])
    check(
        "un check-in validé est figé et durable",
        frozen["status"] == "valide" and not frozen["ephemeral"],
        f"status={frozen['status']} · ephemeral={frozen['ephemeral']}",
    )

    # Une analyse validée est un résultat : elle cesse d'être une vue.
    analysis = [
        i
        for i in client.post("/chat/widget", headers=h, json={"type": "analysis"}).json()["items"]
        if i.get("widget_type") == "analysis"
    ][0]
    check("un widget d'analyse est éphémère à l'ouverture", analysis["ephemeral"] is True)
    done = client.post(
        f"/chat/widget/{analysis['id']}/submit", headers=h, json={"values": {"scope": "libre"}}
    ).json()
    produced = next((i for i in done["items"] if i["id"] == analysis["id"]), None)
    check(
        "une analyse validée cesse d'être une vue : le résultat reste dans le fil",
        produced is not None and produced["ephemeral"] is False,
        f"ephemeral={produced['ephemeral'] if produced else '—'}",
    )

    # --- 3. Le bilan hebdomadaire est durable ------------------------------
    db.execute(
        """
        INSERT INTO thread_items (user_id, role, kind, widget_type, payload, status, ephemeral)
        VALUES (%s, 'assistant', 'widget', 'analysis',
                '{"prefill": {"scope": "hebdomadaire"}}'::jsonb, 'ouvert', false)
        """,
        (user_id,),
    )
    db.execute("UPDATE thread_items SET ephemeral = false WHERE user_id = %s AND false", (user_id,))
    client.post("/chat/widget", headers=h, json={"type": "analysis"})
    weekly = db.query_one(
        """
        SELECT count(*) AS n FROM thread_items
        WHERE user_id = %s AND widget_type = 'analysis'
          AND payload->'prefill'->>'scope' = 'hebdomadaire'
        """,
        (user_id,),
    )
    check(
        "le bilan hebdomadaire survit à l'ouverture d'une autre analyse",
        int(weekly["n"]) == 1,
        "sans ça, le bilan serait redéposé chaque jour",
    )

    # --- 4. Périmé, pas reporté -------------------------------------------
    db.execute(
        """
        INSERT INTO thread_items (user_id, role, kind, widget_type, status, created_at)
        VALUES (%s, 'assistant', 'widget', 'journal', 'ouvert', now() - interval '9 days')
        """,
        (user_id,),
    )
    _reset_opening(user_id, today)
    thread(client, h)  # première page → ménage + ouverture du jour
    stale = db.query_all(
        """
        SELECT status FROM thread_items
        WHERE user_id = %s AND widget_type = 'journal' AND created_at::date < %s
        """,
        (user_id, today),
    )
    check(
        "un formulaire de la semaine dernière est « perime », jamais « reporte »",
        bool(stale) and all(r["status"] == "perime" for r in stale),
        f"statuts trouvés : {sorted({r['status'] for r in stale})}",
    )

    # --- 5. Pagination -----------------------------------------------------
    for n in range(12):
        client.post("/chat/widget", headers=h, json={"type": "checkin", "label": f"saisie {n}"})
    page1 = thread(client, h, limit=5)
    check(
        "la première page est bornée",
        len(page1["items"]) == 5 and page1["has_more"] is True,
        f"{len(page1['items'])} item(s) · oldest_seq={page1['oldest_seq']}",
    )
    before_count = db.query_one(
        "SELECT count(*) AS n FROM thread_items WHERE user_id = %s", (user_id,)
    )
    page2 = thread(client, h, limit=5, before=page1["oldest_seq"])
    after_count = db.query_one(
        "SELECT count(*) AS n FROM thread_items WHERE user_id = %s", (user_id,)
    )
    check(
        "remonter dans le fil ne crée aucun item",
        int(before_count["n"]) == int(after_count["n"]),
        f"{before_count['n']} → {after_count['n']}",
    )
    check(
        "la page suivante est strictement plus ancienne",
        bool(page2["items"]) and max(i["seq"] for i in page2["items"]) < page1["oldest_seq"],
        f"seq max page 2 = {max((i['seq'] for i in page2['items']), default=None)} "
        f"< oldest_seq page 1 = {page1['oldest_seq']}",
    )
    check(
        "seule la première page porte l'état du jour",
        "state" in page1 and "state" not in page2,
    )

    # --- 6. L'ouverture parle du programme du jour -------------------------
    # Le check-in du jour est fait, le GAD-7 vient d'être posé : c'est le cas où
    # l'ouverture s'arrêtait à « tu veux faire quoi ? ».
    db.execute(
        """
        INSERT INTO assessments (user_id, instrument, taken_on, items, total, severity)
        VALUES (%s, 'gad7', %s, '{1,1,1,1,1,1,1}', 7, 'légère')
        ON CONFLICT (user_id, instrument, taken_on) DO NOTHING
        """,
        (user_id, today),
    )
    # De quoi déclencher une règle adaptative : de l'évitement élevé, sur assez de jours.
    for offset in range(1, 16):
        day = today - dt.timedelta(days=offset)
        db.execute(
            """
            INSERT INTO daily_checkins
                (user_id, entry_date, moment, anxiety_0_10, avoidance_0_10, sleep_hours,
                 caffeine_units, panic_attacks)
            VALUES (%s, %s, 'soir', %s, 8, %s, 3, 0)
            ON CONFLICT (user_id, entry_date, moment) DO NOTHING
            """,
            (user_id, day, 6 + (offset % 3), 5.0 + (offset % 4) * 0.5),
        )
    _reset_opening(user_id, today)
    reopened = thread(client, h)
    # L'ouverture n'est pas forcément le dernier message : la proposition de bilan
    # hebdomadaire est déposée juste après elle.
    assistant = [i for i in reopened["items"] if i["role"] == "assistant" and i["kind"] == "text"]
    latest = next((i for i in assistant if i.get("engine") == "programme"), {})
    check(
        "l'ouverture du jour vient du programme, pas d'une phrase creuse",
        latest.get("engine") == "programme",
        f"moteurs présents : {[i.get('engine') for i in assistant]}",
    )
    check(
        "elle porte ses preuves : le panneau « d'où ça sort » est alimenté",
        bool(latest.get("citations")),
        f"{len(latest.get('citations') or [])} citation(s) : "
        f"{[c.get('titre') for c in (latest.get('citations') or [])]}",
    )
    if latest.get("content"):
        print(f"      « {latest['content'][:160].replace(chr(10), ' ')}… »")

    print()
    if FAILURES:
        print(f"[ERR] {len(FAILURES)} vérification(s) en échec :")
        for name in FAILURES:
            print(f"       - {name}")
        raise SystemExit(1)
    print("[OK ] lot 0 : toutes les vérifications passent")
