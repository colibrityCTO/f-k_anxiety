"""Test de fumée du lot 5 : intégration Whoop.

    cd backend && PYTHONPATH=. python tests/smoke_v5_whoop.py

Les appels réseau sont simulés : ce test vérifie le **mapping**, la pagination, le
chiffrement, la révocation et l'entrée dans les signaux — pas la connectivité chez
Whoop, qui demande des identifiants et ne se teste pas hors ligne.

Neuf garanties, dont deux refus :

1. Les jetons sont **chiffrés en base** : la colonne ne contient jamais le jeton.
2. Un rafraîchissement qui ne renvoie pas de nouveau jeton de rafraîchissement ne
   **détruit pas** l'ancien — sinon la connexion mourrait au bout d'une heure.
3. Les quatre ressources alimentent une ligne par jour, et la pagination suit
   `next_token`.
4. Un enregistrement non noté (`score_state != SCORED`) est **ignoré** : l'écrire
   produirait des valeurs nulles qui écraseraient ensuite les bonnes.
5. Le sommeil du capteur **n'écrase pas** le sommeil déclaré : deux tables, deux
   provenances.
6. Une séance devient testable pour l'hypothèse « FC max ≥ 150 puis crise ».
7. La VFC entre dans les signaux comme toute autre source, avec les mêmes seuils.
8. Un webhook non signé est **refusé**.
9. La révocation avec purge efface les données **et** leurs traces en mémoire
   vectorisée — sinon la donnée survivrait à sa suppression.
"""

from __future__ import annotations

import datetime as dt
import json

from fastapi.testclient import TestClient

from app import db, signals as signals_mod
from app.config import settings
from app.integrations import whoop
from app.main import app

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    print(f"[{'OK ' if condition else 'ERR'}] {label}")
    if detail:
        print(f"      {detail}")
    if not condition:
        FAILURES.append(label)


TODAY = dt.date.today()


def iso(day: dt.date, hour: int = 8) -> str:
    return f"{day.isoformat()}T{hour:02d}:00:00.000Z"


# --- Faux service Whoop -----------------------------------------------------
#
# On remplace `_get`, donc la pagination, le mapping et les écritures sont bien
# exercés — seul le transport HTTP est écarté.

CALLS: list[tuple[str, dict]] = []


def fake_get(user_id: str, path: str, params: dict | None = None) -> dict:
    CALLS.append((path, params or {}))
    page = (params or {}).get("nextToken")

    if path == "/v2/recovery":
        # Deux pages, pour vérifier que `next_token` est bien suivi.
        if page is None:
            return {
                "records": [
                    {
                        "created_at": iso(TODAY - dt.timedelta(days=2)),
                        "score_state": "SCORED",
                        "score": {
                            "hrv_rmssd_milli": 31.5, "resting_heart_rate": 62,
                            "recovery_score": 38, "spo2_percentage": 96.1,
                            "skin_temp_celsius": 33.4,
                        },
                    },
                    {
                        # Non noté : doit être ignoré, sinon ses valeurs nulles
                        # écraseraient celles d'une autre passe.
                        "created_at": iso(TODAY - dt.timedelta(days=1)),
                        "score_state": "PENDING_SCORE",
                        "score": None,
                    },
                ],
                "next_token": "page-2",
            }
        return {
            "records": [
                {
                    "created_at": iso(TODAY),
                    "score_state": "SCORED",
                    "score": {
                        "hrv_rmssd_milli": 58.0, "resting_heart_rate": 51,
                        "recovery_score": 79, "spo2_percentage": 97.2,
                        "skin_temp_celsius": 33.1,
                    },
                }
            ],
            "next_token": None,
        }

    if path == "/v2/activity/sleep":
        return {
            "records": [
                {
                    "end": iso(TODAY, 7),
                    "score_state": "SCORED",
                    "score": {
                        "stage_summary": {
                            "total_light_sleep_time_milli": 10_800_000,   # 3 h
                            "total_slow_wave_sleep_time_milli": 5_400_000,  # 1,5 h
                            "total_rem_sleep_time_milli": 3_600_000,      # 1 h
                        },
                        "sleep_efficiency_percentage": 88.5,
                        "sleep_performance_percentage": 71.0,
                        "respiratory_rate": 15.2,
                    },
                }
            ],
            "next_token": None,
        }

    if path == "/v2/cycle":
        return {
            "records": [
                {
                    "start": iso(TODAY),
                    "score_state": "SCORED",
                    "score": {
                        "strain": 14.2, "average_heart_rate": 78,
                        "max_heart_rate": 168, "kilojoule": 9_450.0,
                    },
                }
            ],
            "next_token": None,
        }

    if path == "/v2/activity/workout":
        return {
            "records": [
                {
                    "id": "wk-1",
                    "start": iso(TODAY - dt.timedelta(days=1), 18),
                    "end": iso(TODAY - dt.timedelta(days=1), 19),
                    "sport_name": "running",
                    "score": {
                        "strain": 12.8, "average_heart_rate": 152,
                        "max_heart_rate": 172, "kilojoule": 3_200.0,
                        "distance_meter": 8_400.0,
                        "zone_durations": {
                            "zone_four_milli": 540_000, "zone_five_milli": 120_000
                        },
                    },
                }
            ],
            "next_token": None,
        }

    if path == "/v2/user/profile/basic":
        return {"user_id": 987654, "email": "membre@exemple.fr"}

    return {"records": [], "next_token": None}


