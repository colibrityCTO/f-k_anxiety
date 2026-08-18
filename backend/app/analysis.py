"""Analyse IA : signaux déterministes + RAG sur le corpus + rédaction par le LLM.

Architecture volontairement en deux étages :

1. **Étage déterministe** (`signals.py`) — tous les chiffres sont calculés en
   Python : moyennes, corrélations, taux de réalisation, écarts GAD-7. Le LLM ne
   calcule rien, ce qui élimine la principale source d'erreur factuelle.
2. **Étage LLM** — le modèle reçoit les signaux déjà calculés *et* les extraits du
   corpus retrouvés par recherche hybride, et il n'a le droit de s'appuyer que sur
   ces deux sources. Chaque affirmation clinique doit porter une référence [n].

Si aucun LLM n'est disponible, ou si l'utilisateur n'a pas consenti à l'envoi de
ses données, `local_analysis()` produit une analyse complète sans appel externe.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import re
from collections.abc import AsyncIterator
from typing import Any

from . import db, llm_client, search, signals as signals_mod
from .config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Tu es l'assistant d'analyse d'une application française de suivi des troubles anxieux, fondée sur le Protocole Unifié de Barlow et les recommandations NICE.

RÈGLES ABSOLUES — leur non-respect rend la réponse inutilisable :

1. Tu n'utilises QUE deux sources : (a) les SIGNAUX fournis, déjà calculés, et (b) les EXTRAITS DU CORPUS fournis. Tu n'inventes aucun chiffre, aucune étude, aucune référence. Si une information manque, tu écris explicitement qu'elle manque.
2. Tu ne recalcules rien. Les chiffres des SIGNAUX sont la vérité ; reprends-les tels quels.
3. Chaque affirmation clinique ou recommandation est suivie de la référence de l'extrait utilisé, au format [1], [2]. Sans extrait correspondant, tu ne l'affirmes pas.
4. Tu distingues systématiquement l'observation de l'interprétation. Formulations attendues : « Vos données montrent X » (observation) puis « Une hypothèse est Y » (interprétation). Une corrélation n'est jamais présentée comme une causalité.
5. Tu ne poses aucun diagnostic. Tu ne donnes aucun conseil sur les médicaments (ni démarrer, ni arrêter, ni ajuster) : cela relève du médecin.
6. Tu respectes le seuil de signification : une variation du GAD-7 inférieure à 4 points ne doit PAS être présentée comme un progrès ou une aggravation, mais comme du bruit de mesure.
7. Ne pas avoir fait une activité n'est jamais présenté comme un échec moral. C'est une donnée : tu cherches ce qui a bloqué et tu proposes un ajustement (format plus court, autre moment, autre activité).
8. Ton : tutoiement, direct, concret, sans infantilisation et sans optimisme forcé. Pas d'emoji, pas de politesses inutiles.

FORMAT DE RÉPONSE — respecte-le exactement :

TITRE: <une phrase de 12 mots maximum qui résume la période>

## Ce que vos données montrent
(3 à 6 puces, chacune avec le chiffre exact et sa provenance : nombre de jours, nombre de mesures)

## Ce qui a été fait, et ce qui ne l'a pas été
(les activités réalisées, celles qui ne l'ont pas été avec les raisons données, sans jugement)

## Une hypothèse
(1 à 3 hypothèses explicatives, clairement présentées comme des hypothèses, avec références [n])

## Pour les 7 prochains jours
(2 à 4 actions précises, chacune : quoi, quand, pendant combien de temps, et pourquoi — avec référence [n])

## Ce que je ne peux pas savoir
(les limites de cette analyse : données manquantes, durée d'observation trop courte, ce qui nécessiterait un professionnel)
"""

SAFETY_PROMPT = """
ALERTE SÉCURITÉ : les entrées récentes de l'utilisateur contiennent des formulations évoquant des idées suicidaires ou d'automutilation.

Dans ce cas précis, tu abandonnes le format habituel. Tu réponds brièvement (10 lignes maximum) :
- tu nommes ce que tu as lu, sans dramatiser et sans minimiser ;
- tu dis clairement que cette application n'est pas l'outil adapté à cette situation ;
- tu invites à contacter une personne réelle maintenant, en rappelant le 3114 (France, gratuit, 24 h/24) et le 15 / 112 en urgence ;
- tu ne donnes AUCUN autre conseil, aucun exercice, aucune analyse de données.
"""


