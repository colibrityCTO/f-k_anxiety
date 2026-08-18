"""Le fil : l'unique écran de l'application.

Quatre routes suffisent :

- `GET  /chat/thread`                 — le fil, l'état du jour, et l'ouverture proactive
- `POST /chat/message`                — texte libre → réponse + widget éventuel
- `POST /chat/widget`                 — l'utilisateur ouvre un widget depuis la grille
- `POST /chat/widget/{item_id}/submit` — il valide un widget : on enregistre la donnée,
  on fige l'item, et on renvoie la relance de l'assistant

Tout ce qui est écrit est aussi mémorisé dans `user_chunks` (en tâche de fond) :
l'historique reste interrogeable indéfiniment.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from .. import analysis, chat as chat_mod, db, memory
from .. import signals as signals_mod
from ..deps import CurrentUser
from . import assessments as assessments_mod

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])

WidgetType = Literal[
    # V1
    "checkin", "breath", "journal", "gad7", "stats", "analysis", "sources", "account", "logout",
    # V2
    "exposition", "meditation", "memoire", "echelles",
    # V3
    "interoceptif", "rapport",
    # V5 — le check-in unique éclaté en trois. `checkin` reste accepté : les items
    # déjà dans le fil gardent leur type, et le passé ne se réécrit pas.
    "matin", "soir", "maintenant",
    # QUICK CHILL : le récapitulatif déposé dans le fil *après* la crise. La séquence
    # elle-même ne passe pas par un widget — elle tourne en plein écran, hors du fil,
    # et sans réseau.
    "panique",
    # Charge du jour et prévision du lendemain.
    "prevision",
]

# Widgets de **consultation** : ils n'écrivent aucune donnée de santé, ils
# affichent. Ce sont des vues, elles n'ont pas d'histoire — les garder dans le fil
# empilait des en-têtes entre l'utilisateur et son dernier message. Ouvrir l'un
# d'eux retire le précédent du même type au lieu de s'ajouter.
#
# `breath`, `meditation` et `interoceptif` n'en font **pas** partie : ils
# enregistrent une anxiété avant/après, donc une donnée.
EPHEMERAL_WIDGETS = frozenset(
    {
        "stats", "analysis", "sources", "memoire", "rapport", "account", "logout",
        "prevision",
    }
)


def _prefill_for(user_id: str, widget_type: str, day: dt.date | None = None) -> dict[str, Any]:
    """Valeurs que le serveur sait déjà, pour ne pas les faire retrouver de mémoire.

    C'est le cœur du découpage : quand la personne a noté son état plusieurs fois
    dans la journée, le pic et la moyenne du soir sont **calculés** au lieu d'être
    reconstruits. Sous anxiété, la mémoire retient les pires moments — une moyenne
    demandée de tête est en réalité un pic mal étiqueté.

    `_derive` liste ce qui vient du serveur, pour que l'écran l'affiche comme tel
    (« calculé sur tes 5 mesures — corrige si c'est faux ») au lieu de le présenter
    comme une saisie de l'utilisateur.

    Le sommeil du matin passera par ici quand un bracelet sera branché : la valeur
    du capteur sera proposée avec `sleep_source = 'capteur'`, et la corriger la
    basculera en `corrige`. Aucune valeur de capteur n'écrase une saisie.
    """
    day = day or dt.date.today()
    prefill: dict[str, Any] = {}
    derived: list[str] = []

    if widget_type == "soir":
        spot = db.query_one(
            """
            SELECT count(*) AS n, max(anxiety_0_10) AS pic,
                   round(avg(anxiety_0_10))::int AS moyenne
            FROM momentary_ratings WHERE user_id = %s AND entry_date = %s
            """,
            (user_id, day),
        )
        if spot and int(spot["n"]) > 0:
            prefill["anxiety_peak_0_10"] = spot["pic"]
            prefill["anxiety_0_10"] = spot["moyenne"]
            derived += ["anxiety_peak_0_10", "anxiety_0_10"]

        panic = db.query_one(
            "SELECT count(*) AS n FROM panic_episodes WHERE user_id = %s AND entry_date = %s",
            (user_id, day),
        )
        if panic and int(panic["n"]) > 0:
            prefill["panic_attacks"] = int(panic["n"])
            derived.append("panic_attacks")

    if derived:
        prefill["_derive"] = derived
    return prefill


def _is_ephemeral(widget_type: str | None, explicit: bool | None = None) -> bool:
    """Éphémère par type, sauf décision contraire explicite de l'appelant.

    Le bilan hebdomadaire est le cas qui impose ce paramètre : c'est un widget
    `analysis`, donc une consultation, mais il est **déposé** par le programme et
    sa présence dans le fil est ce qui empêche de le redéposer chaque jour.
    """
    if explicit is not None:
        return explicit
    return widget_type in EPHEMERAL_WIDGETS


_COLUMNS = """
id::text, seq, role, kind, content, widget_type, payload, saved_values, status,
suggestions, citations, engine, ephemeral, created_at
"""


# --- Écriture d'items -------------------------------------------------------


def _add_item(
    user_id: str,
    role: str,
    *,
    kind: str = "text",
    content: str | None = None,
    widget_type: str | None = None,
    payload: dict[str, Any] | None = None,
    saved_values: dict[str, Any] | None = None,
    status: str | None = None,
    suggestions: list[str] | None = None,
    citations: list[dict[str, Any]] | None = None,
    engine: str | None = None,
    ephemeral: bool = False,
) -> dict[str, Any]:
    row = db.execute_returning(
        f"""
        INSERT INTO thread_items
            (user_id, role, kind, content, widget_type, payload, saved_values, status,
             suggestions, citations, engine, ephemeral)
        VALUES (%(user_id)s, %(role)s, %(kind)s, %(content)s, %(widget_type)s, %(payload)s,
                %(saved_values)s, %(status)s, %(suggestions)s, %(citations)s, %(engine)s,
                %(ephemeral)s)
        RETURNING {_COLUMNS}
        """,
        {
            "user_id": user_id,
            "role": role,
            "kind": kind,
            "content": content,
            "widget_type": widget_type,
            "payload": json.dumps(payload or {}, ensure_ascii=False, default=str),
            "saved_values": json.dumps(saved_values or {}, ensure_ascii=False, default=str),
            "status": status,
            "suggestions": json.dumps(suggestions or [], ensure_ascii=False),
            "citations": json.dumps(citations or [], ensure_ascii=False, default=str),
            "engine": engine,
            "ephemeral": ephemeral,
        },
    )
    assert row is not None
    return row


def _retire_ephemeral(user_id: str) -> list[str]:
    """Retire toutes les vues en cours, et renvoie leurs identifiants.

    Tous types confondus, et c'est voulu : on ne consulte pas ses chiffres et ses
    sources en même temps. L'invariant tenu est donc **au plus une vue dans le
    fil**, ce qui est la seule garantie qui empêche l'encombrement de revenir.

    Suppression et non changement de statut : un widget de consultation ne
    contient aucune donnée — `saved_values` est vide par construction, et la
    clause `WHERE` le vérifie au lieu de le supposer. Il n'y a rien à archiver.
    Les identifiants remontent au front pour qu'il retire de son propre état les
    lignes qu'il a déjà affichées.
    """
    rows = db.execute_all_returning(
        """
        DELETE FROM thread_items
        WHERE user_id = %s AND kind = 'widget'
          AND ephemeral AND status = 'ouvert' AND saved_values = '{}'::jsonb
        RETURNING id::text
        """,
        (user_id,),
    )
    return [r["id"] for r in rows]


def _items_from_decision(
    user_id: str, decision: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[str]]:
    """Transforme une décision de l'orchestrateur en items du fil.

    Renvoie les items créés **et** les identifiants des vues retirées, que le
    front doit enlever de son propre état.
    """
    items: list[dict[str, Any]] = []
    retired: list[str] = []
    if decision.get("reply"):
        items.append(
            _add_item(
                user_id,
                "assistant",
                content=decision["reply"],
                suggestions=decision.get("suggestions"),
                citations=decision.get("citations"),
                engine=decision.get("engine"),
            )
        )
    widget = decision.get("widget")
    if widget:
        ephemeral = _is_ephemeral(widget["type"], widget.get("ephemeral"))
        if ephemeral:
            retired += _retire_ephemeral(user_id)
        # Le calculé complète la proposition du modèle sans jamais l'écraser : si le
        # message parlait d'un chiffre lu dans la phrase, c'est celui-là qui compte.
        computed = _prefill_for(user_id, widget["type"])
        merged = {**computed, **(widget.get("prefill") or {})}
        if computed.get("_derive"):
            merged["_derive"] = [k for k in computed["_derive"] if k not in (widget.get("prefill") or {})]
        items.append(
            _add_item(
                user_id,
                "assistant",
                kind="widget",
                widget_type=widget["type"],
                payload={
                    "prefill": merged,
                    "a_verifier": widget.get("a_verifier") or [],
                },
                status="ouvert",
                ephemeral=ephemeral,
            )
        )
    return items, retired


def _maybe_weekly_analysis(user_id: str) -> None:
    """Pousse le bilan hebdomadaire dans le fil, au plus une fois tous les 7 jours.

    On dépose une **proposition** (message + widget d'analyse réglé sur 4 semaines)
    au lieu de lancer l'analyse d'office : générer coûte un appel au modèle et
    quelques secondes, et rien ne justifie de le faire sans que tu l'aies demandé.
    Un clic suffit. La régularité, elle, ne dépend plus de toi.
    """
    today = dt.date.today()

    days_logged = db.query_one(
        "SELECT count(DISTINCT entry_date) AS n FROM daily_checkins WHERE user_id = %s",
        (user_id,),
    )
    if not days_logged or int(days_logged["n"]) < 10:
        return  # en dessous de 10 jours, un bilan hebdomadaire ne dit rien

    last = db.query_one(
        """
        SELECT max(created_at)::date AS jour FROM insights
        WHERE user_id = %s AND scope = 'hebdomadaire'
        """,
        (user_id,),
    )
    proposed = db.query_one(
        """
        SELECT max(created_at)::date AS jour FROM thread_items
        WHERE user_id = %s AND widget_type = 'analysis'
          AND payload->'prefill'->>'scope' = 'hebdomadaire'
        """,
        (user_id,),
    )
    for row in (last, proposed):
        if row and row["jour"] and (today - row["jour"]).days < 7:
            return

    _items_from_decision(
        user_id,
        {
            "reply": (
                "Bilan de la semaine. Je regarde les 4 dernières semaines : ce que les chiffres "
                "montrent, ce qui a été fait, ce qui ne l'a pas été et pourquoi."
            ),
            "widget": {
                "type": "analysis",
                "prefill": {"scope": "hebdomadaire"},
                "a_verifier": [],
                # Durable, contrairement aux autres widgets d'analyse : c'est sa
                # présence dans le fil qui empêche de redéposer le bilan demain.
                "ephemeral": False,
            },
            "suggestions": ["Plus tard"],
            "engine": "local",
        },
    )


def _expire_stale_widgets(user_id: str, today: dt.date) -> list[dict[str, Any]]:
    """Périme les widgets de saisie ouverts dont la journée est passée.

    Un check-in proposé il y a douze jours et jamais validé n'est plus remplissable :
    il porte la date de ce jour-là. Le laisser « ouvert » accumulait des formulaires
    morts dans le fil — l'inspection d'un compte réel en comptait vingt-sept.

    `perime` et non `remplace` : rien ne l'a remplacé, la journée est simplement
    passée. Et surtout pas `reporte`, qui est une réponse de l'utilisateur (« pas
    maintenant », avec sa raison) et donc une donnée : la déduire automatiquement
    serait inventer une réponse qu'il n'a pas donnée.

    Non destructif, et borné aux widgets vides : la clause vérifie
    `saved_values = '{}'` au lieu de la supposer.
    """
    return db.execute_all_returning(
        f"""
        UPDATE thread_items SET status = 'perime'
        WHERE user_id = %s AND kind = 'widget' AND NOT ephemeral
          AND status = 'ouvert' AND saved_values = '{{}}'::jsonb
          AND created_at::date < %s
        RETURNING {_COLUMNS}
        """,
        (user_id, today),
    )


# --- Lecture du fil ---------------------------------------------------------


@router.get("/thread")
def get_thread(
    user: CurrentUser,
    limit: int = 50,
    before: int | None = None,
) -> dict[str, Any]:
    """Une page du fil, l'état du jour, et l'ouverture du jour.

    L'ouverture est créée une seule fois par jour : si aucun item d'assistant
    n'existe pour aujourd'hui, on l'ajoute. Aucune donnée n'est jamais purgée.

    Deux bornes, pour deux raisons distinctes :

    - `limit` / `before` paginent. Le fil est fait pour durer des années ; le
      renvoyer en entier à chaque ouverture finit par coûter des mégaoctets et des
      secondes. `before` est un `seq`, exclusif : on remonte avec le `seq` du plus
      ancien item déjà affiché.
    - les **vues** (`ephemeral`) sont écartées sauf la plus récente. Consulter ses
      chiffres n'est pas un événement de l'historique, et trois en-têtes « Mes
      chiffres » entre l'utilisateur et son dernier message rendaient le fil
      pénible à parcourir.

    `before` n'est honoré que pour remonter : la première page déclenche
    l'ouverture du jour, les suivantes ne doivent rien créer.
    """
    user_id = user["id"]
    today = dt.date.today()

    if before is None:
        already = db.query_one(
            """
            SELECT 1 FROM thread_items
            WHERE user_id = %s AND role = 'assistant' AND created_at::date = %s
            LIMIT 1
            """,
            (user_id, today),
        )
        if already is None:
            # Ménage avant d'écrire : sinon l'ouverture du jour arrive derrière une
            # pile de formulaires de la semaine dernière.
            _expire_stale_widgets(user_id, today)
            _items_from_decision(user_id, chat_mod.opening(user))
            _maybe_weekly_analysis(user_id)

    limit = max(1, min(limit, 200))
    rows = db.query_all(
        f"""
        SELECT {_COLUMNS} FROM thread_items
        WHERE user_id = %(uid)s
          AND (%(before)s::bigint IS NULL OR seq < %(before)s::bigint)
          AND (
              NOT ephemeral
              OR seq = (
                  SELECT max(seq) FROM thread_items
                  WHERE user_id = %(uid)s AND ephemeral
              )
          )
        ORDER BY seq DESC LIMIT %(limit)s
        """,
        {"uid": user_id, "before": before, "limit": limit},
    )
    total = db.query_one(
        "SELECT count(*) AS n FROM thread_items WHERE user_id = %s AND NOT ephemeral",
        (user_id,),
    )

    payload: dict[str, Any] = {
        "items": list(reversed(rows)),
        "total": int(total["n"]) if total else 0,
        # Le front a besoin de savoir s'il reste quelque chose au-dessus, sans avoir
        # à comparer `limit` au nombre de lignes reçues — ce qui serait faux dès que
        # le filtre des vues en écarte une.
        "has_more": len(rows) == limit,
        "oldest_seq": rows[-1]["seq"] if rows else None,
    }
    if before is None:
        payload["state"] = chat_mod.day_state(user_id, today)
        payload["memoire"] = memory.stats(user_id)
    return payload


# --- Message libre ----------------------------------------------------------


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


@router.post("/message")
async def post_message(
    payload: MessageIn, user: CurrentUser, background: BackgroundTasks
) -> dict[str, Any]:
    user_id = user["id"]
    text = payload.text.strip()

    user_item = await asyncio.to_thread(_add_item, user_id, "user", content=text)
    background.add_task(
        memory.remember,
        user_id,
        "message",
        user_item["id"],
        memory.render_message("user", text, dt.date.today()),
        dt.date.today(),
        {"role": "user"},
    )

    decision = await chat_mod.respond(user, text)
    items, retired = await asyncio.to_thread(_items_from_decision, user_id, decision)

    if decision.get("reply"):
        background.add_task(
            memory.remember,
            user_id,
            "message",
            items[0]["id"],
            memory.render_message("assistant", decision["reply"], dt.date.today()),
            dt.date.today(),
            {"role": "assistant", "engine": decision.get("engine")},
        )

    return {
        "items": [user_item, *items],
        "retired": retired,
        "risk": decision.get("risk", False),
    }


@router.post("/message/stream")
async def post_message_stream(payload: MessageIn, user: CurrentUser) -> EventSourceResponse:
    """Même chose, en streaming SSE : la prose arrive au fur et à mesure.

    Événements émis : `item` (le message de l'utilisateur, tout de suite),
    `engine`, `token` (fragments de prose), `items` (les items définitifs créés
    en base), `done`. Le pied structuré du modèle n'est jamais diffusé.

    Les tâches de fond (mémoire) ne sont pas disponibles dans une réponse
    streamée : on les exécute ici dans un thread, une fois la réponse close.
    """
    user_id = user["id"]
    text = payload.text.strip()

    async def events():
        user_item = await asyncio.to_thread(_add_item, user_id, "user", content=text)
        yield {"event": "item", "data": json.dumps(user_item, ensure_ascii=False, default=str)}

        decision: dict[str, Any] = {}
        try:
            async for kind, value in chat_mod.respond_stream(user, text):
                if kind == "token":
                    yield {"event": "token", "data": value}
                elif kind == "engine":
                    yield {"event": "engine", "data": value}
                elif kind == "decision":
                    decision = value
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("Erreur pendant le streaming du fil")
            yield {"event": "error", "data": f"Erreur interne : {exc}"}

        if decision:
            items, retired = await asyncio.to_thread(_items_from_decision, user_id, decision)
            if retired:
                yield {"event": "retired", "data": json.dumps(retired)}
            yield {
                "event": "items",
                "data": json.dumps(items, ensure_ascii=False, default=str),
            }
            today = dt.date.today()
            await asyncio.to_thread(
                memory.remember, user_id, "message", user_item["id"],
                memory.render_message("user", text, today), today, {"role": "user"},
            )
            if items and decision.get("reply"):
                await asyncio.to_thread(
                    memory.remember, user_id, "message", items[0]["id"],
                    memory.render_message("assistant", decision["reply"], today), today,
                    {"role": "assistant", "engine": decision.get("engine")},
                )
        yield {"event": "done", "data": json.dumps({"risk": bool(decision.get("risk"))})}

    return EventSourceResponse(events())


# --- Ouverture d'un widget depuis la grille --------------------------------


class WidgetOpenIn(BaseModel):
    type: WidgetType
    prefill: dict[str, Any] = Field(default_factory=dict)
    # Le libellé de la tuile, pour que le fil garde la trace de l'intention.
    label: str | None = Field(default=None, max_length=40)


@router.post("/widget")
def open_widget(payload: WidgetOpenIn, user: CurrentUser) -> dict[str, Any]:
    """L'utilisateur lance un widget lui-même : il apparaît dans le fil.

    Deux régimes. Un widget de **saisie** s'annonce par un message (« Check-in »)
    et reste : c'est le registre. Un widget de **consultation** n'annonce rien et
    remplace le précédent du même type — son en-tête dit déjà ce qu'il est, et
    un doublon n'apporterait qu'une ligne de plus à faire défiler.
    """
    user_id = user["id"]
    ephemeral = _is_ephemeral(payload.type)
    retired = _retire_ephemeral(user_id) if ephemeral else []

    items: list[dict[str, Any]] = []
    if payload.label and not ephemeral:
        items.append(_add_item(user_id, "user", content=payload.label))
    items.append(
        _add_item(
            user_id,
            "assistant",
            kind="widget",
            widget_type=payload.type,
            payload={
                "prefill": {**_prefill_for(user_id, payload.type), **payload.prefill},
                "a_verifier": [],
            },
            status="ouvert",
            ephemeral=ephemeral,
        )
    )
    return {"items": items, "retired": retired}


# --- Validation d'un widget -------------------------------------------------


def _freeze(
    item_id: str, user_id: str, saved: dict[str, Any], status: str = "valide"
) -> list[dict[str, Any]]:
    """Fige un widget, et clôt les autres widgets du même type restés ouverts.

    Sans ça, le fil garderait deux check-in ouverts le même jour : celui de
    l'ouverture proactive et celui proposé après un message libre. Le second
    validé, le premier n'a plus de sens — il est marqué « remplacé », jamais
    supprimé.
    """
    row = db.execute_returning(
        f"""
        UPDATE thread_items
        -- Un widget qui a produit une donnée n'est plus une vue : il rejoint le
        -- registre, et le registre ne s'efface pas.
        SET saved_values = %s, status = %s, ephemeral = false
        WHERE id = %s AND user_id = %s AND kind = 'widget'
        RETURNING {_COLUMNS}
        """,
        (json.dumps(saved, ensure_ascii=False, default=str), status, item_id, user_id),
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Widget introuvable dans ton fil.")

    # `execute_all_returning` et non `query_all` : ce dernier ne valide pas la
    # transaction. Ce passage à « remplacé » était donc perdu à chaque validation,
    # ce qui laissait s'accumuler les widgets ouverts jamais remplis.
    superseded = db.execute_all_returning(
        f"""
        UPDATE thread_items SET status = 'remplace'
        WHERE user_id = %s AND kind = 'widget' AND widget_type = %s
          AND status = 'ouvert' AND id <> %s
        RETURNING {_COLUMNS}
        """,
        (user_id, row["widget_type"], item_id),
    )
    return [row, *superseded]


class SubmitIn(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)


@router.post("/widget/{item_id}/submit")
async def submit_widget(
    item_id: str,
    payload: SubmitIn,
    user: CurrentUser,
    background: BackgroundTasks,
) -> dict[str, Any]:
    """Enregistre la donnée du widget, fige l'item, renvoie la relance.

    Un seul aller-retour côté client : la donnée métier est écrite, la mémoire
    vectorielle alimentée, le widget figé, et l'assistant réagit avec les
    chiffres réels — pas avec ce que le client prétend avoir envoyé.
    """
    user_id = user["id"]
    item = db.query_one(
        "SELECT id::text, widget_type, status FROM thread_items WHERE id = %s AND user_id = %s",
        (item_id, user_id),
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Widget introuvable dans ton fil.")
    if item["status"] == "valide":
        raise HTTPException(status_code=409, detail="Ce widget est déjà validé.")

    widget_type = item["widget_type"]
    handler = _HANDLERS.get(widget_type)
    if handler is None:
        raise HTTPException(status_code=422, detail=f"Widget « {widget_type} » non enregistrable.")

    saved, follow_up = await handler(user, payload.values or {}, background)
    frozen = await asyncio.to_thread(_freeze, item_id, user_id, saved)
    items, retired = await asyncio.to_thread(_items_from_decision, user_id, follow_up)
    return {"items": [*frozen, *items], "retired": retired}


@router.post("/widget/{item_id}/skip")
def skip_widget(item_id: str, user: CurrentUser) -> dict[str, Any]:
    """« Pas maintenant » : le widget est reporté, et c'est une donnée, pas un échec."""
    frozen = _freeze(item_id, user["id"], {}, status="reporte")
    follow_up = {
        "reply": (
            "Noté comme non fait, sans jugement — c'est une donnée utile. Qu'est-ce qui a bloqué : "
            "trop long, mauvais moment, ou pas envie ?"
        ),
        "widget": None,
        "suggestions": ["Trop long", "Mauvais moment", "Pas envie"],
        "engine": "local",
    }
    items, retired = _items_from_decision(user["id"], follow_up)
    return {"items": [*frozen, *items], "retired": retired}


# --- QUICK CHILL ------------------------------------------------------------


def _panic_bilan(user_id: str) -> dict[str, Any]:
    """L'agrégat du log d'attaque : la preuve rétrospective, en chiffres.

    C'est la finalité que le programme 12 semaines donne à ce log — « au bout de
    trois mois, ceci devient votre preuve principale : l'anxiété passe toujours, la
    catastrophe n'a pas eu lieu ». Un log qu'on ne rend jamais en agrégat ne prouve
    rien : il faut pouvoir lire les quatorze épisodes d'un coup.

    Deux précautions sur l'honnêteté du chiffre :

    - « la catastrophe n'est pas arrivée » n'est **pas** déduit du texte libre.
      L'application ne peut pas juger d'une phrase, et prétendre le faire serait
      inventer. Le compte s'appuie sur `feared_outcome_happened`, que l'utilisateur
      renseigne lui-même.
    - la durée médiane est préférée à la moyenne : un épisode de trois heures mal
      noté déplacerait la moyenne et rendrait le chiffre inutilisable.
    """
    rows = db.query_all(
        """
        SELECT entry_date, anxiety_peak, anxiety_after, time_to_relief_min,
               what_actually_happened, feared_outcome_happened, tools_used
        FROM panic_episodes WHERE user_id = %s ORDER BY started_at DESC
        """,
        (user_id,),
    )
    durations = sorted(r["time_to_relief_min"] for r in rows if r["time_to_relief_min"] is not None)
    median = None
    if durations:
        middle = len(durations) // 2
        median = (
            durations[middle]
            if len(durations) % 2
            else round((durations[middle - 1] + durations[middle]) / 2, 1)
        )

    answered = [r for r in rows if r["feared_outcome_happened"] is not None]
    happened = [r for r in answered if r["feared_outcome_happened"]]

    # Quels outils reviennent, et dans quel ordre ils ont été employés.
    tool_counts: dict[str, int] = {}
    for row in rows:
        for entry in row["tools_used"] or []:
            slug = entry.get("slug") if isinstance(entry, dict) else str(entry)
            if slug:
                tool_counts[slug] = tool_counts.get(slug, 0) + 1

    return {
        "episodes": len(rows),
        "tous_termines": bool(rows) and all(r["time_to_relief_min"] is not None for r in rows),
        "duree_mediane_min": median,
        "duree_max_min": durations[-1] if durations else None,
        "redoute_renseigne": len(answered),
        "redoute_arrive": len(happened),
        "outils": sorted(tool_counts.items(), key=lambda kv: -kv[1]),
        "derniers": [
            {
                "date": str(r["entry_date"]),
                "pic": r["anxiety_peak"],
                "apres": r["anxiety_after"],
                "minutes": r["time_to_relief_min"],
                "ce_qui_est_arrive": r["what_actually_happened"],
                "redoute_arrive": r["feared_outcome_happened"],
            }
            for r in rows[:10]
        ],
        # La phrase est composée ici, pas côté front : c'est un fait construit sur des
        # comptes, et il ne doit pas dépendre d'une reformulation par un modèle.
        "phrase": _bilan_sentence(len(rows), median, len(answered), len(happened)),
    }


def _bilan_sentence(total: int, median: Any, answered: int, happened: int) -> str | None:
    if total == 0:
        return None
    bits = [f"**{total} épisode(s)** enregistré(s)."]
    if median is not None:
        bits.append(f"Durée médiane avant que ça redescende : **{median} min**.")
    if answered:
        if happened == 0:
            bits.append(
                f"Sur les {answered} fois où tu as répondu, ce que tu redoutais est arrivé "
                "**0 fois**."
            )
        else:
            bits.append(
                f"Sur les {answered} fois où tu as répondu, ce que tu redoutais est arrivé "
                f"**{happened} fois**."
            )
    return " ".join(bits)


def _usage_last_week(user_id: str) -> int:
    row = db.query_one(
        """
        SELECT count(*) AS n FROM panic_episodes
        WHERE user_id = %s AND started_at > now() - interval '7 days'
        """,
        (user_id,),
    )
    return int(row["n"]) if row else 0


@router.get("/panique")
def quickchill_context(user: CurrentUser) -> dict[str, Any]:
    """Tout ce dont l'écran de crise a besoin — récupéré **avant** la crise.

    Appelé au chargement de l'application, pas au moment du pic : en crise, il n'y a
    peut-être pas de réseau, et il ne doit surtout pas y avoir d'attente. Le contenu
    est de toute façon dans le bundle ; cette route ne sert qu'à l'état personnel
    (porte du froid validée ou non, bilan, compteur d'usage).
    """
    from ..data import quickchill

    profile = user.get("profile") or {}
    usage = _usage_last_week(user["id"])
    return {
        "cadrage": quickchill.FRAMING,
        "zones": quickchill.BODY_AREAS,
        "pensees": quickchill.THOUGHTS,
        "outils": quickchill.TOOLS,
        "sources": quickchill.SOURCES,
        "froid_valide_le": profile.get("froid_valide_le"),
        "bilan": _panic_bilan(user["id"]),
        "usage_7j": usage,
        "seuil_usage": quickchill.USAGE_ALERT_PER_WEEK,
        "alerte_usage": _usage_alert(user["id"], usage),
    }


def _usage_alert(user_id: str, usage: int) -> str | None:
    """Le garde-fou anti-comportement de sécurité, rendu mesurable.

    Deux conditions, et il faut les deux : beaucoup d'usages **et** un GAD-7 qui ne
    bouge pas au-delà de sa DMCI. Beaucoup d'usages tout seul peut simplement
    signifier une mauvaise semaine — le dire serait un reproche, pas une observation.
    """
    from ..data import quickchill

    if usage < quickchill.USAGE_ALERT_PER_WEEK:
        return None
    gad = db.query_all(
        """
        SELECT total FROM assessments
        WHERE user_id = %s AND instrument = 'gad7' ORDER BY taken_on DESC LIMIT 2
        """,
        (user_id,),
    )
    if len(gad) < 2 or abs(gad[0]["total"] - gad[1]["total"]) >= signals_mod.GAD7_MCID:
        return None
    return (
        f"Tu l'as ouvert **{usage} fois cette semaine**, et ton GAD-7 n'a pas bougé "
        f"au-delà du seuil de signification ({gad[0]['total']} après {gad[1]['total']}). "
        "Ça peut vouloir dire que cet écran est devenu ce qui te rassure, plutôt que ce "
        "qui te fait apprendre. L'exposition intéroceptive travaille l'inverse : "
        "provoquer les sensations pour découvrir qu'elles ne sont pas dangereuses."
    )


class PanicToolIn(BaseModel):
    slug: str = Field(max_length=40)
    seconds: int | None = Field(default=None, ge=0, le=3600)


class PanicIn(BaseModel):
    """Un épisode, tel que l'écran de crise le renvoie une fois la crise passée."""

    entry_date: dt.date | None = None
    what_preceded: str | None = Field(default=None, max_length=1000)
    body_symptoms: list[str] = Field(default_factory=list)
    thought_in_moment: str | None = Field(default=None, max_length=1000)
    tools_used: list[PanicToolIn] = Field(default_factory=list)
    anxiety_before: int | None = Field(default=None, ge=0, le=10)
    anxiety_peak: int | None = Field(default=None, ge=0, le=10)
    anxiety_after: int | None = Field(default=None, ge=0, le=10)
    time_to_relief_min: int | None = Field(default=None, ge=0, le=1440)
    what_actually_happened: str | None = Field(default=None, max_length=2000)
    feared_outcome_happened: bool | None = None
    # Porte du froid : cochée une fois, datée dans le profil. Sans elle, l'API refuse
    # d'enregistrer un épisode qui déclare avoir utilisé le froid.
    confirm_cold_contraindications: bool = False


@router.post("/panique")
async def record_panic(
    payload: PanicIn, user: CurrentUser, background: BackgroundTasks
) -> dict[str, Any]:
    """Enregistre un épisode, et dépose son récapitulatif dans le fil.

    Appelé **après** la crise, jamais pendant : la séquence tourne entièrement côté
    client, sans réseau, et n'envoie qu'une fois terminée. Si l'envoi échoue (métro,
    avion), le front garde l'épisode et le rejoue plus tard — d'où l'importance que
    cette route soit idempotente du point de vue de l'utilisateur : deux envois du
    même épisode créent deux lignes, donc c'est au front de ne pas rejouer deux fois.
    """
    from ..data import quickchill

    user_id = user["id"]
    day = _resolve_entry_date(payload.entry_date)
    slugs = [t.slug for t in payload.tools_used if t.slug in quickchill.TOOLS_BY_SLUG]

    profile = dict(user.get("profile") or {})
    if payload.confirm_cold_contraindications:
        profile["froid_valide_le"] = str(dt.date.today())
        await asyncio.to_thread(
            db.execute,
            "UPDATE users SET profile = %s WHERE id = %s",
            (json.dumps(profile, ensure_ascii=False), user_id),
        )
    if quickchill.COLD_GATE_SLUG in slugs and not profile.get("froid_valide_le"):
        raise HTTPException(
            status_code=422,
            detail=(
                "Le froid a ses contre-indications : trouble du rythme, maladie du cœur, "
                "trouble alimentaire, Raynaud, hypertension non contrôlée. Confirme "
                "qu'aucune ne te concerne avant de l'enregistrer."
            ),
        )

    row = await asyncio.to_thread(
        db.execute_returning,
        """
        INSERT INTO panic_episodes
            (user_id, entry_date, ended_at, what_preceded, body_symptoms,
             thought_in_moment, tools_used, anxiety_before, anxiety_peak, anxiety_after,
             time_to_relief_min, what_actually_happened, feared_outcome_happened)
        VALUES (%(user_id)s, %(entry_date)s, now(), %(what_preceded)s, %(body_symptoms)s,
                %(thought_in_moment)s, %(tools_used)s, %(anxiety_before)s, %(anxiety_peak)s,
                %(anxiety_after)s, %(time_to_relief_min)s, %(what_actually_happened)s,
                %(feared_outcome_happened)s)
        RETURNING id::text, entry_date, anxiety_before, anxiety_peak, anxiety_after,
                  time_to_relief_min, what_actually_happened, feared_outcome_happened
        """,
        {
            "user_id": user_id,
            "entry_date": day,
            "what_preceded": payload.what_preceded,
            "body_symptoms": payload.body_symptoms[:12],
            "thought_in_moment": payload.thought_in_moment,
            "tools_used": json.dumps(
                [{"slug": t.slug, "secondes": t.seconds} for t in payload.tools_used],
                ensure_ascii=False,
            ),
            "anxiety_before": payload.anxiety_before,
            "anxiety_peak": payload.anxiety_peak,
            "anxiety_after": payload.anxiety_after,
            "time_to_relief_min": payload.time_to_relief_min,
            "what_actually_happened": payload.what_actually_happened,
            "feared_outcome_happened": payload.feared_outcome_happened,
        },
    )
    assert row is not None

    # Le compteur du jour suit les épisodes déclarés : c'est lui qui alimente le
    # check-in du soir, en lecture seule.
    await asyncio.to_thread(
        db.execute,
        """
        INSERT INTO daily_checkins (user_id, entry_date, moment, panic_attacks)
        VALUES (%s, %s, 'soir', 1)
        ON CONFLICT (user_id, entry_date, moment)
        DO UPDATE SET panic_attacks = daily_checkins.panic_attacks + 1, updated_at = now()
        """,
        (user_id, day),
    )

    bilan = await asyncio.to_thread(_panic_bilan, user_id)
    tools_label = ", ".join(quickchill.TOOLS_BY_SLUG[s]["name"] for s in slugs) or "—"
    saved = {
        "pic": row["anxiety_peak"],
        "apres": row["anxiety_after"],
        "minutes": row["time_to_relief_min"],
        "outils": tools_label,
        "redoute_arrive": row["feared_outcome_happened"],
        "bilan": bilan["phrase"],
    }

    items = [
        _add_item(
            user_id, "assistant", kind="widget", widget_type="panique",
            saved_values=saved, status="valide",
        )
    ]
    reply = "C'est passé, et c'est noté."
    if row["time_to_relief_min"] is not None:
        reply = f"C'est passé en **{row['time_to_relief_min']} min**, et c'est noté."
    if bilan["phrase"] and bilan["episodes"] > 1:
        reply += f"\n\n{bilan['phrase']}"
    alert = await asyncio.to_thread(_usage_alert, user_id, _usage_last_week(user_id))
    if alert:
        reply += f"\n\n{alert}"
    items.append(
        _add_item(
            user_id, "assistant", content=reply, engine="local",
            suggestions=["Mes chiffres"] + (["Les sensations"] if alert else []),
        )
    )

    rendered = (
        f"Épisode de panique du {day} — pic {row['anxiety_peak']}/10, "
        f"après {row['anxiety_after']}/10, passé en {row['time_to_relief_min']} min. "
        f"Outils : {tools_label}."
    )
    if payload.what_preceded:
        rendered += f" Ce qui a précédé : {payload.what_preceded}."
    if payload.thought_in_moment:
        rendered += f" Pensée sur le moment : {payload.thought_in_moment}."
    if payload.what_actually_happened:
        rendered += f" Ce qui s'est réellement passé : {payload.what_actually_happened}."
    background.add_task(
        memory.remember, user_id, "panique", row["id"], rendered, day, {"pic": row["anxiety_peak"]}
    )

    return {"episode": dict(row), "bilan": bilan, "items": items}


# --- Charge du jour et prévision --------------------------------------------


def _forecast_bundle(user_id: str, today: dt.date) -> dict[str, Any]:
    """Tout ce que l'écran de prévision affiche, calculé d'un seul jet.

    Un seul appel à `signals.compute` : il porte déjà les corrélations retenues, dont
    la pondération de la charge et le choix des prédicteurs dépendent. Recalculer
    séparément coûterait cher pour un résultat identique.
    """
    from .. import forecast as forecast_mod

    sig = signals_mod.compute(user_id, today, 120, with_days=True)
    days = sig.pop("jours")
    anxiety = {d: r["anxiete"] for d, r in days.items() if r.get("anxiete") is not None}

    charge = forecast_mod.load_index(days, sig, today)
    prediction = forecast_mod.predict(days, sig, today)
    return {
        "date": str(today),
        "anxiete_declaree": anxiety.get(today),
        "charge": charge,
        "prevision": (
            None
            if prediction is None
            else {**prediction, "target_date": str(prediction["target_date"])}
        ),
        # Le bilan des prévisions passées : c'est la contrepartie de « jamais réécrite ».
        # Un modèle dont on ne montre pas les échecs est une décoration.
        "historique": forecast_mod.track_record(user_id, anxiety),
    }


@router.get("/prevision")
def forecast_view(user: CurrentUser) -> dict[str, Any]:
    return _forecast_bundle(user["id"], dt.date.today())


def _store_forecast(user_id: str, today: dt.date) -> dict[str, Any] | None:
    """Pose la prévision du lendemain, une fois la journée renseignée.

    Appelée après la validation du soir : avant, l'anxiété du jour n'est pas connue et
    la persistance n'a rien à reporter. L'écriture est idempotente côté base.
    """
    from .. import forecast as forecast_mod

    sig = signals_mod.compute(user_id, today, 120, with_days=True)
    days = sig.pop("jours")
    prediction = forecast_mod.predict(days, sig, today)
    if prediction is not None:
        forecast_mod.store(user_id, prediction)
    return prediction


# --- Enregistrement par type de widget -------------------------------------


def _resolve_entry_date(raw: Any) -> dt.date:
    """Date de saisie : aujourd'hui par défaut, jamais dans le futur, 60 jours en arrière au plus.

    Au-delà de 60 jours, le souvenir est trop reconstruit pour être exploitable dans
    une corrélation — mieux vaut ne pas l'inventer.
    """
    today = dt.date.today()
    if not raw:
        return today
    try:
        day = dt.date.fromisoformat(str(raw))
    except ValueError:
        raise HTTPException(status_code=422, detail="Date illisible (format attendu AAAA-MM-JJ).") from None
    if day > today:
        raise HTTPException(status_code=422, detail="On ne renseigne pas une date future.")
    if day < today - dt.timedelta(days=60):
        raise HTTPException(
            status_code=422,
            detail="Saisie rétroactive limitée à 60 jours : au-delà, le souvenir est trop reconstruit.",
        )
    return day


async def _submit_checkin(
    user: dict[str, Any], values: dict[str, Any], background: BackgroundTasks
) -> tuple[dict[str, Any], dict[str, Any]]:
    from .checkins import _UPSERT

    user_id = user["id"]
    today = _resolve_entry_date(values.get("entry_date"))
    data = {
        "user_id": user_id,
        "entry_date": today,
        "moment": "soir",
        "anxiety_0_10": values.get("anxiety_0_10"),
        # Les deux colonnes du découpage V5. L'ancien écran ne les demande pas, mais
        # `_UPSERT` les attend : un paramètre nommé manquant est une erreur, pas un
        # NULL implicite.
        "anxiety_peak_0_10": values.get("anxiety_peak_0_10"),
        "mood_0_10": values.get("mood_0_10"),
        "sleep_hours": values.get("sleep_hours"),
        "sleep_quality_0_10": values.get("sleep_quality_0_10"),
        "sleep_source": values.get("sleep_source"),
        "bed_time": None,
        "wake_time": None,
        "caffeine_units": values.get("caffeine_units"),
        "alcohol_units": values.get("alcohol_units"),
        "exercise_min": values.get("exercise_min"),
        "panic_attacks": values.get("panic_attacks") or 0,
        "avoidance_0_10": values.get("avoidance_0_10"),
        "contexts": values.get("contexts") or [],
        "main_trigger": values.get("main_trigger"),
        "note": values.get("note"),
    }
    row = await asyncio.to_thread(db.execute_returning, _UPSERT, data)
    assert row is not None
    await asyncio.to_thread(
        db.execute,
        """
        INSERT INTO activity_logs (user_id, activity_slug, entry_date, status)
        VALUES (%s, 'checkin-quotidien', %s, 'fait')
        ON CONFLICT (user_id, activity_slug, entry_date) DO UPDATE SET status = 'fait'
        """,
        (user_id, today),
    )
    background.add_task(
        memory.remember, user_id, "checkin", row["id"],
        memory.render_checkin({**row, "entry_date": today}), today, {"moment": "soir"},
    )

    follow_up = await _comment_on_checkin(user, row)
    return dict(row), follow_up


async def _comment_on_checkin(user: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    """Commentaire après check-in : bâti sur les signaux, pas sur une impression."""
    sig = await asyncio.to_thread(signals_mod.compute, user["id"], dt.date.today(), 60)
    anxiety = row.get("anxiety_0_10")
    bits: list[str] = []
    if anxiety is not None:
        bits.append(f"Noté : anxiété **{anxiety}/10**.")

    by_id = {s["id"]: s for s in sig["signaux"]}
    sleep = by_id.get("correlation_sommeil_anxiete", {})
    trend = by_id.get("tendance_anxiete", {})
    effect = by_id.get("effet_mesure_activites", {})

    suggestions = ["Mes chiffres", "Respirer 5 min"]
    if sleep.get("value") is not None and sleep["value"] <= -0.4:
        bits.append(
            f"Sur tes {sleep['n']} nuits enregistrées, tes nuits courtes sont suivies d'une "
            f"anxiété plus haute le lendemain — corrélation **{sleep['value']}**. "
            "Association, pas causalité."
        )
    elif trend.get("delta") is not None:
        direction = "en baisse" if trend["delta"] < 0 else "en hausse" if trend["delta"] > 0 else "stable"
        bits.append(
            f"Moyenne des 7 derniers jours : **{trend['value']}/10**, {direction} de "
            f"**{abs(trend['delta'])}** point par rapport aux 7 précédents."
        )
    elif effect.get("value"):
        best = effect["value"][0]
        bits.append(
            f"Ce qui marche le mieux chez toi pour l'instant : `{best['activite']}`, "
            f"**{best['delta_moyen']}** point d'anxiété en moyenne sur {best['n']} mesures."
        )
    else:
        bits.append(
            "Il faut encore quelques jours pour que les corrélations deviennent lisibles — "
            "6 paires de jours minimum par signal."
        )

    return {
        "reply": " ".join(bits),
        "widget": None,
        "suggestions": suggestions,
        "engine": "local",
    }


async def _submit_journal(
    user: dict[str, Any], values: dict[str, Any], background: BackgroundTasks
) -> tuple[dict[str, Any], dict[str, Any]]:
    user_id = user["id"]
    today = dt.date.today()
    kind = values.get("kind") or "libre"
    data = {
        "user_id": user_id,
        "entry_date": today,
        "kind": kind,
        "situation": values.get("situation"),
        "emotions": values.get("emotions") or [],
        "body_sensations": values.get("body_sensations") or [],
        "intensity_before": values.get("intensity_before"),
        "intensity_after": values.get("intensity_after"),
        "automatic_thought": values.get("automatic_thought"),
        "thinking_trap": values.get("thinking_trap"),
        "evidence_for": values.get("evidence_for"),
        "evidence_against": values.get("evidence_against"),
        "coping_plan": values.get("coping_plan"),
        "alternative_thought": values.get("alternative_thought"),
        "prediction": None,
        "prediction_probability": None,
        "actual_outcome": None,
        "learning": None,
        "safety_behaviors_dropped": [],
        "worry_text": None,
        "worry_actionable": None,
        "next_action": None,
        "free_text": values.get("free_text"),
    }
    # Correction d'une entrée passée : on modifie, on ne duplique pas. La date
    # d'origine est conservée — corriger le texte d'hier ne le déplace pas à
    # aujourd'hui, sinon la chronologie devient fausse.
    edit_id = values.get("edit_id")
    if edit_id:
        existing = await asyncio.to_thread(
            db.query_one,
            "SELECT entry_date FROM journal_entries WHERE id = %s AND user_id = %s",
            (edit_id, user_id),
        )
        if existing is None:
            raise HTTPException(status_code=404, detail="Entrée introuvable dans ton journal.")
        data["entry_date"] = existing["entry_date"]
        data["id"] = edit_id
        row = await asyncio.to_thread(
            db.execute_returning,
            """
            UPDATE journal_entries SET
                kind = %(kind)s, situation = %(situation)s, emotions = %(emotions)s,
                body_sensations = %(body_sensations)s, intensity_before = %(intensity_before)s,
                intensity_after = %(intensity_after)s, automatic_thought = %(automatic_thought)s,
                thinking_trap = %(thinking_trap)s, evidence_for = %(evidence_for)s,
                evidence_against = %(evidence_against)s, coping_plan = %(coping_plan)s,
                alternative_thought = %(alternative_thought)s, free_text = %(free_text)s,
                updated_at = now()
            WHERE id = %(id)s AND user_id = %(user_id)s
            RETURNING id::text, entry_date, kind
            """,
            data,
        )
    else:
        row = await asyncio.to_thread(
            db.execute_returning,
            """
            INSERT INTO journal_entries
                (user_id, entry_date, kind, situation, emotions, body_sensations,
                 intensity_before, intensity_after, automatic_thought, thinking_trap,
                 evidence_for, evidence_against, coping_plan, alternative_thought,
                 prediction, prediction_probability, actual_outcome, learning,
                 safety_behaviors_dropped, worry_text, worry_actionable, next_action, free_text)
            VALUES (%(user_id)s, %(entry_date)s, %(kind)s, %(situation)s, %(emotions)s,
                    %(body_sensations)s, %(intensity_before)s, %(intensity_after)s,
                    %(automatic_thought)s, %(thinking_trap)s, %(evidence_for)s, %(evidence_against)s,
                    %(coping_plan)s, %(alternative_thought)s, %(prediction)s,
                    %(prediction_probability)s, %(actual_outcome)s, %(learning)s,
                    %(safety_behaviors_dropped)s, %(worry_text)s, %(worry_actionable)s,
                    %(next_action)s, %(free_text)s)
            RETURNING id::text, entry_date, kind
            """,
            data,
        )
    assert row is not None
    today = row["entry_date"]
    row = {**row, "apercu": (data["free_text"] or data["situation"] or "")[:120]}
    slug = "journal-pensees" if kind == "pensee" else "journal-libre"
    await asyncio.to_thread(
        db.execute,
        """
        INSERT INTO activity_logs (user_id, activity_slug, entry_date, status)
        VALUES (%s, %s, %s, 'fait')
        ON CONFLICT (user_id, activity_slug, entry_date) DO UPDATE SET status = 'fait'
        """,
        (user_id, slug, today),
    )
    background.add_task(
        memory.remember, user_id, "journal", row["id"],
        memory.render_journal({**data, "entry_date": today}), today, {"kind": kind},
    )

    if edit_id:
        reply = (
            f"Entrée du **{today}** corrigée. La date d'origine est conservée : corriger un texte "
            "ne le déplace pas à aujourd'hui, sinon la chronologie devient fausse. La mémoire est "
            "réindexée avec la nouvelle version."
        )
    elif (
        kind == "pensee"
        and values.get("intensity_before") is not None
        and values.get("intensity_after") is not None
    ):
        delta = values["intensity_before"] - values["intensity_after"]
        reply = (
            f"Enregistré. Intensité passée de **{values['intensity_before']}** à "
            f"**{values['intensity_after']}** — {delta:+d} point. C'est ta donnée de résultat : "
            "elle dira si la restructuration marche chez toi."
        )
    else:
        reply = "Enregistré. C'est le matériau sur lequel je repère tes schémas récurrents."
    return dict(row), {"reply": reply, "widget": None, "suggestions": [], "engine": "local"}


async def _submit_scale(
    user: dict[str, Any], values: dict[str, Any], background: BackgroundTasks
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Toute échelle : GAD-7, PHQ-2, évitement. Un seul chemin, une seule validation.

    Le commentaire est bâti sur la différence minimale cliniquement importante de
    l'instrument quand elle existe — et sur son absence quand elle n'existe pas.
    """
    instrument = str(values.get("instrument") or "gad7")
    meta = assessments_mod.INSTRUMENTS.get(instrument)
    if meta is None:
        raise HTTPException(status_code=404, detail="Instrument inconnu.")

    items = values.get("items")
    expected = len(meta["items"])
    if not isinstance(items, list) or len(items) != expected or any(
        not isinstance(i, int) or i < 0 or i > 3 for i in items
    ):
        raise HTTPException(
            status_code=422,
            detail=f"{meta['title']} attend {expected} réponses de 0 à 3.",
        )

    user_id = user["id"]
    today = dt.date.today()
    total = sum(items)
    severity = assessments_mod._severity(instrument, total)
    mcid = meta["scoring"]["mcid"]
    maximum = meta["scoring"]["range"][1]

    previous = await asyncio.to_thread(
        db.query_one,
        """
        SELECT total, taken_on FROM assessments
        WHERE user_id = %s AND instrument = %s AND taken_on < %s
        ORDER BY taken_on DESC LIMIT 1
        """,
        (user_id, instrument, today),
    )
    row = await asyncio.to_thread(
        db.execute_returning,
        """
        INSERT INTO assessments (user_id, instrument, taken_on, items, total, severity)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (user_id, instrument, taken_on) DO UPDATE SET
            items = EXCLUDED.items, total = EXCLUDED.total, severity = EXCLUDED.severity
        RETURNING id::text, instrument, taken_on, items, total, severity
        """,
        (user_id, instrument, today, items, total, severity),
    )
    assert row is not None
    background.add_task(
        memory.remember, user_id, "assessment", row["id"],
        memory.render_assessment(row), today, {"instrument": instrument, "total": total},
    )

    bits = [f"**{total} / {maximum}** — {severity}."]
    if previous is None:
        bits.append("Première mesure : elle sert de référence, il n'y a rien à en conclure encore.")
    else:
        delta = total - previous["total"]
        if mcid is None:
            bits.append(
                f"Écart de **{delta:+d}** avec le {previous['taken_on']}. Aucune DMCI publiée pour "
                "cette échelle : regarde la tendance sur plusieurs mesures, pas un écart isolé."
            )
        elif delta <= -mcid:
            bits.append(
                f"Baisse de **{abs(delta)} points** depuis le {previous['taken_on']} : amélioration "
                f"**cliniquement significative** (le seuil est de {mcid})."
            )
        elif delta >= mcid:
            bits.append(
                f"Hausse de **{delta} points** depuis le {previous['taken_on']} : c'est significatif. "
                "Si ça se confirme la semaine prochaine, parles-en à un professionnel."
            )
        else:
            bits.append(
                f"Écart de **{delta:+d}** point avec le {previous['taken_on']} : sous le seuil de "
                f"{mcid}, donc du bruit de mesure. Je te félicite pas pour du bruit."
            )

    if instrument == "gad7" and total >= 15:
        bits.append(
            "À ce niveau, les recommandations NICE prévoient une TCC accompagnée par un "
            "professionnel. Cette application seule ne suffit pas."
        )
    if instrument == "phq2" and total >= 3:
        bits.append(
            "Dépistage dépressif positif. À évoquer avec un médecin ou un psychologue : ça change "
            "la prise en charge indiquée, et ce n'est pas à moi d'en juger."
        )
    if instrument == "avoidance" and total >= 9:
        bits.append(
            "L'évitement est haut : c'est le mécanisme central du maintien de l'anxiété, et donc la "
            "cible la plus rentable. C'est le moment de travailler ton échelle d'expositions."
        )

    suggestions = ["Mes chiffres"]
    if instrument == "avoidance" and total >= 6:
        suggestions.insert(0, "Mes expositions")
    return dict(row), {
        "reply": " ".join(bits),
        "widget": None,
        "suggestions": suggestions,
        "engine": "local",
    }


async def _submit_breath(
    user: dict[str, Any], values: dict[str, Any], background: BackgroundTasks
) -> tuple[dict[str, Any], dict[str, Any]]:
    user_id = user["id"]
    today = dt.date.today()
    before, after = values.get("anxiety_before"), values.get("anxiety_after")
    row = await asyncio.to_thread(
        db.execute_returning,
        """
        INSERT INTO activity_logs
            (user_id, activity_slug, entry_date, status, duration_min, anxiety_before, anxiety_after)
        VALUES (%s, 'respiration-lente-10', %s, %s, %s, %s, %s)
        ON CONFLICT (user_id, activity_slug, entry_date) DO UPDATE SET
            status = EXCLUDED.status, duration_min = EXCLUDED.duration_min,
            anxiety_before = EXCLUDED.anxiety_before, anxiety_after = EXCLUDED.anxiety_after
        RETURNING id::text, activity_slug, entry_date, status, anxiety_before, anxiety_after
        """,
        (user_id, today, values.get("status") or "fait", values.get("duration_min"), before, after),
    )
    assert row is not None
    background.add_task(
        memory.remember, user_id, "activity", row["id"],
        memory.render_activity({**row, "title": "Respiration lente"}), today,
        {"slug": "respiration-lente-10"},
    )

    if before is not None and after is not None:
        reply = (
            f"Séance faite, anxiété **{before} → {after}**. Une séance ne prouve rien : "
            "je calculerai la moyenne à partir de 3 mesures."
        )
    else:
        reply = "Séance faite."
    return dict(row), {"reply": reply, "widget": None, "suggestions": [], "engine": "local"}


async def _submit_analysis(
    user: dict[str, Any], values: dict[str, Any], background: BackgroundTasks
) -> tuple[dict[str, Any], dict[str, Any]]:
    """L'analyse n'est pas une saisie : « valider » signifie « lance-la »."""
    scope = "hebdomadaire" if values.get("scope") == "hebdomadaire" else "quotidien"
    result = await analysis.analyze(user, scope=scope)
    background.add_task(
        memory.remember, user["id"], "insight", result["id"],
        memory.render_insight(result), dt.date.today(), {"scope": scope},
    )
    # Le corps complet part dans le fil : une analyse enfermée dans un widget
    # replié ne serait jamais lue.
    body = f"**{result['headline']}**\n\n{result['body']}" if result.get("headline") else result["body"]
    return (
        {"insight_id": result["id"], "scope": scope},
        {
            "reply": body,
            "widget": None,
            "suggestions": ["Voir les sources", "Mes chiffres"],
            "citations": result["citations"],
            "engine": result["engine"],
        },
    )


async def _submit_exposition(
    user: dict[str, Any], values: dict[str, Any], background: BackgroundTasks
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Deux modes : ajouter un item à l'échelle, ou enregistrer une tentative.

    Une tentative crée aussi une entrée de journal de type « exposition » : c'est
    elle qui alimente le signal d'écart prédiction / réalité. Sans ça, l'exposition
    serait invisible dans l'analyse.
    """
    user_id = user["id"]
    today = dt.date.today()
    mode = values.get("mode") or "attempt"

    if mode == "add":
        label = str(values.get("label") or "").strip()
        if not label:
            raise HTTPException(status_code=422, detail="Décris ce que tu évites, en une phrase.")
        row = await asyncio.to_thread(
            db.execute_returning,
            """
            INSERT INTO exposure_items (user_id, label, kind, anticipated_anxiety, safety_behaviors)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id::text, label, kind, anticipated_anxiety, safety_behaviors
            """,
            (
                user_id,
                label[:300],
                values.get("kind") or "in_vivo",
                values.get("anticipated_anxiety"),
                values.get("safety_behaviors") or [],
            ),
        )
        assert row is not None
        background.add_task(
            memory.remember, user_id, "activity", f"expo-item-{row['id']}",
            f"Item ajouté à l'échelle d'expositions le {today} : « {label} » "
            f"({row['kind']}, anxiété anticipée {row['anticipated_anxiety']}/10).",
            today, {"kind": "exposure_item"},
        )
        anticipated = row.get("anticipated_anxiety")
        if anticipated is not None and 4 <= anticipated <= 6:
            comment = "C'est exactement la bonne zone pour commencer : 4 à 6 sur 10."
        elif anticipated is not None and anticipated > 6:
            comment = (
                "C'est haut pour un début. Garde-le pour plus tard et commence par un item à "
                "4-6/10 — plus bas n'apprend rien, plus haut fait fuir."
            )
        else:
            comment = "Trop facile pour apprendre quelque chose, mais utile pour s'échauffer."
        return dict(row), {
            "reply": f"Ajouté à ton échelle. {comment}",
            "widget": None,
            "suggestions": ["Mes expositions"],
            "engine": "local",
        }

    # --- Enregistrement d'une tentative -------------------------------------
    item_id = values.get("item_id")
    if not item_id:
        raise HTTPException(status_code=422, detail="Quelle exposition as-tu tentée ?")
    prediction = str(values.get("prediction") or "").strip()
    outcome = str(values.get("actual_outcome") or "").strip()
    if not prediction and not outcome:
        raise HTTPException(
            status_code=422,
            detail=(
                "Il faut au moins la prédiction ou le résultat réel : c'est l'écart entre les deux "
                "qui produit l'apprentissage."
            ),
        )

    mastered = bool(values.get("mastered"))
    learning = str(values.get("learning") or "").strip()
    item = await asyncio.to_thread(
        db.execute_returning,
        """
        UPDATE exposure_items
        SET attempts = attempts + 1,
            last_attempt_on = %s,
            best_learning = COALESCE(NULLIF(%s, ''), best_learning),
            mastered = %s OR mastered
        WHERE id = %s AND user_id = %s
        RETURNING id::text, label, kind, attempts, anticipated_anxiety, mastered, best_learning
        """,
        (today, learning, mastered, item_id, user_id),
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Item introuvable dans ton échelle.")

    journal = await asyncio.to_thread(
        db.execute_returning,
        """
        INSERT INTO journal_entries
            (user_id, entry_date, kind, situation, prediction, prediction_probability,
             actual_outcome, learning, intensity_before, intensity_after,
             safety_behaviors_dropped, emotions, body_sensations)
        VALUES (%s, %s, 'exposition', %s, %s, %s, %s, %s, %s, %s, %s, '{}', '{}')
        RETURNING id::text
        """,
        (
            user_id, today, item["label"], prediction or None,
            values.get("prediction_probability"), outcome or None, learning or None,
            values.get("anxiety_max"), values.get("anxiety_after"),
            values.get("safety_behaviors_dropped") or [],
        ),
    )
    await asyncio.to_thread(
        db.execute,
        """
        INSERT INTO activity_logs (user_id, activity_slug, entry_date, status, notes)
        VALUES (%s, %s, %s, 'fait', %s)
        ON CONFLICT (user_id, activity_slug, entry_date) DO UPDATE SET
            status = 'fait', notes = EXCLUDED.notes
        """,
        (
            user_id,
            "exposition-interoceptive" if item["kind"] == "interoceptif" else "exposition-in-vivo",
            today,
            item["label"],
        ),
    )
    if journal is not None:
        background.add_task(
            memory.remember, user_id, "journal", journal["id"],
            memory.render_journal(
                {
                    "entry_date": today, "kind": "exposition", "situation": item["label"],
                    "prediction": prediction, "prediction_probability": values.get("prediction_probability"),
                    "actual_outcome": outcome, "learning": learning,
                    "intensity_before": values.get("anxiety_max"),
                    "intensity_after": values.get("anxiety_after"),
                    "safety_behaviors_dropped": values.get("safety_behaviors_dropped") or [],
                }
            ),
            today, {"kind": "exposition"},
        )

    bits = [f"Exposition **{item['attempts']}** sur « {item['label']} », enregistrée."]
    probability = values.get("prediction_probability")
    if probability is not None and outcome:
        bits.append(
            f"Tu donnais **{probability} %** au scénario redouté. Ce qui est arrivé : {outcome}"
        )
    if learning:
        bits.append(f"Ce que t'as appris : « {learning} »")
    if item["attempts"] < 3 and not item["mastered"]:
        bits.append(
            "Refais le même item 3 à 5 fois, en variant lieu, heure et personnes, avant de monter "
            "d'un cran : la variabilité contextuelle est l'un des deux leviers dont l'effet est "
            "démontré."
        )
    elif item["mastered"]:
        bits.append("Marqué comme maîtrisé. Passe à l'item suivant de ton échelle.")

    return dict(item), {
        "reply": " ".join(bits),
        "widget": None,
        "suggestions": ["Mes expositions", "Mes chiffres"],
        "engine": "local",
    }


MEDITATIONS = {
    "meditation-souffle": "Conscience du souffle",
    "scan-corporel": "Scan corporel",
    "conscience-emotionnelle": "Conscience émotionnelle",
    "relaxation-musculaire": "Relaxation musculaire progressive",
}


async def _submit_meditation(
    user: dict[str, Any], values: dict[str, Any], background: BackgroundTasks
) -> tuple[dict[str, Any], dict[str, Any]]:
    slug = str(values.get("slug") or "meditation-souffle")
    if slug not in MEDITATIONS:
        raise HTTPException(status_code=422, detail="Pratique inconnue.")

    user_id = user["id"]
    today = dt.date.today()
    before, after = values.get("anxiety_before"), values.get("anxiety_after")
    row = await asyncio.to_thread(
        db.execute_returning,
        """
        INSERT INTO activity_logs
            (user_id, activity_slug, entry_date, status, duration_min, anxiety_before, anxiety_after, notes)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (user_id, activity_slug, entry_date) DO UPDATE SET
            status = EXCLUDED.status, duration_min = EXCLUDED.duration_min,
            anxiety_before = EXCLUDED.anxiety_before, anxiety_after = EXCLUDED.anxiety_after,
            notes = EXCLUDED.notes
        RETURNING id::text, activity_slug, entry_date, status, duration_min,
                  anxiety_before, anxiety_after
        """,
        (
            user_id, slug, today, values.get("status") or "fait", values.get("duration_min"),
            before, after, values.get("notes"),
        ),
    )
    assert row is not None
    background.add_task(
        memory.remember, user_id, "activity", row["id"],
        memory.render_activity({**row, "title": MEDITATIONS[slug]}), today, {"slug": slug},
    )

    bits = [f"{MEDITATIONS[slug]} : séance enregistrée."]
    if before is not None and after is not None:
        bits.append(f"Anxiété **{before} → {after}**.")
    if slug == "scan-corporel":
        bits.append(
            "Si l'anxiété est montée pendant le scan, c'est fréquent et transitoire — raccourcis la "
            "séance plutôt que d'arrêter."
        )
    return dict(row), {"reply": " ".join(bits), "widget": None, "suggestions": [], "engine": "local"}


async def _submit_interoceptif(
    user: dict[str, Any], values: dict[str, Any], background: BackgroundTasks
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Exposition intéroceptive : un exercice, une prédiction, un constat.

    La porte de contre-indications est validée une fois et datée dans le profil.
    Sans elle, rien n'est enregistré : ces exercices ne créent aucun danger chez
    une personne en bonne santé physique, mais la vérification n'est pas
    négociable — c'est aussi ce qui rend l'exercice crédible.
    """
    from ..data import interoceptive

    user_id = user["id"]
    today = dt.date.today()
    profile = dict(user.get("profile") or {})

    if values.get("confirm_contraindications"):
        profile["interoceptif_valide_le"] = str(today)
        await asyncio.to_thread(
            db.execute,
            "UPDATE users SET profile = %s WHERE id = %s",
            (json.dumps(profile, ensure_ascii=False), user_id),
        )

    if not profile.get("interoceptif_valide_le"):
        raise HTTPException(
            status_code=422,
            detail=(
                "Confirme d'abord que tu n'as aucune des contre-indications, ou que ton médecin "
                "a donné son accord."
            ),
        )

    slug = str(values.get("slug") or "")
    exercise = interoceptive.EXERCISES_BY_SLUG.get(slug)
    if exercise is None:
        raise HTTPException(status_code=422, detail="Exercice inconnu.")

    prediction = str(values.get("prediction") or "").strip()
    outcome = str(values.get("actual_outcome") or "").strip()
    if not prediction and not outcome:
        raise HTTPException(
            status_code=422,
            detail="Il faut au moins la prédiction ou le résultat réel : c'est l'écart qui apprend.",
        )

    journal = await asyncio.to_thread(
        db.execute_returning,
        """
        INSERT INTO journal_entries
            (user_id, entry_date, kind, situation, prediction, prediction_probability,
             actual_outcome, learning, intensity_before, intensity_after, body_sensations,
             emotions, safety_behaviors_dropped)
        VALUES (%s, %s, 'exposition', %s, %s, %s, %s, %s, %s, %s, %s, '{}', '{}')
        RETURNING id::text
        """,
        (
            user_id, today, f"Exposition intéroceptive — {exercise['name']}",
            prediction or None, values.get("prediction_probability"), outcome or None,
            values.get("learning") or None, values.get("anxiety_max"), values.get("anxiety_after"),
            exercise["sensations"],
        ),
    )
    row = await asyncio.to_thread(
        db.execute_returning,
        """
        INSERT INTO activity_logs
            (user_id, activity_slug, entry_date, status, duration_min, anxiety_before,
             anxiety_after, notes)
        VALUES (%s, 'exposition-interoceptive', %s, 'fait', %s, %s, %s, %s)
        ON CONFLICT (user_id, activity_slug, entry_date) DO UPDATE SET
            status = 'fait', anxiety_before = EXCLUDED.anxiety_before,
            anxiety_after = EXCLUDED.anxiety_after, notes = EXCLUDED.notes
        RETURNING id::text, activity_slug, entry_date, status, anxiety_before, anxiety_after
        """,
        (
            user_id, today, max(1, round(exercise["seconds"] / 60)),
            values.get("anxiety_max"), values.get("anxiety_after"),
            f"{exercise['name']} · répétition {values.get('repetition') or 1}",
        ),
    )
    assert row is not None
    if journal is not None:
        background.add_task(
            memory.remember, user_id, "journal", journal["id"],
            memory.render_journal(
                {
                    "entry_date": today, "kind": "exposition",
                    "situation": f"Exposition intéroceptive — {exercise['name']}",
                    "prediction": prediction, "prediction_probability": values.get("prediction_probability"),
                    "actual_outcome": outcome, "learning": values.get("learning"),
                    "intensity_before": values.get("anxiety_max"),
                    "intensity_after": values.get("anxiety_after"),
                    "body_sensations": exercise["sensations"],
                }
            ),
            today, {"kind": "interoceptif", "exercice": slug},
        )

    # Combien de fois cet exercice a déjà été fait : la répétition est le levier.
    done = await asyncio.to_thread(
        db.query_one,
        """
        SELECT count(*) AS n FROM journal_entries
        WHERE user_id = %s AND kind = 'exposition' AND situation = %s
        """,
        (user_id, f"Exposition intéroceptive — {exercise['name']}"),
    )
    repetitions = int(done["n"]) if done else 1

    bits = [f"{exercise['name']} — répétition **{repetitions}**, enregistrée."]
    probability = values.get("prediction_probability")
    if probability is not None and outcome:
        bits.append(f"Tu donnais **{probability} %** au scénario redouté. Ce qui est arrivé : {outcome}")
    before, after = values.get("anxiety_max"), values.get("anxiety_after")
    if before is not None and after is not None:
        bits.append(f"Anxiété **{before} → {after}**.")
    if repetitions < 3:
        bits.append(
            "Refais le même exercice, plusieurs jours de suite : c'est la répétition qui fait "
            "tomber l'anxiété initiale, pas une séance isolée."
        )
    else:
        bits.append(
            f"**{repetitions} répétitions** sur cet exercice. Si l'anxiété initiale a nettement "
            "baissé, passe à un exercice qui vise d'autres sensations."
        )

    return dict(row), {
        "reply": " ".join(bits),
        "widget": None,
        "suggestions": ["Mes chiffres", "Encore une répétition"],
        "engine": "local",
    }


async def _submit_matin(
    user: dict[str, Any], values: dict[str, Any], background: BackgroundTasks
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Le matin : ce que la nuit a produit, et où il en est là.

    Trois choses seulement, et c'est délibéré : la compliance baisse avec le nombre
    d'items, pas avec le nombre de moments. Un écran de trente secondes tenu tous
    les jours vaut mieux qu'un formulaire complet rempli deux fois par semaine.
    """
    from .checkins import _UPSERT

    user_id = user["id"]
    day = _resolve_entry_date(values.get("entry_date"))
    sleep_hours = values.get("sleep_hours")
    data = {
        "user_id": user_id, "entry_date": day, "moment": "matin",
        # « Comment tu te sens là » : c'est bien l'anxiété du moment, pas celle de
        # la journée — la journée n'a pas commencé.
        "anxiety_0_10": values.get("anxiety_0_10"),
        "anxiety_peak_0_10": None,
        "mood_0_10": values.get("mood_0_10"),
        "sleep_hours": sleep_hours,
        "sleep_quality_0_10": values.get("sleep_quality_0_10"),
        "sleep_source": values.get("sleep_source") or ("declare" if sleep_hours is not None else None),
        "bed_time": None, "wake_time": None,
        "caffeine_units": None, "alcohol_units": None, "exercise_min": None,
        "panic_attacks": 0, "avoidance_0_10": None,
        "contexts": values.get("contexts") or [],
        # Le premier trou de la phrase du matin : ce qu'il redoute aujourd'hui.
        "main_trigger": values.get("main_trigger"),
        "note": values.get("note"),
    }
    row = await asyncio.to_thread(db.execute_returning, _UPSERT, data)
    assert row is not None

    # « Aujourd'hui j'ai peur de ___. Aujourd'hui je vais faire ___ malgré ça. »
    # Les deux trous dans une seule phrase : l'appréhension et l'action engagée. Le
    # second est déjà de l'acceptation — agir malgré, plutôt qu'attendre que ça passe.
    intention = str(values.get("intention") or "").strip()
    fear = str(values.get("main_trigger") or "").strip()
    if intention or fear:
        text = (
            f"Aujourd'hui j'ai peur de {fear or '—'}. "
            f"Aujourd'hui je vais faire {intention or '—'} malgré ça."
        )
        entry = await asyncio.to_thread(
            db.execute_returning,
            """
            INSERT INTO journal_entries (user_id, entry_date, kind, free_text)
            VALUES (%s, %s, 'libre', %s) RETURNING id::text
            """,
            (user_id, day, text),
        )
        if entry:
            background.add_task(
                memory.remember, user_id, "journal", entry["id"],
                f"Intention du {day} — {text}", day, {"kind": "intention"},
            )

    await asyncio.to_thread(_log_activity, user_id, "checkin-quotidien", day)
    background.add_task(
        memory.remember, user_id, "checkin", row["id"],
        memory.render_checkin({**row, "entry_date": day}), day, {"moment": "matin"},
    )

    bits = []
    if sleep_hours is not None:
        bits.append(f"**{float(sleep_hours):.1f} h** de sommeil noté.")
    if values.get("anxiety_0_10") is not None:
        bits.append(f"Anxiété **{values['anxiety_0_10']}/10** là, maintenant.")
    if intention:
        bits.append(f"Et l'intention du jour : {intention}.")
    return dict(row), {
        "reply": " ".join(bits) or "Noté.",
        "widget": None,
        "suggestions": ["Comment je me sens là", "Respirer 5 min", "Mes chiffres"],
        "engine": "local",
    }


async def _submit_soir(
    user: dict[str, Any], values: dict[str, Any], background: BackgroundTasks
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Le soir : la journée écoulée, une fois qu'elle est finie.

    Le compteur de paniques n'est **pas** saisi ici. Il est dérivé de
    `panic_episodes` : une crise se déclare au moment où elle arrive, pas douze
    heures plus tard de mémoire. Tant qu'aucun épisode n'a été déclaré, la valeur
    envoyée par l'écran est acceptée — sinon il n'y aurait aucun moyen de la noter
    avant que le mode d'urgence n'existe.
    """
    from .checkins import _UPSERT

    user_id = user["id"]
    day = _resolve_entry_date(values.get("entry_date"))

    declared = await asyncio.to_thread(
        db.query_one,
        "SELECT count(*) AS n FROM panic_episodes WHERE user_id = %s AND entry_date = %s",
        (user_id, day),
    )
    episodes = int(declared["n"]) if declared else 0
    panic = episodes if episodes else int(values.get("panic_attacks") or 0)

    data = {
        "user_id": user_id, "entry_date": day, "moment": "soir",
        "anxiety_0_10": values.get("anxiety_0_10"),
        "anxiety_peak_0_10": values.get("anxiety_peak_0_10"),
        "mood_0_10": values.get("mood_0_10"),
        "sleep_hours": None, "sleep_quality_0_10": None, "sleep_source": None,
        "bed_time": None, "wake_time": None,
        "caffeine_units": values.get("caffeine_units"),
        "alcohol_units": values.get("alcohol_units"),
        "exercise_min": values.get("exercise_min"),
        "panic_attacks": panic,
        "avoidance_0_10": values.get("avoidance_0_10"),
        "contexts": values.get("contexts") or [],
        "main_trigger": values.get("main_trigger"),
        "note": values.get("note"),
    }
    row = await asyncio.to_thread(db.execute_returning, _UPSERT, data)
    assert row is not None
    await asyncio.to_thread(_log_activity, user_id, "checkin-quotidien", day)
    background.add_task(
        memory.remember, user_id, "checkin", row["id"],
        memory.render_checkin({**row, "entry_date": day}), day, {"moment": "soir"},
    )
    follow_up = await _comment_on_checkin(user, row)

    # La prévision du lendemain est posée maintenant : la journée est renseignée, donc
    # la persistance a quelque chose à reporter. Écrite une fois, jamais réécrite.
    prediction = await asyncio.to_thread(_store_forecast, user_id, day)
    if prediction is not None:
        follow_up["reply"] = f"{follow_up['reply']}\n\n{prediction['phrase']}"
        follow_up.setdefault("suggestions", [])
        if "Ma prévision" not in follow_up["suggestions"]:
            follow_up["suggestions"] = [*follow_up["suggestions"][:2], "Ma prévision"]

    return dict(row), follow_up


async def _submit_maintenant(
    user: dict[str, Any], values: dict[str, Any], background: BackgroundTasks
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Une mesure instantanée. Un curseur, et rien d'autre.

    Un item unique 0-10 est défendable pour l'instant présent : il corrèle autour
    de 0,70 avec la sous-échelle anxiété du HADS. Réserve à connaître et à ne pas
    masquer : sur un item unique on ne peut pas calculer de cohérence interne —
    c'est un signal exploitable, pas un score psychométrique.

    Aucun commentaire de l'application en retour, volontairement. Chez certains, la
    consultation répétée de ses propres notes devient elle-même le symptôme ; y
    répondre à chaque fois par une analyse entraînerait exactement ça.
    """
    user_id = user["id"]
    anxiety = values.get("anxiety_0_10")
    if anxiety is None:
        raise HTTPException(status_code=422, detail="Il manque le chiffre : 0 à 10.")

    contexts = [str(c)[:60] for c in (values.get("contexts") or [])][:6]
    note = str(values.get("note") or "").strip() or None
    row = await asyncio.to_thread(
        db.execute_returning,
        """
        INSERT INTO momentary_ratings (user_id, anxiety_0_10, contexts, note)
        VALUES (%s, %s, %s, %s)
        RETURNING id::text, rated_at, entry_date, anxiety_0_10, contexts, note
        """,
        (user_id, int(anxiety), contexts, note),
    )
    assert row is not None

    # En mémoire vectorisée **seulement** s'il y a du texte. Les chiffres sont
    # recalculés par `signals.py` sur l'historique entier : les embedder ne servirait
    # à rien et polluerait la recherche sémantique avec des lignes interchangeables.
    if note or contexts:
        when = row["rated_at"].strftime("%H:%M")
        rendered = f"Mesure du {row['entry_date']} à {when} — anxiété {anxiety}/10"
        if contexts:
            rendered += " · " + ", ".join(contexts)
        if note:
            rendered += f". {note}"
        background.add_task(
            memory.remember, user_id, "momentary", row["id"], rendered,
            row["entry_date"], {"heure": when},
        )

    same_day = await asyncio.to_thread(
        db.query_one,
        """
        SELECT count(*) AS n, max(anxiety_0_10) AS pic, round(avg(anxiety_0_10), 1) AS moyenne
        FROM momentary_ratings WHERE user_id = %s AND entry_date = %s
        """,
        (user_id, row["entry_date"]),
    )
    count = int(same_day["n"]) if same_day else 1
    reply = f"**{anxiety}/10**, noté."
    if count > 1:
        reply += (
            f" {count}\u00a0mesures aujourd'hui — pic **{same_day['pic']}**, "
            f"moyenne **{same_day['moyenne']}**. Ce sont ces deux chiffres que je te "
            "proposerai ce soir, au lieu de te les faire retrouver de mémoire."
        )
    return dict(row), {
        "reply": reply, "widget": None, "suggestions": [], "engine": "local",
    }


def _log_activity(user_id: str, slug: str, day: dt.date) -> None:
    """Marque une activité du programme comme faite pour ce jour-là."""
    db.execute(
        """
        INSERT INTO activity_logs (user_id, activity_slug, entry_date, status)
        VALUES (%s, %s, %s, 'fait')
        ON CONFLICT (user_id, activity_slug, entry_date) DO UPDATE SET status = 'fait'
        """,
        (user_id, slug, day),
    )


_HANDLERS = {
    # V1
    "checkin": _submit_checkin,
    "journal": _submit_journal,
    "gad7": _submit_scale,
    "breath": _submit_breath,
    "analysis": _submit_analysis,
    # V2
    "echelles": _submit_scale,
    "exposition": _submit_exposition,
    "meditation": _submit_meditation,
    # V3
    "interoceptif": _submit_interoceptif,
    # V5
    "matin": _submit_matin,
    "soir": _submit_soir,
    "maintenant": _submit_maintenant,
}


# --- Mémoire ----------------------------------------------------------------


@router.get("/interoceptif")
def interoceptive_exercises(user: CurrentUser) -> dict[str, Any]:
    """Les exercices, leurs contre-indications, et l'état de la validation."""
    from ..data import interoceptive

    profile = user.get("profile") or {}
    return {
        "exercices": interoceptive.EXERCISES,
        "contre_indications": interoceptive.CONTRAINDICATIONS,
        "mecanisme": interoceptive.MECHANISM,
        "sources": interoceptive.SOURCES,
        "valide_le": profile.get("interoceptif_valide_le"),
        "compte_par_exercice": {
            row["situation"]: int(row["n"])
            for row in db.query_all(
                """
                SELECT situation, count(*) AS n FROM journal_entries
                WHERE user_id = %s AND kind = 'exposition'
                  AND situation LIKE 'Exposition intéroceptive%%'
                GROUP BY situation
                """,
                (user["id"],),
            )
        },
    }


@router.get("/rapport")
def report(user: CurrentUser, days: int = 90) -> dict[str, Any]:
    """Tout ce qu'il faut pour un rapport imprimable destiné à un professionnel.

    Rien de nouveau n'est calculé ici : ce sont les mêmes signaux déterministes
    que ceux affichés dans le fil, rassemblés en un seul objet.
    """
    user_id = user["id"]
    today = dt.date.today()
    start = today - dt.timedelta(days=days - 1)
    sig = signals_mod.compute(user_id, today, days)
    state = chat_mod.day_state(user_id, today)

    return {
        "genere_le": str(today),
        "periode": {"debut": str(start), "fin": str(today), "jours": days},
        "compte": {
            "email": user["email"],
            "depuis": str(user.get("created_at"))[:10] if user.get("created_at") else None,
        },
        "programme": state,
        "cadre": (
            "Auto-assistance structurée fondée sur le Protocole Unifié (Barlow) et les "
            "recommandations NICE — intervention de « faible intensité » au sens de NICE. "
            "Aucun diagnostic, aucun conseil médicamenteux. Les chiffres sont calculés par le "
            "serveur sur l'historique complet, pas produits par un modèle de langage."
        ),
        "signaux": sig["signaux"],
        "quotidien": db.query_all(
            """
            SELECT entry_date,
                   avg(anxiety_0_10)::numeric(4,2) AS anxiete,
                   avg(mood_0_10)::numeric(4,2)    AS humeur,
                   max(sleep_hours)                AS sommeil_h,
                   max(avoidance_0_10)             AS evitement,
                   sum(panic_attacks)              AS paniques
            FROM daily_checkins WHERE user_id = %s AND entry_date >= %s
            GROUP BY entry_date ORDER BY entry_date
            """,
            (user_id, start),
        ),
        "echelles": db.query_all(
            """
            SELECT instrument, taken_on, total, severity FROM assessments
            WHERE user_id = %s AND taken_on >= %s ORDER BY instrument, taken_on
            """,
            (user_id, start),
        ),
        "expositions": db.query_all(
            """
            SELECT label, kind, anticipated_anxiety, attempts, last_attempt_on, best_learning, mastered
            FROM exposure_items WHERE user_id = %s ORDER BY mastered, anticipated_anxiety NULLS LAST
            """,
            (user_id,),
        ),
        "apprentissages": db.query_all(
            """
            SELECT entry_date, situation, prediction, prediction_probability, actual_outcome, learning
            FROM journal_entries
            WHERE user_id = %s AND kind = 'exposition' AND entry_date >= %s
              AND learning IS NOT NULL
            ORDER BY entry_date DESC LIMIT 20
            """,
            (user_id, start),
        ),
        "activites": db.query_all(
            """
            SELECT a.title,
                   count(*) FILTER (WHERE l.status IN ('fait','partiel')) AS faites,
                   count(*) FILTER (WHERE l.status = 'pas_fait')          AS non_faites,
                   avg(l.anxiety_after - l.anxiety_before)::numeric(4,2)  AS effet_moyen
            FROM activity_logs l JOIN activities a ON a.slug = l.activity_slug
            WHERE l.user_id = %s AND l.entry_date >= %s
            GROUP BY a.title ORDER BY faites DESC
            """,
            (user_id, start),
        ),
    }


@router.get("/memory")
def memory_state(user: CurrentUser, q: str | None = None, k: int = 10) -> dict[str, Any]:
    """Ce que l'assistant a en mémoire, et ce qu'une requête y retrouve.

    Exposé volontairement : l'utilisateur doit pouvoir vérifier ce qui est stocké
    à son sujet et ce qui est effectivement retrouvé.
    """
    out: dict[str, Any] = {"stats": memory.stats(user["id"])}
    if q:
        out["resultats"] = memory.search(user["id"], q, k=k)
    else:
        out["recents"] = memory.recent(user["id"], 12)
    return out


@router.post("/memory/reindex")
def reindex(user: CurrentUser) -> dict[str, Any]:
    """Réindexe tout l'historique déjà en base (idempotent)."""
    counts = memory.backfill(user["id"])
    vectorised = memory.embed_pending(user["id"])
    return {"indexes": counts, "vectorises": vectorised, "stats": memory.stats(user["id"])}
