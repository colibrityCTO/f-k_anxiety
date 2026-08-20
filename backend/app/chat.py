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
from . import db, llm_client, memory, next_step, program, search, signals as signals_mod
from .config import settings

logger = logging.getLogger(__name__)

# Ce que le modèle a le droit d'ouvrir. Volontairement plus court que
# `WidgetType` côté front : ce dernier doit encore savoir **rendre** `checkin`,
# `account` et `logout`, parce que des items de ces types dorment dans les fils
# existants et que le passé ne se réécrit pas. Mais plus rien ne doit en **créer**
# — le compte a sa page en haut à droite, et le check-in unique est découpé en
# trois depuis la V5. Une consigne en langue naturelle dans le prompt ne suffisait
# pas : c'est une liste blanche, vérifiée par `_sanitise`.
WIDGET_TYPES = {
    "breath", "journal", "gad7", "stats", "analysis", "sources",
    "exposition", "meditation", "memoire", "echelles",
    "interoceptif", "rapport",
    "matin", "soir", "maintenant",
    # Charge du jour et prévision : une consultation, elle n'écrit rien.
    "prevision",
    # `panique` et `onboarding` ne sont **pas** dans cette liste, et c'est le point :
    # elle ne sert qu'à filtrer la sortie du modèle. Le récapitulatif d'épisode est
    # déposé par QUICK CHILL une fois la crise passée, le questionnaire initial une
    # seule fois à la première ouverture — les deux par des chemins déterministes qui
    # ne passent pas par `_sanitise`. Les laisser ici n'aurait servi qu'à autoriser
    # le modèle à rouvrir un questionnaire de trois minutes au milieu d'une phrase.
    # `jour` n'y est plus : le parcours vit sous le titre, en permanence, et n'est
    # plus déposé dans le fil. À la question « qu'est-ce que je dois faire », le
    # modèle répond en texte et renvoie au bandeau — ouvrir un widget pour montrer
    # ce qui est déjà affiché en haut de l'écran serait un doublon.
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

Le parcours du jour n'est pas un widget : il est affiché en permanence sous le titre, et l'utilisateur le déplie d'un geste. Si on te demande ce qu'il y a à faire aujourd'hui, réponds en une phrase et dis-lui que le détail est en haut de l'écran.

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

    # Nombre de jours réellement notés. Sert de garde à tout ce qui n'a de sens
    # qu'avec de l'historique : proposer « mes chiffres » au deuxième jour affiche
    # une courbe de deux points, ce qui n'est pas une courbe.
    logged = db.query_one(
        "SELECT count(DISTINCT entry_date) AS n FROM daily_checkins WHERE user_id = %s",
        (user_id,),
    )

    # --- Le socle du jour, et lui seul -------------------------------------
    #
    # Ce qui est *attendu* aujourd'hui, par opposition à ce qui est *proposé*. La
    # distinction porte toute la barre de progression : « Mon parcours » affichait
    # `fait / total` sur les cinq à huit items du programme tout en écrivant, deux
    # écrans plus bas, qu'un seul était attendu. Quelqu'un qui avait fait exactement
    # ce qu'on lui demandait lisait donc « 1/7 » — la barre annonçait un échec
    # pendant que le contrat annonçait une réussite.
    #
    # Le socle est le contrat : la saisie du jour, la respiration, le journal. Le
    # reste est proposé, montré dans le parcours, et ne pèse pas.
    socle = _socle_progress(user_id, today, moments)

    # Le check-in a-t-il été explicitement refusé aujourd'hui ? Lu dans
    # `activity_logs` et non dans le fil : c'est la table que `_log_skip` alimente, et
    # celle sur laquelle tous les signaux se calculent.
    refus = db.query_one(
        """
        SELECT 1 FROM activity_logs
        WHERE user_id = %s AND entry_date = %s
          AND activity_slug = 'checkin-quotidien' AND status = 'reporte'
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
        "jours_notes": int(logged["n"]) if logged else 0,
        "socle": socle,
        "saisie_reportee": refus is not None,
    }


# Le socle quotidien, en un seul endroit. `program.build_day` compose sa liste à
# partir des mêmes slugs ; les faire diverger produirait une barre qui ne compte pas
# ce que le parcours affiche.
SOCLE_SLUGS: tuple[str, ...] = ("checkin-quotidien", "respiration-lente-10", "journal-libre")

SOCLE_LABELS: dict[str, str] = {
    "checkin-quotidien": "Noter",
    "respiration-lente-10": "Respirer",
    "journal-libre": "Écrire",
}


def _socle_progress(
    user_id: str, today: dt.date, moments: dict[str, Any], now: dt.datetime | None = None
) -> dict[str, Any]:
    """Où en est le contrat du jour : trois lignes, faites ou pas.

    Le check-in ne se lit pas dans `activity_logs` mais dans `daily_checkins` : c'est
    la table qui porte la donnée, et le journal d'activités n'en est qu'un reflet
    écrit par le gestionnaire. Se fier au reflet, c'était afficher « pas fait » si
    l'écriture secondaire échouait.

    Et la ligne « Noter » suit le **créneau en cours**, pas la journée entière. Le
    faire autrement produisait une contradiction visible : à vingt heures, quelqu'un
    qui avait noté sa nuit le matin lisait « fait » dans la barre pendant que le fil,
    juste en dessous, lui réclamait sa journée. `checkin_done` reste vrai dans les
    deux cas — c'est la bonne sémantique pour les signaux, qui ont besoin d'une ligne
    par jour, pas d'une ligne par moment.
    """
    hour = (now or dt.datetime.now()).hour
    saisie_due = "soir" if hour >= EVENING_FROM else "matin"
    rows = {
        row["activity_slug"]: row["status"]
        for row in db.query_all(
            """
            SELECT activity_slug, status FROM activity_logs
            WHERE user_id = %s AND entry_date = %s AND activity_slug = ANY(%s)
            """,
            (user_id, today, list(SOCLE_SLUGS)),
        )
    }
    items = []
    for slug in SOCLE_SLUGS:
        done = (
            saisie_due in moments
            if slug == "checkin-quotidien"
            else rows.get(slug) in {"fait", "partiel"}
        )
        items.append({"slug": slug, "label": SOCLE_LABELS[slug], "fait": done})
    return {
        "items": items,
        "fait": sum(1 for item in items if item["fait"]),
        "total": len(items),
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
            "suggestions": [],
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
    if "jour" in intents:
        return {
            "reply": (
                "Ton parcours du jour est en haut de l'écran, sous le titre : les trois "
                "lignes du socle, et le détail complet en dépliant."
            ),
            "widget": None,
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


def _fill_suggestions(decision: dict[str, Any], state: dict[str, Any]) -> None:
    """Complète les propositions jusqu'à trois, sur l'état réel du jour.

    Vaut pour les deux chemins : le modèle en renvoie souvent zéro ou une, et le
    repli déterministe en écrivait des constantes. Ce qui vient du modèle est
    conservé et passe devant — il a lu le message, il sait des choses que l'état du
    jour ignore. Le classeur ne fait que remplir les places restantes.
    """
    widget = decision.get("widget")
    exclude = {widget["type"]} if widget else set()
    existing = [s for s in (decision.get("suggestions") or [])]
    for label in next_step.suggestions_for(state, None, exclude=exclude):
        if label not in existing and len(existing) < 3:
            existing.append(label)
    decision["suggestions"] = existing


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
    _fill_suggestions(decision, context["state"])
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
        _fill_suggestions(decision, context["state"])
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
    _fill_suggestions(decision, context["state"])

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


# La table activité → widget vit dans `program.py`, où `build_day` en a besoin pour
# que chaque item du jour sache ce qu'il ouvre. Deux copies auraient fini par
# diverger, et c'est le genre de divergence qui ne lève aucune erreur.
SLUG_WIDGETS = program.SLUG_WIDGETS


# `_citation_for`, `_decision_for_item` et `_todays_proposal` ont quitté ce fichier.
# Les deux premiers vivent désormais dans `program.citation_for` et
# `next_step._from_plan` ; le troisième n'existe plus du tout. Il ne regardait que
# deux créneaux du programme sur quatre — le socle et la pratique corporelle
# n'étaient jamais proposés dans le fil, ce qui produisait des « rien à faire
# aujourd'hui » alors que quatre activités calculées le matin même attendaient.
# Le classement complet est dans `next_step.choose`, et il ne rend jamais `None`.


# Les trois créneaux d'ouverture proactive. Un dépôt par créneau, au plus.
#
# Pourquoi trois et pas un : avec un seul dépôt par jour, ouvrir l'application à 9 h
# consommait l'unique message, et revenir à 20 h ne proposait plus rien — alors que
# c'est le soir que la journée se raconte.
#
# Pourquoi pas plus : les invites contextuelles tiennent l'engagement, mais l'adhésion
# se dégrade vite (90 % d'usage en semaine 3, 59 % en semaine 6 dans un essai à
# randomisation micro). Trois est un plafond, pas une cible — et le créneau du milieu
# de journée ne demande rien à remplir, il pose une question.
SLOTS: list[tuple[str, int, int]] = [
    ("matin", 5, 12),
    ("midi", 12, 17),
    ("soir", 17, 24),
]


def slot_for(now: dt.datetime | None = None) -> str | None:
    """Dans quel créneau on se trouve, ou `None` la nuit (0 h - 5 h).

    La nuit ne déclenche rien : quelqu'un qui ouvre l'application à 3 h n'a pas besoin
    d'une question sur sa journée, et le créneau du matin l'attendra au réveil.
    """
    hour = (now or dt.datetime.now()).hour
    for name, low, high in SLOTS:
        if low <= hour < high:
            return name
    return None


# Bornes des deux créneaux de saisie. Avant midi, c'est le matin ; à partir de 17 h, le soir.
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


# --- La question du milieu de journée ---------------------------------------
#
# Liste fermée, tirée de façon **déterministe** : même jour, même question. Pas de
# modèle de langage, et c'est un choix, pas une économie. Une question générée serait
# différente à chaque rechargement, donc impossible à reprendre, et rien ne
# garantirait qu'elle reste dans le cadre — alors que le tirage, lui, est vérifiable.
#
# Chacune est rattachée à un module : on ne demande pas à quelqu'un en semaine 2 ce
# qu'il a appris de sa dernière exposition. `None` signifie « valable partout ».
MIDDAY_QUESTIONS: list[dict[str, Any]] = [
    {"module": None, "q": "Qu'est-ce que tu as évité aujourd'hui, même une petite chose ?"},
    {"module": None, "q": "À quel moment ça a été le pire, et qu'est-ce qui se passait juste avant ?"},
    {"module": None, "q": "Qu'est-ce que tu as fait aujourd'hui qui compte pour toi, même en étant anxieux ?"},
    {"module": None, "q": "Si un ami te racontait ta matinée, tu lui dirais quoi ?"},
    {"module": 2, "q": "Là, tu peux repérer les trois composantes : la pensée, la sensation, le comportement ?"},
    {"module": 3, "q": "Quelle sensation physique est la plus présente en ce moment ?"},
    {"module": 4, "q": "Quelle pensée tourne le plus aujourd'hui, et tu y crois à combien sur 100 ?"},
    {"module": 4, "q": "Le pire scénario du moment : c'est déjà arrivé, une seule fois ?"},
    {"module": 5, "q": "Quel geste tu as fait aujourd'hui pour te rassurer, sans en avoir besoin ?"},
    {"module": 6, "q": "Les sensations que tu redoutes : lesquelles as-tu senties aujourd'hui, sans crise ?"},
    {"module": 7, "q": "Qu'est-ce que tu as appris de ta dernière exposition, que tu ne savais pas avant ?"},
    {"module": 8, "q": "Qu'est-ce qui, si tu l'arrêtais, te ferait rechuter en premier ?"},
]


def midday_question(module: int, day: dt.date) -> str:
    """Tire la question du jour. Stable dans la journée, différente le lendemain.

    Le tirage combine la date et le module : recharger l'application ne change pas la
    question — sinon on ne pourrait pas y revenir après l'avoir laissée de côté.
    """
    pool = [q["q"] for q in MIDDAY_QUESTIONS if q["module"] in (None, module)]
    return pool[day.toordinal() % len(pool)]


def onboarding_opening(user: dict[str, Any]) -> dict[str, Any]:
    """Le tout premier message. Il annonce le coût et ce que ça change.

    « Trois minutes » est dit parce que c'est vrai et parce que ne pas le dire fait
    abandonner au troisième écran. Et la raison est donnée avant les questions : un
    questionnaire dont on ne sait pas à quoi il sert se remplit mal, ou pas.
    """
    name = (user.get("display_name") or "").strip()
    hello = f"Salut {name}." if name else "Salut."
    return {
        "reply": (
            f"{hello} Avant de commencer : trois minutes de questions, une fois.\n\n"
            "Ça sert à deux choses concrètes. **Adapter le programme** — si la panique "
            "est ta difficulté principale, les exercices sur les sensations arrivent tôt "
            "au lieu d'attendre huit semaines. Et **poser une ligne de base chiffrée** : "
            "sans elle, impossible de dire dans six semaines si quelque chose a marché, "
            "parce que la mémoire sous anxiété ne retient que les pires moments."
        ),
        "widget": {"type": "onboarding", "prefill": {}, "a_verifier": []},
        "suggestions": [],
        "citations": [],
        "engine": "local",
    }


def opening_for_slot(user: dict[str, Any], slot: str) -> dict[str, Any]:
    """L'ouverture du créneau. Trois régimes distincts, pas trois variantes du même.

    - **matin** et **soir** proposent la première étape que le classeur retient.
    - **midi** ne demande rien à remplir. C'est une question, et une seule. Réclamer un
      troisième formulaire en milieu de journée aurait fait abandonner les deux autres.
    """
    if slot != "midi":
        return opening(user)

    state = day_state(user["id"])
    today = dt.date.today()
    question = midday_question(state["module"], today)

    # Le journal libre est proposé pour recueillir la réponse : elle ira en mémoire
    # vectorisée, donc elle sera retrouvable des mois plus tard. Une question posée
    # sans endroit pour répondre est une question perdue.
    #
    # Les propositions sont calculées, plus écrites en dur. L'ancienne paire
    # « Rien à signaler / Comment je me sens là » offrait une porte de sortie avant
    # même de savoir s'il y avait matière, et « Rien à signaler » repartait en message
    # libre vers le modèle : un appel payant pour n'enregistrer strictement rien.
    return {
        "reply": question,
        "widget": {
            "type": "journal",
            "prefill": {"situation": question},
            "a_verifier": [],
        },
        "suggestions": next_step.suggestions_for(state, None, exclude={"journal"}),
        "citations": [],
        "engine": "question-du-jour",
    }


def opening(user: dict[str, Any]) -> dict[str, Any]:
    """Message d'ouverture du jour. Déterministe : rapide, gratuit, prévisible.

    Ce n'est plus une cascade de cas particuliers mais un habillage du classeur :
    la salutation et la reprise du chiffre du jour d'un côté, le choix de l'étape
    de l'autre. Le partage compte — l'ancienne cascade se terminait sur trois
    impasses (« rien à faire aujourd'hui », « tu veux faire quoi ? ») parce que
    chacune de ses branches devait prévoir son propre repli. Le classeur, lui, en
    a un seul, et il n'est jamais vide.
    """
    state = day_state(user["id"])
    name = (user.get("display_name") or "").strip()
    hello = f"Salut {name}." if name else "Salut."

    # Une séance intense hier, et rien de noté depuis : on demande. C'est ce qui
    # remplace la détection automatique de crise — impossible avec l'API Whoop, qui
    # n'expose aucune série de fréquence cardiaque, et de toute façon indésirable :
    # une fausse alerte de panique est un déclencheur de panique.
    #
    # Traité avant le classeur et non dedans : c'est un événement daté d'hier, il
    # périme, et il ne se range pas dans un ordre de priorité stable.
    session = _intense_session_yesterday(user["id"])
    if session is not None:
        session.setdefault("citations", [])
        session["suggestions"] = next_step.suggestions_for(state, None)
        return session

    step = next_step.choose(user, state)

    # La salutation ne s'ajoute qu'au premier créneau de la journée — celui où rien
    # n'est encore noté. Dire « salut » le soir à quelqu'un qui a déjà écrit trois
    # fois dans la journée sonne comme une application qui ne suit pas.
    if not state["checkin_done"] and state["mesures_instantanees"] == 0:
        step["reply"] = f"{hello} {step['reply']}"
    elif state["anxiety_today"] is not None:
        step["reply"] = f"Check-in fait (anxiété **{state['anxiety_today']}/10**). {step['reply']}"

    return step
