"""Orchestrateur du fil : décide quoi répondre et quel widget ouvrir.

Répartition des rôles, volontairement stricte :

- **`capture.py`** extrait les chiffres du texte libre. Déterministe.
- **`signals.py`** calcule les statistiques sur l'historique entier. Déterministe.
- **`memory.py`** retrouve les éléments d'historique pertinents, sans limite d'âge.
- **`search.py`** retrouve les extraits du corpus de fiches.
- **le modèle** rédige la réponse et choisit le widget à ouvrir. Il ne calcule
  rien, n'invente aucun chiffre, et n'écrit rien en base : un widget est une
  proposition que l'utilisateur valide.

Sans clé d'API, tout continue de fonctionner : `_deterministic()` prend le relais
avec des règles explicites, et le dit.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import re
from typing import Any

from . import capture as capture_mod
from . import db, llm_client, memory, program, search, signals as signals_mod
from .config import settings

logger = logging.getLogger(__name__)

WIDGET_TYPES = {
    "checkin", "breath", "journal", "gad7", "stats", "analysis", "sources", "account", "logout",
    "exposition", "meditation", "memoire", "echelles",
    "interoceptif", "rapport",
    # V5 — le check-in unique est découpé en trois. `checkin` est conservé : les
    # items déjà dans le fil gardent leur type, et le passé ne se réécrit pas.
    "matin", "soir", "maintenant",
    # Récapitulatif d'un épisode, déposé après la crise. Le modèle ne l'ouvre
    # jamais lui-même : il n'y a rien à saisir, l'épisode est déjà enregistré.
    "panique",
    # Charge du jour et prévision : une consultation, elle n'écrit rien.
    "prevision",
}

# Séparateur entre la prose et la décision structurée. Ce format rend le
# streaming token par token possible : un objet JSON unique n'est exploitable
# qu'une fois complet, donc impossible à afficher au fur et à mesure.
FOOTER = "---WIDGET---"

PREFILL_FIELDS = {
    "anxiety_0_10", "anxiety_peak_0_10", "mood_0_10", "avoidance_0_10", "sleep_hours",
    "sleep_quality_0_10", "caffeine_units", "alcohol_units", "exercise_min",
    "panic_attacks", "main_trigger", "free_text", "situation", "automatic_thought",
}

SYSTEM_PROMPT = """Tu es l'assistant de FUCK ANXIETY, une application française de suivi des troubles anxieux fondée sur le Protocole Unifié de Barlow et les recommandations NICE.

TON
- Tutoiement, direct, concret. Pas de politesses inutiles, pas d'emoji, pas de « je comprends que ce doit être difficile ».
- Court : 2 à 5 phrases. Si tu as beaucoup à dire, ouvre un widget au lieu d'écrire un mur de texte.
- Jamais de félicitations pour une variation sous le seuil de signification clinique.

