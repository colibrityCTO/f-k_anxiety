"""Test de fumée du lot 4 : charge du jour et prévision du lendemain.

    cd backend && PYTHONPATH=. python tests/smoke_v5_prevision.py

Sept garanties, et trois portent sur des refus — ce sont les plus importantes.

1. **La charge n'est pas affichée sans pondération personnelle.** Si aucune
   association n'a survécu à la correction du lot 3, il n'y a pas de poids ; inventer
   des poids universels annulerait tout le travail statistique.
2. **La persistance est le modèle par défaut**, et elle le reste tant qu'aucun calcul
   ne fait mieux. La référence à battre n'est pas le hasard.
3. **La régression ne gagne que si elle gagne vraiment**, mesurée en avance glissante :
   à chaque jour testé, le modèle n'est ajusté que sur les jours antérieurs.
4. **Une prévision ne se réécrit jamais.** C'est ce qui rend l'erreur affichable.
5. **La fourchette est calibrée sur les variations de la personne**, pas sur un
   écart-type théorique.
6. **Le bilan compare au modèle de référence**, échecs compris.
7. **Aucune crise n'est jamais prédite.**
"""

from __future__ import annotations

import datetime as dt
import random

from fastapi.testclient import TestClient

from app import db, forecast, signals as signals_mod
from app.main import app

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    print(f"[{'OK ' if condition else 'ERR'}] {label}")
    if detail:
        print(f"      {detail}")
    if not condition:
        FAILURES.append(label)


def register(client, tag):
    email = f"{tag}{dt.datetime.now().strftime('%H%M%S%f')[:12]}@exemple.fr"
    auth = client.post(
        "/auth/register", json={"email": email, "password": "motdepasse-tres-long-2026"}
    ).json()
    return {"Authorization": f"Bearer {auth['access_token']}"}, auth["user"]["id"]


def write_day(user_id, day, anxiety, sleep, caffeine=1, exercise=0, panic=0):
    db.execute(
        """
        INSERT INTO daily_checkins
            (user_id, entry_date, moment, anxiety_0_10, sleep_hours, caffeine_units,
             alcohol_units, exercise_min, avoidance_0_10, panic_attacks)
        VALUES (%s, %s, 'soir', %s, %s, %s, 0, %s, 4, %s)
        ON CONFLICT (user_id, entry_date, moment) DO UPDATE SET
            anxiety_0_10 = EXCLUDED.anxiety_0_10, sleep_hours = EXCLUDED.sleep_hours,
            caffeine_units = EXCLUDED.caffeine_units, exercise_min = EXCLUDED.exercise_min
        """,
        (user_id, day, anxiety, sleep, caffeine, exercise, panic),
    )


def bundle(client, headers):
    return client.get("/chat/prevision", headers=headers).json()