CHAT_SYSTEM_PROMPT = """Tu es l'assistant explicatif d'une application française de suivi des troubles anxieux (fondée sur le Protocole Unifié de Barlow et les recommandations NICE).

Ton rôle unique : expliquer d'où viennent les recommandations du programme, pour que l'utilisateur comprenne au lieu d'obéir.

RÈGLES :
1. Tu réponds uniquement à partir des EXTRAITS DU CORPUS fournis et, si présents, des SIGNAUX de l'utilisateur. Tu n'inventes rien. Si le corpus ne contient pas la réponse, tu le dis.
2. Chaque affirmation porte une référence [n] renvoyant à un extrait.
3. Tu expliques toujours trois choses : le mécanisme (pourquoi ça marche), le niveau de preuve (et ses limites), et l'application concrète.
4. Tu mentionnes les limites et contre-indications quand elles existent dans les extraits.
5. Aucun diagnostic, aucun conseil médicamenteux. Tutoiement. Pas d'emoji.
6. Réponse courte et dense : 200 mots maximum sauf si la question exige plus.
"""


# --- Construction du prompt --------------------------------------------------


def _format_signals(sig: dict[str, Any]) -> str:
    lines = [
        f"Période analysée : du {sig['periode']['debut']} au {sig['periode']['fin']} "
        f"({sig['periode']['jours']} jours)",
        f"Volume de données : {json.dumps(sig['brut'], ensure_ascii=False)}",
        "",
        "SIGNAUX CALCULÉS :",
    ]
    for signal in sig["signaux"]:
        lines.append(
            f"- [{signal['id']}] {signal['label']} : valeur = {signal.get('value')!r}"
            + (f", delta = {signal['delta']!r}" if signal.get("delta") is not None else "")
            + f" — verdict : {signal.get('verdict')}"
            + f" (n = {signal.get('n')}, méthode : {signal.get('method')})"
        )
        observations = signal.get("observations") or []
        if observations:
            extract = json.dumps(observations[:6], ensure_ascii=False, default=str)
            lines.append(f"  données : {extract}")
        if signal.get("pieges_frequents"):
            lines.append(f"  pièges de pensée fréquents : {signal['pieges_frequents']}")
    return "\n".join(lines)


def retrieval_queries(sig: dict[str, Any]) -> list[str]:
    """Construit les requêtes de recherche à partir des signaux les plus saillants.

    Plusieurs requêtes ciblées valent mieux qu'une requête générique : chacune va
    chercher la fiche du corpus qui traite précisément du signal observé.
    """
    queries: list[str] = ["programme quotidien anxiété suivi et mesure"]
    by_id = {s["id"]: s for s in sig["signaux"]}

    def val(sid: str) -> Any:
        return (by_id.get(sid) or {}).get("value")

    if (val("correlation_sommeil_anxiete") or 0) <= -0.35 or (val("correlation_qualite_sommeil") or 0) <= -0.35:
        queries.append("sommeil régularité contrôle du stimulus anxiété lendemain")
    if (val("attaques_panique") or 0) > 0:
        queries.append("attaque de panique exposition intéroceptive sensations physiques")
    if (val("evitement") or 0) and val("evitement") >= 5:
        queries.append("évitement comportements de sécurité exposition violation d'attente")
    if (val("correlation_cafeine_anxiete") or 0) >= 0.3:
        queries.append("caféine alcool anxiété rebond sevrage progressif")
    if (val("adherence") or 1) < 0.5:
        queries.append("adhérence auto-monitoring pourquoi remplir un journal quotidien")
    trend = by_id.get("tendance_anxiete") or {}
    if (trend.get("delta") or 0) >= 0.7:
        queries.append("inquiétude rumination temps d'inquiétude report flexibilité cognitive")
    if val("gad7") is not None:
        queries.append("GAD-7 seuils interprétation différence minimale cliniquement importante")
    if (val("journal_pensees") or 0) == 0:
        queries.append("restructuration cognitive pièges de pensée catastrophisation")
    return queries[:5]