whoop._get = fake_get  # noqa: SLF001


with TestClient(app) as client:
    auth = client.post(
        "/auth/register",
        json={
            "email": f"wh{dt.datetime.now().strftime('%H%M%S%f')[:12]}@exemple.fr",
            "password": "motdepasse-tres-long-2026",
        },
    ).json()
    h = {"Authorization": f"Bearer {auth['access_token']}"}
    user_id = auth["user"]["id"]
    print(f"[OK ] compte créé : {auth['user']['email']}")

    # --- Sans configuration, l'intégration est absente et le dit ----------
    state = client.get("/integrations", headers=h).json()["whoop"]
    check(
        "sans identifiants serveur, l'intégration se déclare non configurée",
        state["configure"] is False and state["connecte"] is False,
        "aucun bouton qui mène à une erreur, aucune route qui échoue à moitié",
    )
    check(
        "la limite de la source est dite là où la question se pose",
        "aucune série de fréquence cardiaque" in state["limite"],
        f"« {state['limite'][:120]}… »",
    )
    refused = client.post("/integrations/whoop/authorize", headers=h)
    check(
        "et la connexion est refusée proprement",
        refused.status_code == 503,
        f"HTTP {refused.status_code}",
    )

    # --- Configuration simulée -------------------------------------------
    settings.whoop_client_id = "client-de-test"
    settings.whoop_client_secret = "secret-de-test"
    settings.whoop_redirect_uri = "http://localhost:8000/integrations/whoop/callback"

    url = whoop.authorize_url("etat-123")
    check(
        "l'URL d'autorisation demande le scope offline",
        "offline" in url and "read%3Arecovery" in url and "etat-123" in url,
        "sans `offline`, aucun jeton de rafraîchissement : la connexion mourrait "
        "au bout d'une heure",
    )

    # --- 1 & 2. Jetons chiffrés, rafraîchissement préservé ---------------
    whoop.save_tokens(
        user_id,
        {"access_token": "acces-tres-secret", "refresh_token": "refresh-tres-secret",
         "expires_in": 3600, "scope": " ".join(whoop.SCOPES)},
        provider_user_id="987654",
    )
    row = db.query_one(
        "SELECT access_token, refresh_token FROM oauth_tokens WHERE user_id = %s", (user_id,)
    )
    check(
        "les jetons ne sont jamais en clair en base",
        "acces-tres-secret" not in row["access_token"]
        and "refresh-tres-secret" not in row["refresh_token"],
        f"colonne : {row['access_token'][:28]}… (Fernet, clé dérivée de JWT_SECRET)",
    )

    # Whoop ne renvoie pas toujours un nouveau jeton de rafraîchissement.
    whoop.save_tokens(user_id, {"access_token": "acces-2", "expires_in": 3600, "scope": "offline"})
    after = db.query_one(
        "SELECT refresh_token FROM oauth_tokens WHERE user_id = %s", (user_id,)
    )
    check(
        "un rafraîchissement sans nouveau jeton ne détruit pas l'ancien",
        after["refresh_token"] == row["refresh_token"],
        "sinon la connexion mourrait silencieusement au rafraîchissement suivant",
    )

    # --- Un sommeil déclaré, pour vérifier qu'il n'est pas écrasé ---------
    db.execute(
        """
        INSERT INTO daily_checkins (user_id, entry_date, moment, sleep_hours, sleep_source,
                                    anxiety_0_10)
        VALUES (%s, %s, 'matin', 9.5, 'declare', 4)
        ON CONFLICT (user_id, entry_date, moment) DO NOTHING
        """,
        (user_id, TODAY),
    )

    # --- 3, 4, 5. Synchronisation ----------------------------------------
    CALLS.clear()
    counts = whoop.sync(user_id, days=10)
    check(
        "les quatre ressources sont importées",
        counts == {"recuperations": 2, "sommeils": 1, "cycles": 1, "seances": 1},
        f"{counts}",
    )
    check(
        "la pagination suit next_token",
        sum(1 for path, _ in CALLS if path == "/v2/recovery") == 2
        and any(p.get("nextToken") == "page-2" for path, p in CALLS if path == "/v2/recovery"),
        f"{sum(1 for path, _ in CALLS if path == '/v2/recovery')} appels sur /v2/recovery, "
        "dont un avec le curseur",
    )
    check(
        "la limite de page respecte le plafond de l'API",
        all(p.get("limit") == 25 for _, p in CALLS if "limit" in p),
        "`limit` est plafonné à 25 chez Whoop : demander plus est refusé, pas tronqué",
    )

    day_row = db.query_one(
        """
        SELECT hrv_rmssd_milli, resting_heart_rate, recovery_score, sleep_hours,
               sleep_efficiency, respiratory_rate, strain, max_heart_rate
        FROM wearable_daily WHERE user_id = %s AND entry_date = %s
        """,
        (user_id, TODAY),
    )
    check(
        "récupération, sommeil et cycle atterrissent sur la même ligne de jour",
        day_row is not None
        and float(day_row["hrv_rmssd_milli"]) == 58.0
        and float(day_row["sleep_hours"]) == 5.5
        and float(day_row["strain"]) == 14.2
        and day_row["max_heart_rate"] == 168,
        f"VFC {day_row['hrv_rmssd_milli']} ms · sommeil {day_row['sleep_hours']} h "
        f"(3 + 1,5 + 1 des stades) · strain {day_row['strain']} · FC max {day_row['max_heart_rate']}",
    )
    skipped = db.query_one(
        "SELECT hrv_rmssd_milli FROM wearable_daily WHERE user_id = %s AND entry_date = %s",
        (user_id, TODAY - dt.timedelta(days=1)),
    )
    check(
        "un enregistrement non noté est ignoré, pas écrit avec des valeurs nulles",
        skipped is None,
        "score_state = PENDING_SCORE → aucune ligne créée pour ce jour",
    )
    declared = db.query_one(
        """
        SELECT sleep_hours, sleep_source FROM daily_checkins
        WHERE user_id = %s AND entry_date = %s AND moment = 'matin'
        """,
        (user_id, TODAY),
    )
    check(
        "le capteur n'écrase pas la saisie : deux tables, deux provenances",
        float(declared["sleep_hours"]) == 9.5 and declared["sleep_source"] == "declare",
        f"déclaré {declared['sleep_hours']} h ({declared['sleep_source']}) · "
        f"capteur {day_row['sleep_hours']} h — les deux coexistent, et c'est le but",
    )

    # --- 6. La séance devient testable -----------------------------------
    sessions = whoop.intense_sessions(user_id, TODAY - dt.timedelta(days=3), TODAY)
    check(
        "une séance au-dessus du seuil est retrouvée avec ses zones",
        len(sessions) == 1
        and sessions[0]["max_heart_rate"] == 172
        and "zone_five_milli" in (sessions[0]["zone_durations"] or {}),
        f"{sessions[0]['sport']} · FC max {sessions[0]['max_heart_rate']} · "
        f"zones {list((sessions[0]['zone_durations'] or {}).keys())}",
    )

    # --- 7. Entrée dans les signaux --------------------------------------
    sig = signals_mod.compute(user_id, TODAY, 30, with_days=True)
    by_id = {s["id"]: s for s in sig["signaux"]}
    check(
        "la VFC est traitée comme toute autre source, avec les mêmes seuils",
        "correlation_vfc_anxiete" in by_id
        and str(stats_min := signals_mod.stats.MIN_PAIRS) in by_id["correlation_vfc_anxiete"]["method"],
        f"« {by_id['correlation_vfc_anxiete']['verdict']} » — minimum {stats_min} paires, "
        "correction de multiplicité incluse",
    )
    check(
        "les mesures du bracelet entrent dans les jours agrégés",
        sig["jours"][TODAY]["vfc"] == 58.0
        and sig["jours"][TODAY - dt.timedelta(days=1)]["fc_max_seance"] == 172.0,
        f"VFC du jour {sig['jours'][TODAY]['vfc']} · FC max de la séance d'hier "
        f"{sig['jours'][TODAY - dt.timedelta(days=1)]['fc_max_seance']}",
    )
    check(
        "le volume brut compte les jours et les séances du bracelet",
        sig["brut"]["jours_bracelet"] >= 1 and sig["brut"]["seances_bracelet"] == 1,
        f"{sig['brut']['jours_bracelet']} jour(s), {sig['brut']['seances_bracelet']} séance(s)",
    )
    hypo_labels = [o["hypothese"] for o in by_id["hypotheses"]["observations"]]
    check(
        "les deux hypothèses qui demandaient un capteur sont dans la liste fermée",
        any("variabilité cardiaque basse" in h for h in hypo_labels)
        and any("150 battements" in h for h in hypo_labels),
        "et elles restent pré-enregistrées : aucune fouille automatique n'a été ajoutée",
    )

    # --- L'invite du lendemain, pas une alerte ---------------------------
    from app import chat as chat_mod

    prompt = chat_mod._intense_session_yesterday(user_id)  # noqa: SLF001
    alarm_words = ("risque", "attention", "alerte", "danger", "tu vas")
    check(
        "une séance intense déclenche une question, jamais une alerte",
        prompt is not None
        and "172" in prompt["reply"]
        and "?" in prompt["reply"]
        and not any(word in prompt["reply"].lower() for word in alarm_words),
        f"« {prompt['reply'][:150]}… » — une question, aucun mot d'alarme "
        f"parmi {alarm_words}",
    )
    check(
        "et elle ne se répète pas le même jour",
        chat_mod._intense_session_yesterday(user_id) is None,  # noqa: SLF001
        "marque posée dans le journal des notifications, contrainte d'unicité (compte, type, jour)",
    )

    # --- 8. Webhook non signé refusé -------------------------------------
    body = json.dumps({"user_id": 987654, "type": "recovery.updated"}).encode()
    unsigned = client.post("/integrations/whoop/webhook", content=body)
    check(
        "un webhook non signé est refusé",
        unsigned.status_code == 401,
        f"HTTP {unsigned.status_code} — sinon ce serait un endpoint public capable "
        "d'écrire des données de santé",
    )
    import base64
    import hashlib
    import hmac

    timestamp = "1700000000"
    signature = base64.b64encode(
        hmac.new(b"secret-de-test", timestamp.encode() + body, hashlib.sha256).digest()
    ).decode()
    signed = client.post(
        "/integrations/whoop/webhook",
        content=body,
        headers={"X-WHOOP-Signature": signature, "X-WHOOP-Signature-Timestamp": timestamp},
    )
    check(
        "un webhook correctement signé est accepté et resynchronise",
        signed.status_code == 200 and signed.json()["statut"] == "synchronisé",
        f"{signed.json()} — le corps annonce un changement, la donnée est relue par l'API",
    )

    # --- 9. Révocation avec purge ----------------------------------------
    db.execute(
        """
        INSERT INTO user_chunks (user_id, source_kind, source_id, content, entry_date)
        VALUES (%s, 'wearable', %s, 'Whoop du jour — VFC 58 ms', %s)
        ON CONFLICT (user_id, source_kind, source_id) DO NOTHING
        """,
        (user_id, f"whoop:{TODAY}", TODAY),
    )
    removed = client.delete("/integrations/whoop?purge=true", headers=h).json()["supprime"]
    left = {
        "jetons": db.query_one(
            "SELECT count(*) AS n FROM oauth_tokens WHERE user_id = %s", (user_id,)
        )["n"],
        "jours": db.query_one(
            "SELECT count(*) AS n FROM wearable_daily WHERE user_id = %s", (user_id,)
        )["n"],
        "seances": db.query_one(
            "SELECT count(*) AS n FROM wearable_workouts WHERE user_id = %s", (user_id,)
        )["n"],
        "souvenirs": db.query_one(
            "SELECT count(*) AS n FROM user_chunks WHERE user_id = %s AND source_kind = 'wearable'",
            (user_id,),
        )["n"],
    }
    check(
        "la purge efface les données ET leurs traces en mémoire vectorisée",
        all(v == 0 for v in left.values()) and removed.get("souvenirs", 0) >= 1,
        f"supprimé {removed} · restant {left} — sans la mémoire, la donnée survivrait "
        "dans une table que personne ne penserait à regarder",
    )

print()
if FAILURES:
    print(f"[ERR] {len(FAILURES)} vérification(s) en échec :")
    for name in FAILURES:
        print(f"       - {name}")
    raise SystemExit(1)
print("[OK ] lot 5 : toutes les vérifications passent")