RÈGLES ABSOLUES
1. Tu n'utilises que ce qui t'est fourni : SIGNAUX (déjà calculés), HISTORIQUE (mémoire de l'utilisateur), EXTRAITS DU CORPUS. Tu n'inventes aucun chiffre, aucune étude, aucune référence.
2. Tu ne recalcules rien. Les chiffres des SIGNAUX sont la vérité, reprends-les tels quels.
2 bis. Un signal marqué NON RETENU n'a pas survécu à la correction statistique : tu ne le présentes jamais comme une régularité établie. Au mieux : « pas encore assez de données pour le dire ». Tu ne dis pas non plus qu'il n'y a aucun lien — l'absence de preuve n'est pas une preuve d'absence.
3. Toute affirmation clinique porte la référence de l'extrait utilisé : [1], [2]. Sans extrait, tu ne l'affirmes pas.
4. Tu distingues l'observation de l'interprétation. Une corrélation n'est jamais présentée comme une cause.
5. Aucun diagnostic. Aucun conseil sur les médicaments : ni démarrer, ni arrêter, ni ajuster.
6. Tu n'enregistres jamais rien toi-même. Pour saisir une donnée, tu ouvres un widget que l'utilisateur valide.
7. Si l'utilisateur évoque des idées suicidaires ou de se faire du mal : tu abandonnes tout le reste, tu le dis simplement, tu renvoies vers le 3114 (France, gratuit, 24 h/24) et le 15 / 112, et tu ne donnes aucun autre conseil.

WIDGETS QUE TU PEUX OUVRIR
- matin       : la nuit et l'instant (sommeil, comment il se sent là, ce qu'il redoute aujourd'hui)
- soir        : la journée écoulée (pic et moyenne d'anxiété, évitement, cafés, alcool, sport)
- maintenant  : une mesure instantanée, un seul curseur — quand il dit comment il va *là*
- checkin     : l'ancien formulaire unique. Ne l'ouvre plus : préfère matin, soir ou maintenant
- breath      : respiration lente guidée, 5 min à ~6 cycles/min
- journal     : écrire une entrée (libre ou journal de pensées)
- echelles    : GAD-7 (hebdomadaire), PHQ-2 (mensuel), évitement (hebdomadaire)
- exposition  : échelle d'expositions — ajouter un item, ou enregistrer une tentative
- interoceptif: exposition intéroceptive guidée (hyperventilation, apnée, rotation…) pour la peur des sensations physiques
- meditation  : pratique guidée (souffle, scan corporel, conscience émotionnelle, relaxation)
- rapport     : synthèse imprimable pour un professionnel
- prevision   : la charge du jour, la fourchette prévue pour demain, et la fiabilité réelle du modèle
- stats       : ses chiffres et ses courbes
- analysis    : analyse de la période avec ses sources
- memoire     : recherche dans son propre historique
- sources     : les fiches du corpus
- account     : compte et consentement
- logout      : se déconnecter

FORMAT DE SORTIE — deux parties, dans cet ordre, rien d'autre :

1. Ta réponse en prose. 2 à 5 phrases. Markdown léger autorisé (**gras** seulement).
2. Une ligne contenant exactement ---WIDGET--- suivie d'un objet JSON :
   {"widget": {"type": "checkin", "prefill": {"anxiety_0_10": 8}}, "suggestions": ["Mes chiffres"]}

Mets "widget": null si aucun widget n'est utile. "prefill" ne contient que des champs que tu as réellement lus dans le message. "suggestions" : 0 à 3 propositions de 4 mots maximum. N'écris rien après le JSON."""

SAFETY_REPLY = (
    "Ce que tu écris là parle d'idées suicidaires ou de te faire du mal. Je ne suis pas "
    "l'outil qu'il faut pour ça, et je ne vais pas faire comme si.\n\n"
    "**Appelle quelqu'un maintenant : 3114** — prévention du suicide, gratuit, 24 h/24, "
    "7 j/7. En urgence, le **15** ou le **112**.\n\n"
    "Je reste là pour le suivi quand tu veux."
)


# --- Contexte ---------------------------------------------------------------


def day_state(user_id: str, today: dt.date | None = None) -> dict[str, Any]:
    """État du jour : ce qui est fait, où on en est dans le programme."""
    today = today or dt.date.today()
    state = program.recompute_week(user_id, today)
    module = program.module_for_week(state["current_week"])

    moments = {
        row["moment"]: row
        for row in db.query_all(
            """
            SELECT moment, anxiety_0_10, anxiety_peak_0_10, sleep_hours
            FROM daily_checkins WHERE user_id = %s AND entry_date = %s
            """,
            (user_id, today),
        )
    }
    # `checkin` reste la ligne du soir en priorité : c'est elle qui porte l'anxiété
    # de la journée. À défaut, celle du matin — mieux que rien pour l'affichage.
    checkin = moments.get("soir") or moments.get("matin")
    last_gad = db.query_one(
        """
        SELECT taken_on, total FROM assessments
        WHERE user_id = %s AND instrument = 'gad7' ORDER BY taken_on DESC LIMIT 1
        """,
        (user_id,),
    )
    streak_rows = db.query_all(
        """
        SELECT DISTINCT entry_date FROM daily_checkins
        WHERE user_id = %s AND entry_date <= %s ORDER BY entry_date DESC LIMIT 400
        """,
        (user_id, today),
    )
    streak, expected = 0, today
    for row in streak_rows:
        if row["entry_date"] == expected:
            streak += 1
            expected -= dt.timedelta(days=1)
        elif row["entry_date"] < expected:
            break

    maintenance = state["status"] == "entretien"
    last_exposure = db.query_one(
        """
        SELECT max(entry_date) AS last FROM journal_entries
        WHERE user_id = %s AND kind = 'exposition'
        """,
        (user_id,),
    )
    exposure_on = last_exposure["last"] if last_exposure else None
    days_since_exposure = (today - exposure_on).days if exposure_on else None

    # Nombre de mesures instantanées du jour : c'est ce qui permet de proposer le
    # pic et la moyenne calculés le soir, au lieu de les faire reconstruire.
    momentary = db.query_one(
        """
        SELECT count(*) AS n, max(anxiety_0_10) AS pic, avg(anxiety_0_10) AS moyenne
        FROM momentary_ratings WHERE user_id = %s AND entry_date = %s
        """,
        (user_id, today),
    )

    return {
        "date": str(today),
        # Vrai dès qu'un des deux moments est renseigné : le socle est tenu.
        "checkin_done": checkin is not None,
        "matin_done": "matin" in moments,
        "soir_done": "soir" in moments,
        "mesures_instantanees": int(momentary["n"]) if momentary else 0,
        "pic_instantane": momentary["pic"] if momentary else None,
        "anxiety_today": checkin["anxiety_0_10"] if checkin else None,
        "week": state["current_week"],
        "module": module["module"],
        "module_title": module["title"],
        "module_goal": module["goal"],
        "streak": streak,
        # En entretien, le GAD-7 passe de l'hebdomadaire au mensuel : il n'y a plus
        # de raison de mesurer aussi souvent une fois la rémission atteinte.
        "gad7_due": last_gad is None
        or (today - last_gad["taken_on"]).days >= (30 if maintenance else 7),
        "gad7_last": last_gad["total"] if last_gad else None,
        "gad7_last_on": str(last_gad["taken_on"]) if last_gad else None,
        "status": state["status"],
        "critere": state.get("critere") or {},
        "exposition_due": maintenance and (days_since_exposure is None or days_since_exposure >= 7),
        "jours_depuis_exposition": days_since_exposure,
    }


def _thread_tail(user_id: str, limit: int = 10) -> list[dict[str, Any]]:
    rows = db.query_all(
        """
        SELECT role, kind, content, widget_type, status
        FROM thread_items WHERE user_id = %s ORDER BY seq DESC LIMIT %s
        """,
        (user_id, limit),
    )
    return list(reversed(rows))


def _build_context(user: dict[str, Any], text: str) -> dict[str, Any]:
    user_id = user["id"]
    state = day_state(user_id)
    sig = signals_mod.compute(user_id, dt.date.today(), 60)
    memories = memory.search(user_id, text, k=8) if text else memory.recent(user_id, 8)
    chunks = search.hybrid_search(text, k=5) if text else []
    return {
        "state": state,
        "signals": sig,
        "memories": memories,
        "chunks": chunks,
        "tail": _thread_tail(user_id),
    }


def _signals_digest(sig: dict[str, Any]) -> str:
    """Les signaux, en une liste compacte. Calculés sur l'historique entier."""
    lines = [
        f"Période couverte : {sig['periode']['debut']} → {sig['periode']['fin']} "
        f"({sig['periode']['jours']} jours). Volume : {json.dumps(sig['brut'], ensure_ascii=False)}"
    ]
    for signal in sig["signaux"]:
        if signal.get("value") in (None, [], {}) and signal.get("n", 0) == 0:
            continue
        # Pour une corrélation, la valeur à commenter est celle des **variations**, pas
        # le niveau brut : le brut est gonflé par la dérive commune, et le modèle
        # commenterait un chiffre que la méthode a justement écarté. On lui dit aussi
        # explicitement si l'association a survécu à la correction de multiplicité.
        value = signal.get("value")
        if "value_variations" in signal:
            value = signal.get("value_variations")
        line = f"- {signal['label']} : {value!r}"
        if signal.get("delta") is not None:
            line += f" (écart {signal['delta']!r})"
        if signal.get("retenu") is False and signal.get("p") is not None:
            line += " [NON RETENU — ne pas présenter comme un fait]"
        line += f" — {signal.get('verdict')} [n={signal.get('n')}]"
        lines.append(line)
    return "\n".join(lines)


def _user_prompt(context: dict[str, Any], text: str, cap: capture_mod.Capture) -> str:
    state = context["state"]
    parts = [
        "ÉTAT DU JOUR",
        f"- date : {state['date']}",
        f"- check-in fait aujourd'hui : {'oui' if state['checkin_done'] else 'non'}",
        f"- semaine {state['week']} du programme, module {state['module']} — "
        f"{state['module_title']} ({state['module_goal']})",
        f"- jours d'affilée : {state['streak']}",
        f"- GAD-7 à faire : {'oui' if state['gad7_due'] else 'non'}"
        + (f", dernier score {state['gad7_last']} le {state['gad7_last_on']}" if state["gad7_last"] is not None else ""),
        "",
        "SIGNAUX (déjà calculés sur tout l'historique — ne recalcule rien)",
        _signals_digest(context["signals"]),
        "",
        "HISTORIQUE PERTINENT (mémoire de l'utilisateur, sans limite d'ancienneté)",
        memory.format_for_prompt(context["memories"]),
        "",
        "EXTRAITS DU CORPUS (cite-les par leur numéro)",
        search.build_context(context["chunks"], max_chars=6000) or "(aucun extrait pertinent)",
        "",
    ]
    if context["tail"]:
        parts.append("DERNIERS TOURS DU FIL")
        for item in context["tail"]:
            if item["kind"] == "widget":
                parts.append(f"- [widget {item['widget_type']} · {item.get('status') or 'ouvert'}]")
            else:
                who = "utilisateur" if item["role"] == "user" else "toi"
                parts.append(f"- {who} : {(item.get('content') or '')[:280]}")
        parts.append("")

    if cap.has_values:
        parts.append(
            "VALEURS EXTRAITES DU MESSAGE (extraction déterministe, déjà fiable — "
            "reprends-les dans le prefill, ne les modifie pas) :\n"
            + json.dumps(cap.values, ensure_ascii=False)
            + f"\nExtraits de phrase correspondants : {json.dumps(cap.evidence, ensure_ascii=False)}"
        )
        if cap.approximate:
            parts.append(
                f"Valeurs déduites d'une formulation qualitative, à faire confirmer : {cap.approximate}"
            )
        parts.append("")

    parts.append(f"MESSAGE DE L'UTILISATEUR\n{text}")
    return "\n".join(parts)


# --- Réponse ----------------------------------------------------------------


def split_reply(raw: str) -> tuple[str, dict[str, Any]]:
    """Sépare la prose du pied structuré.

    Retourne (prose, décision). Si le pied est absent ou illisible, toute la
    sortie est traitée comme de la prose : une réponse sans widget vaut mieux
    qu'une erreur.
    """
    text = (raw or "").strip()
    if FOOTER not in text:
        return text, {}
    prose, _, footer = text.partition(FOOTER)
    footer = re.sub(r"```(?:json)?", "", footer).strip()
    start, end = footer.find("{"), footer.rfind("}")
    if start == -1 or end == -1:
        return prose.strip(), {}
    try:
        parsed = json.loads(footer[start : end + 1])
    except json.JSONDecodeError:
        logger.warning("Pied JSON illisible, réponse conservée sans widget")
        return prose.strip(), {}
    return prose.strip(), parsed if isinstance(parsed, dict) else {}


def _sanitise(
    decision: dict[str, Any], cap: capture_mod.Capture, reply: str | None = None
) -> dict[str, Any]:
    """Filtre la sortie du modèle : type de widget connu, champs autorisés.

    Les valeurs extraites par `capture` sont **prioritaires** sur celles du
    modèle : un chiffre de santé ne dépend pas d'une interprétation.
    """
    reply = str(reply if reply is not None else decision.get("reply") or "").strip()

    widget = decision.get("widget")
    clean_widget: dict[str, Any] | None = None
    if isinstance(widget, dict) and widget.get("type") in WIDGET_TYPES:
        prefill = widget.get("prefill") if isinstance(widget.get("prefill"), dict) else {}
        prefill = {k: v for k, v in prefill.items() if k in PREFILL_FIELDS}
        inferred = [k for k in prefill if k not in cap.values]
        prefill.update(cap.values)  # le déterministe écrase le modèle
        clean_widget = {
            "type": widget["type"],
            "prefill": prefill,
            "a_verifier": sorted(set(cap.approximate) | set(inferred)),
        }

    suggestions = decision.get("suggestions")
    clean_suggestions: list[str] = []
    if isinstance(suggestions, list):
        for item in suggestions[:3]:
            if isinstance(item, str) and 1 <= len(item.strip()) <= 40:
                clean_suggestions.append(item.strip())

    return {"reply": reply, "widget": clean_widget, "suggestions": clean_suggestions}


def _local_reason(user: dict[str, Any], detail: str | None = None) -> str:
    """Pourquoi la réponse vient des règles fixes plutôt que du modèle.

    Trois causes distinctes, longtemps confondues sous « aucune clé configurée » —
    ce qui est faux, et trompeur, quand la clé est bien là et que c'est le
    consentement qui manque ou l'appel qui a échoué.
    """
    if not settings.has_llm:
        return "Aucune clé d'IA n'est configurée sur ce serveur"
    if not user.get("ai_consent"):
        # Ne devrait plus arriver : l'IA est active par défaut et rien ne permet
        # de la couper. On ne renvoie donc plus l'utilisateur vers un réglage qui
        # n'existe pas — c'est une anomalie de compte, pas un choix.
        return "L'IA n'est pas active sur ce compte, ce qui n'est pas censé arriver"
    return detail or "Le modèle n'a pas répondu"


def _deterministic(
    context: dict[str, Any],
    text: str,
    cap: capture_mod.Capture,
    reason: str = "Aucune clé d'IA n'est configurée sur ce serveur",
) -> dict[str, Any]:
    """Décision sans modèle : règles explicites, et on assume de le dire."""
    state = context["state"]
    intents = cap.intents

    if cap.has_values:
        summary = capture_mod.summarise(cap)
        # Vers quel écran : si la phrase ne parle que de la nuit, c'est le matin.
        # Sinon le soir, qui porte la journée. Le choix suit ce qui a été extrait,
        # pas l'heure — quelqu'un qui raconte sa nuit à 18 h parle bien de sa nuit.
        sleep_only = set(cap.values) <= {"sleep_hours", "sleep_quality_0_10"}
        target = "matin" if sleep_only and cap.values else "soir"
        return {
            "reply": (
                f"J'ai compris : **{summary}**. J'ai pré-rempli — vérifie et valide, "
                "j'enregistre rien avant."
            ),
            "widget": {"type": target, "prefill": cap.values, "a_verifier": cap.approximate},
            "suggestions": ["Mes chiffres", "Respirer 5 min"],
        }

    if "breath" in intents:
        return {
            "reply": (
                "On fait redescendre l'activation d'abord. 5 minutes à ~6 cycles par minute, "
                "l'expiration est la partie qui compte."
            ),
            "widget": {"type": "breath", "prefill": {}, "a_verifier": []},
            "suggestions": [],
        }
    if "prevision" in intents:
        return {
            "reply": (
                "Ta charge du jour et la fourchette de demain. La fourchette est large "
                "exprès : un chiffre unique serait lu comme une promesse."
            ),
            "widget": {"type": "prevision", "prefill": {}, "a_verifier": []},
            "suggestions": [],
        }
    if "stats" in intents:
        return {"reply": "Voilà tes chiffres.", "widget": {"type": "stats", "prefill": {}, "a_verifier": []}, "suggestions": []}
    if "analysis" in intents:
        return {"reply": "Je regarde la période et je te dis ce que les données montrent.",
                "widget": {"type": "analysis", "prefill": {}, "a_verifier": []}, "suggestions": []}
    if "gad7" in intents:
        return {"reply": "Le GAD-7 prend deux minutes." if state["gad7_due"]
                else "Tu l'as déjà rempli cette semaine — il porte sur 2 semaines, plus souvent n'a pas de sens.",
                "widget": {"type": "echelles", "prefill": {}, "a_verifier": []} if state["gad7_due"] else None,
                "suggestions": []}
    if "exposition" in intents:
        return {
            "reply": (
                "C'est le module qui produit l'essentiel du changement durable. Écris ta prédiction "
                "avant, le résultat réel après — c'est l'écart entre les deux qui apprend quelque "
                "chose, pas la baisse d'anxiété pendant."
            ),
            "widget": {"type": "exposition", "prefill": {}, "a_verifier": []},
            "suggestions": [],
        }
    if "interoceptif" in intents:
        return {
            "reply": (
                "Si ce sont les sensations elles-mêmes qui font peur, c'est l'exposition "
                "intéroceptive qu'il faut : les provoquer volontairement, en sécurité, pour "
                "apprendre qu'elles sont désagréables et pas dangereuses. Lis les "
                "contre-indications avant de commencer."
            ),
            "widget": {"type": "interoceptif", "prefill": {}, "a_verifier": []},
            "suggestions": [],
        }
    if "rapport" in intents:
        return {
            "reply": (
                "Voilà de quoi imprimer une synthèse : courbes, GAD-7 avec ses seuils, expositions "
                "et ce que tu en as appris, et ce qui a marché chez toi."
            ),
            "widget": {"type": "rapport", "prefill": {}, "a_verifier": []},
            "suggestions": [],
        }
    if "meditation" in intents:
        return {
            "reply": "Choisis la pratique et la durée. La régularité compte plus que la longueur.",
            "widget": {"type": "meditation", "prefill": {}, "a_verifier": []},
            "suggestions": [],
        }
    if "memoire" in intents:
        return {
            "reply": (
                "Tout est conservé, sans limite d'ancienneté. Cherche dans ton propre historique."
            ),
            "widget": {"type": "memoire", "prefill": {}, "a_verifier": []},
            "suggestions": [],
        }
    if "sources" in intents:
        return {"reply": "Tout ce que je te propose vient de ces fiches. Ouvre celle qui t'intéresse.",
                "widget": {"type": "sources", "prefill": {}, "a_verifier": []}, "suggestions": []}
    if "maintenant" in intents:
        return {
            "reply": "Un chiffre, c'est tout. Tu peux le faire autant de fois que tu veux.",
            "widget": {"type": "maintenant", "prefill": {}, "a_verifier": []},
            "suggestions": [],
        }
    if "checkin" in intents or not state["checkin_done"]:
        due = _moment_due(state) or "soir"
        return {"reply": "On note ta journée." if due == "soir" else "On commence par la nuit.",
                "widget": {"type": due, "prefill": {}, "a_verifier": []}, "suggestions": []}

    return {
        "reply": (
            f"Noté, c'est dans ton journal du jour. {reason} : je réponds avec des règles "
            "fixes, pas avec un modèle de langage."
        ),
        "widget": {"type": "journal", "prefill": {"free_text": text}, "a_verifier": []},
        "suggestions": [],
    }


async def respond(user: dict[str, Any], text: str) -> dict[str, Any]:
    """Retourne la décision : réponse, widget éventuel, suggestions, citations."""
    cap = capture_mod.parse(text)
    context = await asyncio.to_thread(_build_context, user, text)

    red_flags = signals_mod.detect_red_flags([text])
    if red_flags:
        return {
            "reply": SAFETY_REPLY,
            "widget": None,
            "suggestions": [],
            "citations": [],
            "engine": "sécurité",
            "risk": True,
            "capture": cap,
        }

    citations = search.to_citations(context["chunks"])
    ai_allowed = bool(user.get("ai_consent")) and settings.has_llm

    if ai_allowed:
        try:
            result = await llm_client.complete(SYSTEM_PROMPT, _user_prompt(context, text, cap))
            prose, footer = split_reply(result.text)
            if not prose:
                decision = _deterministic(
                    context, text, cap, _local_reason(user, "Le modèle a renvoyé une réponse vide")
                )
                engine = f"{result.engine} (sortie vide, repli local)"
            else:
                decision = _sanitise(footer, cap, reply=prose)
                engine = result.engine + (" (fallback)" if result.fallback_used else "")
        except llm_client.LLMUnavailable as exc:
            logger.warning("LLM indisponible : %s", exc)
            decision = _deterministic(
                context, text, cap, _local_reason(user, f"Le modèle a échoué ({exc})")
            )
            engine = "local"
    else:
        decision = _deterministic(context, text, cap, _local_reason(user))
        engine = "local"

    decision.update({"citations": citations, "engine": engine, "risk": False, "capture": cap})
    return decision


async def respond_stream(user: dict[str, Any], text: str):
    """Version streamée de `respond`.

    Yield des tuples :
      ("token", str)      fragment de prose, à afficher immédiatement
      ("engine", str)     moteur retenu
      ("decision", dict)  décision finale (réponse complète, widget, suggestions, citations)

    La prose est diffusée telle qu'elle arrive ; le pied structuré est retenu et
    n'apparaît jamais à l'écran. Si aucun modèle n'est disponible, la décision
    déterministe est renvoyée d'un coup — il n'y a rien à faire patienter.
    """
    cap = capture_mod.parse(text)
    context = await asyncio.to_thread(_build_context, user, text)

    red_flags = signals_mod.detect_red_flags([text])
    if red_flags:
        yield ("engine", "sécurité")
        yield ("token", SAFETY_REPLY)
        yield (
            "decision",
            {
                "reply": SAFETY_REPLY, "widget": None, "suggestions": [], "citations": [],
                "engine": "sécurité", "risk": True,
            },
        )
        return

    citations = search.to_citations(context["chunks"])
    if not (bool(user.get("ai_consent")) and settings.has_llm):
        decision = _deterministic(context, text, cap, _local_reason(user))
        decision.update({"citations": citations, "engine": "local", "risk": False})
        yield ("engine", "local")
        yield ("token", decision["reply"])
        yield ("decision", decision)
        return

    buffer = ""
    emitted = 0
    engine = "inconnu"
    async for kind, value in llm_client.stream(SYSTEM_PROMPT, _user_prompt(context, text, cap)):
        if kind == "engine":
            engine = value
            yield ("engine", value)
        elif kind == "error":
            logger.warning("Streaming interrompu : %s", value)
            break
        elif kind == "token":
            buffer += value
            # On ne diffuse que ce qui est sûrement de la prose : tant que la fin
            # du buffer pourrait être un début de séparateur, on retient.
            safe = buffer.split(FOOTER)[0] if FOOTER in buffer else _hold_back(buffer)
            if len(safe) > emitted:
                yield ("token", safe[emitted:])
                emitted = len(safe)
            if FOOTER in buffer:
                continue

    prose, footer = split_reply(buffer)
    if not prose:
        decision = _deterministic(
            context, text, cap, _local_reason(user, "Le modèle a renvoyé une réponse vide")
        )
        engine = f"{engine} (sortie vide, repli local)"
    else:
        decision = _sanitise(footer, cap, reply=prose)
    decision.update({"citations": citations, "engine": engine, "risk": False})

    # Rattrapage : si la prose finale dépasse ce qui a été diffusé (reste retenu
    # par prudence), on envoie la fin avant de clore.
    if len(decision["reply"]) > emitted:
        yield ("token", decision["reply"][emitted:])
    yield ("decision", decision)


def _hold_back(buffer: str) -> str:
    """Retient la fin du buffer si elle peut être un séparateur en cours d'arrivée."""
    for length in range(min(len(FOOTER), len(buffer)), 0, -1):
        if buffer.endswith(FOOTER[:length]):
            return buffer[:-length]
    return buffer


# Quel widget ouvre une activité du programme. `None` est un choix, pas un oubli :
# régularité du sommeil, activité physique et caféine sont des recommandations
# d'hygiène, pas des exercices à minuter. Le message porte le conseil et ses
# preuves, et aucun widget ne s'ouvre — c'est le « conseil » du parcours quotidien.
SLUG_WIDGETS: dict[str, str | None] = {
    "checkin-quotidien": "checkin",
    "respiration-lente-10": "breath",
    "soupir-physiologique": "breath",
    "journal-libre": "journal",
    "journal-pensees": "journal",
    "temps-inquietude": "journal",
    "resolution-problemes": "journal",
    "inventaire-securite": "journal",
    "objectifs-valeurs": "journal",
    "plan-prevention-rechute": "journal",
    "psychoeducation-cycle": "journal",
    "meditation-souffle": "meditation",
    "scan-corporel": "meditation",
    "conscience-emotionnelle": "meditation",
    "relaxation-musculaire": "meditation",
    "exposition-interoceptive": "interoceptif",
    "echelle-exposition": "exposition",
    "exposition-in-vivo": "exposition",
    "experience-sociale": "exposition",
    "exposition-imaginaire": "exposition",
    "gad7-hebdo": "echelles",
    "regularite-sommeil": None,
    "activite-physique": None,
    "reduction-cafeine": None,
}


def _citation_for(item: dict[str, Any]) -> dict[str, Any]:
    """La fiche de preuve d'une activité, au format des citations du fil.

    C'est ce qui alimente le panneau « D'OÙ ÇA SORT » : le mécanisme, le niveau de
    preuve et les références de l'activité, plus les observations personnelles qui
    l'ont déclenchée. `build_day` produit déjà `triggered_by` dans ce but ; il
    suffit de le rendre.
    """
    activity = item["activity"]
    triggers = [
        f"{obs.get('libelle')} : {obs.get('valeur')} — {obs.get('methode')}"
        for obs in (item.get("triggered_by") or [])
        if obs.get("libelle")
    ]
    return {
        "doc_id": activity.get("kb_doc_id") or activity["slug"],
        "titre": activity["title"],
        "niveau_de_preuve": activity.get("evidence_level"),
        "categorie": activity.get("category"),
        "sources": activity.get("sources") or [],
        "extraits": [activity.get("mechanism"), *triggers],
        "recuperation": {"origine": "programme du jour", "slot": item["slot"]},
    }


def _decision_for_item(item: dict[str, Any], suggestions: list[str]) -> dict[str, Any]:
    """Transforme un item du programme du jour en décision du fil.

    La justification vient de `why_for_you`, écrite par `program.py` avec les
    chiffres de la personne. On ne la reformule pas : elle est déjà personnalisée,
    et la faire réécrire par un modèle ne ferait qu'ajouter un risque d'invention.
    """
    widget_type = SLUG_WIDGETS.get(item["activity"]["slug"], None)
    activity = item["activity"]
    duration = activity.get("duration_min")
    reply = item["why_for_you"]
    if widget_type is None:
        reply += "\n\nRien à ouvrir : c'est une habitude à changer, pas un exercice à faire ici."
    elif duration:
        reply += f"\n\n**{activity['title']}** — {duration} min."
    return {
        "reply": reply,
        "widget": (
            {"type": widget_type, "prefill": {}, "a_verifier": []} if widget_type else None
        ),
        "suggestions": suggestions,
        "citations": [_citation_for(item)],
        "engine": "programme",
    }


def _todays_proposal(user: dict[str, Any], today: dt.date) -> dict[str, Any] | None:
    """L'item du jour à proposer, choisi dans le programme construit par `program.py`.

    Priorité aux items **adaptatifs** : ce sont ceux que les données de la personne
    ont déclenchés, donc les seuls dont la justification porte ses propres chiffres.
    À défaut, un item du module de la semaine. Le socle n'est pas proposé ici : le
    check-in est déjà traité en amont, et proposer « écris ton journal » sans raison
    particulière n'apporte rien.

    Renvoie `None` si le programme n'a rien à dire — auquel cas l'appelant garde sa
    formulation habituelle. Un échec de construction ne doit pas casser l'ouverture
    du fil : c'est le message d'accueil, il doit toujours arriver.
    """
    try:
        plan = program.build_day(user["id"], user.get("profile") or {}, today)
    except Exception:  # noqa: BLE001
        logger.exception("Programme du jour indisponible, ouverture en mode simple")
        return None

    pending = [
        item
        for item in plan.get("items", [])
        if item.get("status") not in {"fait", "partiel"}
    ]
    for slot in ("adaptatif", "module"):
        for item in pending:
            if item["slot"] == slot and item["activity"]["slug"] != "checkin-quotidien":
                return _decision_for_item(item, ["Mes chiffres", "Plus tard"])
    return None


# Bornes des deux créneaux. Avant midi, c'est le matin ; à partir de 17 h, le soir.
# Entre les deux, on ne réclame rien de neuf : on rattrape ce qui manque, en
# commençant par le matin — sa question porte sur la nuit, elle reste répondable.
MORNING_UNTIL = 12
EVENING_FROM = 17


def _moment_due(state: dict[str, Any], now: dt.datetime | None = None) -> str | None:
    """Lequel des deux moments réclamer, ou `None` si rien n'est dû.

    On ne demande jamais le soir avant 17 h : à midi, la journée n'est pas finie et
    la faire résumer produirait un chiffre faux — puis il faudrait le corriger, ce
    qui apprend à l'utilisateur que ses saisies ne comptent pas.
    """
    hour = (now or dt.datetime.now()).hour
    matin_done, soir_done = state["matin_done"], state["soir_done"]
    if not matin_done and hour < EVENING_FROM:
        return "matin"
    if not soir_done and hour >= EVENING_FROM:
        return "soir"
    if not matin_done and not soir_done:
        return "matin"
    return None


def _intense_session_yesterday(user_id: str) -> dict[str, Any] | None:
    """Demande comment s'est passée la journée après une séance à FC max élevée.

    Formulée comme une **question**, jamais comme une alerte. « Ton cœur est monté à
    172 hier, comment ça a été aujourd'hui ? » est utile ; « attention, risque de
    crise » serait une prédiction sans fiabilité, et anxiogène par elle-même.

    Une seule fois par séance : la marque est posée dans le journal des notifications,
    qui porte déjà la contrainte d'unicité (compte, type, jour).
    """
    from .integrations import whoop

    today = dt.date.today()
    yesterday = today - dt.timedelta(days=1)
    sessions = whoop.intense_sessions(user_id, yesterday, yesterday)
    if not sessions:
        return None

    already = db.query_one(
        """
        SELECT 1 FROM notification_log
        WHERE user_id = %s AND kind = 'suite_seance' AND sent_on = %s
        """,
        (user_id, today),
    )
    if already is not None:
        return None
    db.execute(
        """
        INSERT INTO notification_log (user_id, kind, sent_on, detail)
        VALUES (%s, 'suite_seance', %s, %s)
        ON CONFLICT (user_id, kind, sent_on) DO NOTHING
        """,
        (user_id, today, json.dumps({"seances": len(sessions)})),
    )

    session = sessions[0]
    sport = session["sport"] or "ta séance"
    return {
        "reply": (
            f"Hier, {sport} : ton cœur est monté à **{session['max_heart_rate']}**. "
            "Comment ça a été aujourd'hui ? Un effort intense produit exactement les "
            "sensations que tu redoutes — chez certains ça aide, chez d'autres ça "
            "déclenche. C'est en le notant qu'on saura de quel côté tu es."
        ),
        "widget": {"type": "maintenant", "prefill": {}, "a_verifier": []},
        "suggestions": ["Rien de spécial", "Ça a été dur"],
        "citations": [],
        "engine": "bracelet",
    }


def opening(user: dict[str, Any]) -> dict[str, Any]:
    """Message d'ouverture du jour. Déterministe : rapide, gratuit, prévisible."""
    state = day_state(user["id"])
    name = (user.get("display_name") or "").strip()
    hello = f"Salut {name}." if name else "Salut."

    # --- Régime d'entretien -------------------------------------------------
    # Ce qui distingue les personnes qui rechutent de celles qui ne rechutent pas,
    # c'est de continuer les expositions après la guérison : l'évitement se
    # réinstalle silencieusement, par petites décisions confortables.
    if state["status"] == "entretien":
        if state["exposition_due"]:
            since = state["jours_depuis_exposition"]
            when = f"{since} jours" if since is not None else "un moment"
            return {
                "reply": (
                    f"Tu es en régime d'entretien, et ta dernière exposition volontaire date de "
                    f"**{when}**. Une par semaine, même quand tout va bien : c'est ce qui empêche "
                    "l'évitement de revenir sans bruit."
                ),
                "widget": {"type": "exposition", "prefill": {}, "a_verifier": []},
                "suggestions": ["Mes chiffres", "Plus tard"],
            }
        if not state["checkin_done"]:
            return {
                "reply": (
                    f"{hello} Entretien : check-in hebdomadaire, GAD-7 mensuel, une exposition par "
                    "semaine. Rien d'autre à faire."
                ),
                "widget": {"type": "soir", "prefill": {}, "a_verifier": []},
                "suggestions": ["Mes chiffres", "Mon rapport"],
            }
        return {
            "reply": "Entretien, et tout est à jour. Rien à faire aujourd'hui.",
            "widget": None,
            "suggestions": ["Mes chiffres", "Mon rapport", "Respirer 5 min"],
        }

    # Deux moments, deux questions distinctes. Le sommeil se demande au réveil :
    # le rappel se dégrade dès que l'agenda n'est pas rempli le matin, et
    # l'estimation rétrospective porte un biais qui n'est pas constant. La journée
    # se raconte le soir, quand elle est finie.
    due = _moment_due(state)
    if due is not None:
        streak = state["streak"]
        if due == "matin":
            line = (
                f"{hello} La nuit d'abord : combien t'as dormi, et comment tu te sens là. "
                "Trente secondes."
            )
            if streak >= 2:
                line = (
                    f"**{streak} jours d'affilée.** La nuit d'abord : combien t'as dormi, et "
                    "comment tu te sens là."
                )
        else:
            line = (
                "La journée est finie — on la note. Le pic et la moyenne, pas un chiffre unique : "
                "sous anxiété la mémoire retient les pires moments."
            )
            if state["mesures_instantanees"]:
                line = (
                    f"T'as noté **{state['mesures_instantanees']} fois** comment tu te sentais "
                    f"aujourd'hui (pic à **{state['pic_instantane']}/10**). Je te propose le pic et "
                    "la moyenne calculés — vérifie, corrige si c'est faux."
                )
        return {
            "reply": line,
            "widget": {"type": due, "prefill": {}, "a_verifier": []},
            "suggestions": ["Comment je me sens là", "Respirer 5 min"],
        }

    if state["gad7_due"]:
        return {
            "reply": (
                f"Check-in fait (anxiété **{state['anxiety_today']}/10**). Le GAD-7 est dû cette "
                "semaine : c'est lui qui dit si quelque chose bouge vraiment."
            ),
            "widget": {"type": "gad7", "prefill": {}, "a_verifier": []},
            "suggestions": ["Mes chiffres", "Plus tard"],
        }

    # Une séance intense hier, et rien de noté depuis : on demande. C'est ce qui
    # remplace la détection automatique de crise — impossible avec l'API Whoop, qui
    # n'expose aucune série de fréquence cardiaque, et de toute façon indésirable :
    # une fausse alerte de panique est un déclencheur de panique.
    #
    # Une question n'a pas ce défaut. Elle ne peut rien annoncer.
    session = _intense_session_yesterday(user["id"])
    if session is not None:
        return session

    # Le check-in est fait et rien n'est dû : c'est ici que le programme du jour
    # prend la parole. Sans ça, l'ouverture s'arrêtait à « tu veux faire quoi ? » —
    # alors que `build_day` avait déjà calculé quoi proposer, et pourquoi.
    proposal = _todays_proposal(user, dt.date.today())
    if proposal is not None:
        anxiety = state["anxiety_today"]
        prefix = f"Check-in fait (anxiété **{anxiety}/10**). " if anxiety is not None else ""
        proposal["reply"] = prefix + proposal["reply"]
        return proposal

    return {
        "reply": f"Check-in fait (anxiété **{state['anxiety_today']}/10**). Tu veux faire quoi ?",
        "widget": None,
        "suggestions": ["Respirer 5 min", "Comment je vais ?", "Mes chiffres"],
    }