def retrieve(sig: dict[str, Any], k_per_query: int = 3) -> list[dict[str, Any]]:
    """Recherche hybride multi-requêtes, dédoublonnée par chunk."""
    seen: set[int] = set()
    chunks: list[dict[str, Any]] = []
    for query in retrieval_queries(sig):
        for chunk in search.hybrid_search(query, k=k_per_query, candidates=24):
            if chunk["chunk_id"] in seen:
                continue
            seen.add(chunk["chunk_id"])
            chunk["matched_query"] = query
            chunks.append(chunk)
    return chunks[:12]


# --- Analyse locale (sans LLM) -----------------------------------------------


def local_analysis(sig: dict[str, Any], chunks: list[dict[str, Any]]) -> tuple[str, str]:
    """Analyse déterministe, utilisée quand aucun LLM n'est disponible.

    Retourne (titre, corps markdown). Toutes les phrases sont générées à partir
    des signaux : aucune interprétation qui ne soit adossée à un chiffre.
    """
    by_id = {s["id"]: s for s in sig["signaux"]}
    lines: list[str] = []

    if sig["drapeaux_rouges"]:
        return (
            "Contenu préoccupant repéré — parle à quelqu'un",
            "## Important\n\n"
            "Tes entrées récentes contiennent des formulations qui évoquent des idées suicidaires "
            "ou de te faire du mal. Cette application n'est pas l'outil qu'il faut pour ça.\n\n"
            "**Parle à quelqu'un maintenant :**\n\n"
            "- **3114** — prévention du suicide, France, gratuit, 24 h/24, 7 j/7\n"
            "- **15** (SAMU) ou **112** en cas d'urgence\n"
            "- Belgique 0800 32 123 · Suisse 143 · Canada 988\n\n"
            "L'analyse habituelle est suspendue. Elle reprendra quand tu voudras.",
        )

    checkins = by_id.get("assiduite_checkin", {})
    trend = by_id.get("tendance_anxiete", {})
    adherence = by_id.get("adherence", {})
    gad = by_id.get("gad7", {})

    lines.append("## Ce que tes données montrent\n")
    lines.append(
        f"- **{checkins.get('value', 0)} jour(s)** renseigné(s) sur la période "
        f"({sig['periode']['debut']} → {sig['periode']['fin']})."
    )
    if trend.get("value") is not None:
        delta_text = (
            "pas encore de comparaison possible"
            if trend.get("delta") is None
            else f"{trend['delta']:+.2f} point par rapport aux 7 jours précédents"
        )
        lines.append(
            f"- Anxiété moyenne des 7 derniers jours : **{trend['value']}/10** — {delta_text} "
            f"({trend.get('verdict')})."
        )
    if gad.get("value") is not None:
        lines.append(f"- GAD-7 : **{gad['verdict']}**.")
    if adherence.get("value") is not None:
        lines.append(
            f"- Activités réalisées : **{round(adherence['value'] * 100)} %** "
            f"({adherence.get('verdict')}, sur {adherence.get('n')} activités tracées)."
        )

    for sid in (
        "correlation_sommeil_anxiete",
        "correlation_qualite_sommeil",
        "correlation_cafeine_anxiete",
        "correlation_alcool_anxiete",
        "correlation_sport_anxiete",
    ):
        signal = by_id.get(sid, {})
        if signal.get("value") is not None and abs(signal["value"]) >= 0.25:
            lines.append(
                f"- {signal['label']} : coefficient **{signal['value']}** "
                f"({signal['verdict']}, {signal['n']} paires de jours). "
                "Attention : association, pas causalité."
            )

    lines.append("\n## Ce qui a été fait, et ce qui ne l'a pas été\n")
    effects = by_id.get("effet_mesure_activites", {})
    if effects.get("value"):
        for effect in effects["value"][:3]:
            lines.append(
                f"- `{effect['activite']}` : variation moyenne de l'anxiété "
                f"**{effect['delta_moyen']:+.2f}** point sur {effect['n']} mesures avant/après."
            )
    not_done = by_id.get("activites_non_faites", {})
    if not_done.get("value"):
        for slug, count in not_done["value"][:3]:
            lines.append(f"- `{slug}` : non fait **{count}** fois.")
        reasons = not_done.get("observations") or []
        if reasons:
            lines.append(
                "- Raisons que t'as notées : "
                + " ; ".join(f"« {r['raison']} »" for r in reasons[:3])
                + ". C'est une information utile, pas un échec : ça indique quel format ajuster."
            )
    else:
        lines.append("- Aucune activité marquée comme non faite sur la période.")

    exposures = by_id.get("expositions", {})
    lines.append("\n## Une hypothèse\n")
    hypotheses = 0
    sleep = by_id.get("correlation_sommeil_anxiete", {})
    if sleep.get("value") is not None and sleep["value"] <= -0.4:
        lines.append(
            "- Le sommeil apparaît comme un levier chez toi. La littérature va dans ce sens : "
            "dans une analyse de médiation sur deux grands essais randomisés, l'amélioration du "
            "sommeil médiait l'amélioration de l'anxiété."
        )
        hypotheses += 1
    if (exposures.get("value") or 0) == 0:
        lines.append(
            "- Aucune exposition enregistrée. C'est le module qui produit l'essentiel du "
            "changement durable : sans lui, on peut réduire la tension sans réduire l'évitement, "
            "et l'anxiété revient dès que le contexte redevient exigeant."
        )
        hypotheses += 1
    if adherence.get("value") is not None and adherence["value"] < 0.4:
        lines.append(
            "- Le taux de réalisation est bas. L'hypothèse la plus probable n'est pas un manque "
            "de volonté mais un programme mal calibré : trop long, mal placé dans la journée, ou "
            "trop peu relié à ce qui compte pour toi."
        )
        hypotheses += 1
    if hypotheses == 0:
        lines.append(
            "- Pas d'hypothèse solide à ce stade : il faut davantage de jours renseignés pour que "
            "les corrélations deviennent interprétables (minimum 6 paires de jours par signal)."
        )

    lines.append("\n## Pour les 7 prochains jours\n")
    lines.append(
        "- Socle non négociable : check-in quotidien (2 min) et respiration lente 10 min à heure fixe."
    )
    if (exposures.get("value") or 0) == 0:
        lines.append(
            "- Une exposition, une seule, à 4-6/10 sur ton échelle. Écris la prédiction avant, le "
            "résultat réel après."
        )
    if sleep.get("value") is not None and sleep["value"] <= -0.4:
        lines.append("- Heure de lever fixe, 7 jours sur 7, week-end compris.")
    if gad.get("value") is None:
        lines.append("- Remplis le GAD-7 une fois : sans ligne de base, il n'y a rien à suivre.")

    lines.append("\n## Ce que je ne peux pas savoir\n")
    lines.append(
        "- Cette analyse est **déterministe** : produite sans modèle de langage (aucune clé d'API "
        "configurée, ou consentement non donné). Elle décrit tes chiffres et applique des règles "
        "fixes ; elle ne lit pas le contenu de tes textes."
    )
    lines.append(
        f"- Elle porte sur {sig['periode']['jours']} jours et {checkins.get('value', 0)} jours "
        "réellement renseignés. En dessous de 14 jours, les tendances sont peu fiables."
    )
    lines.append(
        "- Elle ne remplace ni un diagnostic ni un suivi professionnel. Si ton GAD-7 est ≥ 15, ou "
        "s'il n'y a aucune amélioration après 6 à 8 semaines, l'étape suivante recommandée par NICE "
        "est une TCC accompagnée. Ce n'est pas un échec, c'est la suite prévue."
    )

    parts: list[str] = []
    if trend.get("value") is not None and trend.get("delta") is not None:
        parts.append(f"anxiété {trend['verdict']} à {trend['value']}/10 sur 7 jours")
    elif trend.get("value") is not None:
        parts.append(f"anxiété moyenne {trend['value']}/10")
    if adherence.get("value") is not None:
        parts.append(f"{round(adherence['value'] * 100)} % d'activités réalisées")
    if gad.get("value") is not None:
        parts.append(f"GAD-7 à {gad['value']}")
    joined = ", ".join(parts)
    # Majuscule sur la première lettre seulement : `capitalize()` mettrait
    # « GAD-7 » en minuscules.
    headline = (
        joined[0].upper() + joined[1:] if joined else "Pas encore assez de données pour conclure"
    )
    return headline, "\n".join(lines)