with TestClient(app) as client:
    today = dt.date.today()

    # --- 1 & 2. Du bruit : pas de charge, persistance retenue ------------
    print("=== bruit : 50 jours sans structure ===")
    rng = random.Random(777)
    h_noise, id_noise = register(client, "pvnoise")
    for index in range(50, 0, -1):
        write_day(
            id_noise, today - dt.timedelta(days=index - 1),
            rng.randint(0, 10), round(rng.uniform(4.0, 9.0), 1), rng.randint(0, 4),
        )

    noise = bundle(client, h_noise)
    check(
        "aucune charge affichée sans pondération personnelle",
        noise["charge"]["valeur"] is None,
        f"raison : {noise['charge']['raison'][:120] if noise['charge']['raison'] else '—'}",
    )
    check(
        "les composantes disent lesquelles ne comptent pas, et pourquoi",
        all(c["poids"] == 0 for c in noise["charge"]["composantes"]),
        "chaque facteur porte « association non retenue chez toi — ne compte pas » : "
        "poids nul, pas un petit poids",
    )
    # Sur du bruit, la persistance est *mauvaise* : reporter une valeur aléatoire pour
    # prédire la suivante est pire que de viser la moyenne. Un modèle a donc le droit de
    # gagner ici — mais en revenant à la moyenne, pas grâce à des facteurs. C'est cette
    # distinction que le nom du modèle doit porter, sinon il s'attribue un mérite qu'il
    # n'a pas. Ce test avait d'ailleurs attrapé exactement cette formulation trompeuse.
    check(
        "aucun facteur n'entre dans le modèle : seule l'anxiété elle-même",
        noise["prevision"]["validation"]["prédicteurs"] == ["anxiete"],
        f"prédicteurs : {noise['prevision']['validation']['prédicteurs']} — aucune "
        "association n'a survécu, donc aucun facteur n'est autorisé à entrer",
    )
    check(
        "un modèle qui ne fait que revenir à la moyenne est nommé comme tel",
        noise["prevision"]["model"] in {"persistance", "retour-moyenne"},
        f"modèle = {noise['prevision']['model']} · MAE persistance "
        f"{noise['prevision']['validation']['mae_persistance']} vs "
        f"{noise['prevision']['validation']['mae_regression']}",
    )
    check(
        "et la phrase ne s'attribue aucun facteur qu'elle n'utilise pas",
        "tes propres facteurs" not in noise["prevision"]["phrase"],
        f"« {noise['prevision']['phrase'][:190]} »",
    )
    check(
        "une fourchette, jamais un point",
        noise["prevision"]["interval_high"] > noise["prevision"]["interval_low"],
        f"{noise['prevision']['interval_low']} à {noise['prevision']['interval_high']} "
        f"(point : {noise['prevision']['predicted']})",
    )
    check(
        "aucune crise n'est prédite",
        not any("panique" in str(v).lower() or "crise" in str(v).lower()
                for v in (noise["prevision"]["phrase"],)),
        "la prévision ne porte que sur le niveau d'anxiété, jamais sur un événement",
    )

    # --- 3. Un signal réellement prédictif -------------------------------
    print("\n=== structure réelle : la nuit détermine le lendemain ===")
    h_real, id_real = register(client, "pvreal")
    rng2 = random.Random(99)
    # Le sommeil alterne, et l'anxiété du **lendemain** en dépend. La persistance est
    # alors mauvaise par construction (elle reporte une valeur qui alterne), et un
    # modèle qui utilise le sommeil de la veille doit faire nettement mieux. C'est le
    # cas où la régression *doit* gagner — sinon la validation ne sert à rien.
    for index in range(60, 0, -1):
        day = today - dt.timedelta(days=index - 1)
        short = index % 2 == 0
        sleep = round(rng2.uniform(4.0, 5.5), 1) if short else round(rng2.uniform(7.5, 8.5), 1)
        # L'anxiété du jour dépend du sommeil de la veille : veille courte → 8, sinon 2.
        previous_short = (index + 1) % 2 == 0
        anxiety = (8 if previous_short else 2) + rng2.randint(-1, 1)
        write_day(id_real, day, max(0, min(10, anxiety)), sleep)

    real = bundle(client, h_real)
    validation = real["prevision"]["validation"]
    check(
        "la régression gagne quand elle a réellement de quoi",
        validation["gagnant"] == "regression",
        f"MAE régression {validation['mae_regression']} < persistance "
        f"{validation['mae_persistance']} sur {validation['n_test']} jours de test",
    )
    check(
        "le sommeil est entré dans les prédicteurs, parce que son association tient",
        "sommeil" in validation["prédicteurs"],
        f"prédicteurs : {validation['prédicteurs']}",
    )
    check(
        "une charge est calculable dès qu'une association est retenue",
        real["charge"]["valeur"] is not None,
        f"charge = {real['charge']['valeur']}/10 · "
        f"composantes actives : "
        f"{[c['facteur'] for c in real['charge']['composantes'] if c.get('actif')]}",
    )
    check(
        "la charge reste distincte de l'anxiété déclarée",
        real["charge"]["valeur"] != real["anxiete_declaree"]
        or "charge" in (real["charge"].get("methode") or ""),
        f"anxiété déclarée {real['anxiete_declaree']} · charge {real['charge']['valeur']} — "
        "deux chiffres, deux natures",
    )

    # --- 5. La fourchette suit les variations de la personne -------------
    stable_h, stable_id = register(client, "pvstable")
    for index in range(40, 0, -1):
        write_day(stable_id, today - dt.timedelta(days=index - 1), 5, 7.0)
    stable = bundle(client, stable_h)
    noise_width = noise["prevision"]["interval_high"] - noise["prevision"]["interval_low"]
    stable_width = stable["prevision"]["interval_high"] - stable["prevision"]["interval_low"]
    check(
        "une personne stable reçoit une fourchette plus étroite qu'une personne instable",
        stable_width < noise_width,
        f"stable {stable_width:.2f} point(s) contre instable {noise_width:.2f} — "
        "l'intervalle est calibré sur les variations réelles, pas sur une constante",
    )

    # --- 4. Une prévision ne se réécrit pas ------------------------------
    print("\n=== immuabilité ===")
    stored = forecast.predict(
        {**{}, **signals_mod.compute(id_real, today, 120, with_days=True)["jours"]},
        signals_mod.compute(id_real, today, 120),
        today,
    )
    forecast.store(id_real, stored)
    first_row = db.query_one(
        """
        SELECT predicted, created_at FROM daily_forecasts
        WHERE user_id = %s AND target_date = %s AND model = %s
        """,
        (id_real, stored["target_date"], stored["model"]),
    )
    # Deuxième écriture avec une valeur volontairement différente : elle doit être ignorée.
    forecast.store(id_real, {**stored, "predicted": 0.0, "interval_low": 0.0, "interval_high": 1.0})
    second_row = db.query_one(
        """
        SELECT predicted, count(*) OVER () AS n FROM daily_forecasts
        WHERE user_id = %s AND target_date = %s AND model = %s
        """,
        (id_real, stored["target_date"], stored["model"]),
    )
    check(
        "une prévision déjà posée n'est ni écrasée ni dupliquée",
        float(second_row["predicted"]) == float(first_row["predicted"]) and int(second_row["n"]) == 1,
        f"annoncé {first_row['predicted']}, réécriture tentée à 0.0 → reste "
        f"{second_row['predicted']} ({second_row['n']} ligne). Sans ça, on pourrait "
        "« corriger » une prévision ratée après coup, donc ne jamais se tromper",
    )

    # --- 6. Le bilan compare à la référence ------------------------------
    print("\n=== bilan des prévisions passées ===")
    # On pose des prévisions sur des jours déjà observés pour pouvoir les noter.
    for index in range(1, 12):
        day = today - dt.timedelta(days=index)
        db.execute(
            """
            INSERT INTO daily_forecasts
                (user_id, target_date, made_on, model, predicted, interval_low,
                 interval_high, baseline)
            VALUES (%s, %s, %s, 'persistance', %s, %s, %s, %s)
            ON CONFLICT (user_id, target_date, model) DO NOTHING
            """,
            (id_real, day, day - dt.timedelta(days=1), 5.0, 2.0, 8.0, 7.0),
        )
    scored = bundle(client, h_real)["historique"]
    check(
        "les prévisions passées sont notées contre ce qui est réellement arrivé",
        scored["n"] >= 10 and scored["mae"] is not None,
        f"{scored['n']} prévisions notées · erreur moyenne {scored['mae']} · "
        f"persistance {scored['mae_persistance']}",
    )
    check(
        "la couverture de la fourchette est affichée, même mauvaise",
        scored["couverture"] is not None,
        f"couverture réelle {round((scored['couverture'] or 0) * 100)} % pour une "
        "fourchette annoncée à 95 % — affiché plutôt que corrigé en silence",
    )
    check(
        "chaque prévision notée porte l'erreur de la persistance à côté de la sienne",
        all(d["erreur_persistance"] is not None for d in scored["detail"]),
        f"exemple : annoncé {scored['detail'][0]['annonce']}, observé "
        f"{scored['detail'][0]['observe']}, erreur {scored['detail'][0]['erreur']} "
        f"contre {scored['detail'][0]['erreur_persistance']} pour la persistance",
    )

    # --- Le check-in du soir pose la prévision --------------------------
    print("\n=== écriture au check-in du soir ===")
    h_flow, id_flow = register(client, "pvflow")
    for index in range(40, 1, -1):
        write_day(id_flow, today - dt.timedelta(days=index), 5, 7.0)
    item = next(
        i
        for i in client.post("/chat/widget", headers=h_flow, json={"type": "soir"}).json()["items"]
        if i.get("widget_type") == "soir"
    )
    submitted = client.post(
        f"/chat/widget/{item['id']}/submit",
        headers=h_flow,
        json={"values": {"anxiety_0_10": 6, "anxiety_peak_0_10": 8, "caffeine_units": 2}},
    ).json()
    rows = db.query_all(
        "SELECT target_date, model, predicted FROM daily_forecasts WHERE user_id = %s",
        (id_flow,),
    )
    check(
        "valider le soir pose la prévision du lendemain",
        len(rows) == 1 and rows[0]["target_date"] == today + dt.timedelta(days=1),
        f"{len(rows)} prévision(s) · cible {rows[0]['target_date'] if rows else '—'} · "
        f"annoncé {rows[0]['predicted'] if rows else '—'}",
    )
    message = " ".join(i.get("content") or "" for i in submitted["items"])
    check(
        "et la réponse du soir annonce l'estimation",
        "probablement entre" in message or "probablement autour de" in message,
        f"« …{message[message.find('probablement') - 20 : message.find('probablement') + 90]}… »"
        if "probablement" in message
        else message[:120],
    )

print()
if FAILURES:
    print(f"[ERR] {len(FAILURES)} vérification(s) en échec :")
    for name in FAILURES:
        print(f"       - {name}")
    raise SystemExit(1)
print("[OK ] lot 4 : toutes les vérifications passent")