# --- Analyse LLM -------------------------------------------------------------

_TITLE_RE = re.compile(r"^\s*TITRE\s*:\s*(.+)$", re.IGNORECASE | re.MULTILINE)


def _split_title(text: str) -> tuple[str | None, str]:
    match = _TITLE_RE.search(text)
    if not match:
        return None, text.strip()
    title = match.group(1).strip().strip(".")
    body = text[: match.start()] + text[match.end() :]
    return title, body.strip()


async def analyze(
    user: dict[str, Any],
    scope: str = "quotidien",
    end_date: dt.date | None = None,
) -> dict[str, Any]:
    """Produit une analyse et la persiste. Ne lève pas : dégrade en local."""
    user_id = user["id"]
    # 14 jours minimum même pour l'analyse « quotidienne » : en dessous, la
    # comparaison 7 jours vs 7 jours précédents est impossible et les
    # corrélations n'atteignent pas les 6 paires requises.
    days = 14 if scope == "quotidien" else 28
    end = end_date or dt.date.today()

    sig = await asyncio.to_thread(signals_mod.compute, user_id, end, days)
    chunks = await asyncio.to_thread(retrieve, sig)
    citations = search.to_citations(chunks)

    ai_allowed = bool(user.get("ai_consent")) and settings.has_llm
    engine = "local"
    headline: str | None = None
    body: str

    if ai_allowed:
        context = search.build_context(chunks)
        system = SYSTEM_PROMPT + (SAFETY_PROMPT if sig["drapeaux_rouges"] else "")
        user_prompt = (
            f"PORTÉE DE L'ANALYSE : {scope}\n\n"
            f"{_format_signals(sig)}\n\n"
            f"EXTRAITS DU CORPUS (utilise leur numéro entre crochets pour citer) :\n\n{context}\n\n"
            + (
                "SIGNALEMENT : extraits ayant déclenché l'alerte sécurité : "
                + json.dumps(sig["drapeaux_rouges"], ensure_ascii=False)
                + "\n\n"
                if sig["drapeaux_rouges"]
                else ""
            )
            + "Rédige l'analyse en respectant strictement le format demandé."
        )
        try:
            result = await llm_client.complete(system, user_prompt)
            headline, body = _split_title(result.text)
            engine = result.engine + (" (fallback)" if result.fallback_used else "")
        except llm_client.LLMUnavailable as exc:
            logger.warning("LLM indisponible, analyse locale : %s", exc)
            headline, body = local_analysis(sig, chunks)
            engine = "local"
    else:
        headline, body = local_analysis(sig, chunks)
        engine = "local"
        if not user.get("ai_consent"):
            body += (
                "\n\n---\n\n*Analyse produite sans intelligence artificielle : vous n'avez pas "
                "activé l'envoi de vos données à un modèle de langage. Vous pouvez l'activer dans "
                "les réglages — le contenu de votre journal serait alors transmis à l'API du "
                "fournisseur.*"
            )

    recommendations = [
        {
            "slug": item["slug"],
            "pourquoi": item["why"],
            "declencheurs": item["triggered_by"],
        }
        for item in _recommendations_from_signals(sig, user)
    ]

    row = await asyncio.to_thread(
        db.execute_returning,
        """
        INSERT INTO insights (user_id, scope, period_start, period_end, headline, body,
                              signals, citations, recommendations, engine, risk_flag)
        VALUES (%(user_id)s, %(scope)s, %(start)s, %(end)s, %(headline)s, %(body)s,
                %(signals)s, %(citations)s, %(recommendations)s, %(engine)s, %(risk)s)
        RETURNING id::text, created_at
        """,
        {
            "user_id": user_id,
            "scope": scope,
            "start": sig["periode"]["debut"],
            "end": sig["periode"]["fin"],
            "headline": headline,
            "body": body,
            "signals": json.dumps(sig, ensure_ascii=False, default=str),
            "citations": json.dumps(citations, ensure_ascii=False, default=str),
            "recommendations": json.dumps(recommendations, ensure_ascii=False, default=str),
            "engine": engine,
            "risk": bool(sig["drapeaux_rouges"]),
        },
    )

    return {
        "id": row["id"] if row else "",
        "scope": scope,
        "period_start": sig["periode"]["debut"],
        "period_end": sig["periode"]["fin"],
        "headline": headline,
        "body": body,
        "signals": sig,
        "citations": citations,
        "recommendations": recommendations,
        "engine": engine,
        "risk_flag": bool(sig["drapeaux_rouges"]),
        "created_at": row["created_at"] if row else None,
    }


def _recommendations_from_signals(sig: dict[str, Any], user: dict[str, Any]) -> list[dict[str, Any]]:
    from .program import adaptive_items

    return adaptive_items(sig, user.get("profile") or {})


# --- Chat explicatif en streaming SSE ---------------------------------------


async def stream_explanation(
    user: dict[str, Any],
    question: str,
    include_my_data: bool = True,
    about_activity: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Génère des événements SSE : citations d'abord, puis les tokens.

    Envoyer les citations avant le texte permet à l'interface d'afficher les
    sources immédiatement : l'utilisateur voit sur quoi la réponse s'appuie
    pendant qu'elle s'écrit.
    """
    doc_ids = None
    if about_activity:
        row = await asyncio.to_thread(
            db.query_one, "SELECT kb_doc_id FROM activities WHERE slug = %s", (about_activity,)
        )
        if row and row.get("kb_doc_id"):
            doc_ids = [row["kb_doc_id"]]

    chunks = await asyncio.to_thread(
        lambda: search.hybrid_search(question, k=6, candidates=30, doc_ids=doc_ids)
    )
    if not chunks and doc_ids:
        chunks = await asyncio.to_thread(lambda: search.hybrid_search(question, k=6))

    citations = search.to_citations(chunks)
    yield {"event": "citations", "data": citations}

    if not settings.has_llm:
        yield {
            "event": "error",
            "data": (
                "Aucun modèle de langage n'est configuré sur ce serveur. Les fiches sources "
                "restent consultables dans la bibliothèque."
            ),
        }
        yield {"event": "done", "data": {"engine": "aucun"}}
        return

    context = search.build_context(chunks, max_chars=9000)
    parts = [f"QUESTION DE L'UTILISATEUR :\n{question}\n"]

    if include_my_data and user.get("ai_consent"):
        sig = await asyncio.to_thread(signals_mod.compute, user["id"], dt.date.today(), 21)
        parts.append(f"\nSIGNAUX DE L'UTILISATEUR :\n{_format_signals(sig)}\n")
        if sig["drapeaux_rouges"]:
            yield {
                "event": "safety",
                "data": {
                    "message": (
                        "Des formulations préoccupantes ont été repérées dans vos entrées "
                        "récentes. Si vous avez des idées suicidaires, appelez le 3114 "
                        "(France, gratuit, 24 h/24) ou le 15."
                    ),
                    "ressources": signals_mod.CRISIS_RESOURCES,
                },
            }
    elif include_my_data:
        parts.append(
            "\n(L'utilisateur n'a pas consenti à l'envoi de ses données personnelles : réponds "
            "uniquement à partir du corpus, sans faire référence à ses données.)\n"
        )

    parts.append(f"\nEXTRAITS DU CORPUS :\n\n{context}\n")
    user_prompt = "".join(parts)

    engine = "inconnu"
    async for kind, value in llm_client.stream(CHAT_SYSTEM_PROMPT, user_prompt):
        if kind == "engine":
            engine = value
            yield {"event": "engine", "data": value}
        elif kind == "token":
            yield {"event": "token", "data": value}
        elif kind == "error":
            yield {"event": "error", "data": value}
    yield {"event": "done", "data": {"engine": engine}}
