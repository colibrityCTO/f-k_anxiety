"""Le classeur : ce que l'application a à proposer, maintenant.

Un seul endroit décide. Avant, trois surfaces répondaient à la même question sans
se parler — la cascade d'ouverture de `chat.py`, `build_day()` de `program.py`, et
la grille de widgets du front. Elles se contredisaient : `build_day` calculait cinq
à huit items justifiés, l'ouverture n'en regardait que deux catégories sur quatre,
et le reste du temps l'application disait « rien à faire aujourd'hui » alors que le
socle du jour était intégralement vide.

Le classement est **déterministe et ordonné**. Aucune décision n'est laissée au
modèle : il ne choisit pas ce qu'il y a à faire, il n'en écrit même pas la
justification — `program.py` la produit déjà avec les chiffres de la personne. Ce
qui se gagne : c'est testable, c'est gratuit, c'est reproductible, et ça ne peut
pas inventer une activité qui n'existe pas.

Le contrat tenu, et c'est le point : **`choose()` ne renvoie jamais `None`**. Il y a
toujours une étape suivante — une saisie due, un exercice du programme, une question
dont la réponse manque encore, ou une fiche du corpus jamais lue. « Reviens demain »
n'est plus un état atteignable.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from . import db, program

logger = logging.getLogger("fuck_anxiety.next_step")

# Le soir commence à 17 h — même borne que `chat._moment_due`, et pour la même
# raison : à midi la journée n'est pas finie, la faire résumer produit un chiffre
# faux. Importée depuis `chat` serait circulaire ; redéfinie ici et vérifiée par
# `tests/smoke_v5_next_step.py`.
EVENING_FROM = 17


# --- Utilitaires -------------------------------------------------------------


def _decision(
    reply: str,
    widget: dict[str, Any] | None,
    *,
    engine: str,
    citations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Le format commun à toutes les étapes. Les suggestions sont ajoutées après.

    Elles ne peuvent pas l'être ici : elles dépendent de ce que l'étape choisie
    occupe déjà, donc elles se calculent une fois l'étape connue.
    """
    return {
        "reply": reply,
        "widget": widget,
        "suggestions": [],
        "citations": citations or [],
        "engine": engine,
    }


def _widget(widget_type: str, prefill: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"type": widget_type, "prefill": prefill or {}, "a_verifier": []}


# --- Questions ouvertes ------------------------------------------------------
#
# Ce que l'application ne sait pas encore, et qui changerait ce qu'elle propose.
#
# Chaque question porte trois choses : une condition vérifiable en base, un endroit
# où la réponse s'enregistre, et une raison. Le troisième point est ce qui les
# distingue d'un questionnaire : une question dont la réponse ne sert à rien n'a
# pas à être posée, et une question sans widget derrière est une question perdue —
# la réponse partirait dans un message libre et ne serait jamais structurée.


def _open_questions(
    user_id: str, profile: dict[str, Any], state: dict[str, Any], today: dt.date
) -> list[dict[str, Any]]:
    """Les trous du dossier, dans l'ordre où ça vaut la peine de les combler."""
    week = state["week"]
    module = state["module"]
    out: list[dict[str, Any]] = []

    # 1. L'échelle d'expositions vide. C'est le trou le plus coûteux : sans elle,
    #    le module 7 — celui qui produit l'essentiel du changement durable — n'a
    #    aucune matière. On ne l'attend pas la semaine 9 pour la construire.
    if week >= 3:
        rows = db.query_one(
            "SELECT count(*) AS n FROM exposure_items WHERE user_id = %s", (user_id,)
        )
        if not rows or int(rows["n"]) == 0:
            out.append(
                {
                    "id": "echelle_vide",
                    "reply": (
                        "Ton échelle d'expositions est vide, et c'est la seule chose qui me "
                        "manque vraiment. Cite une situation que tu évites — même une petite. "
                        "C'est elle qui servira de matière au module 7, et le construire "
                        "maintenant évite de s'y mettre en urgence semaine 9."
                    ),
                    "widget": _widget("exposition"),
                }
            )

    # 2. Les contextes jamais renseignés. Sans eux, aucun signal ne peut dire *où*
    #    l'anxiété monte — et « où » est la question qui rend une exposition
    #    concevable, là où un chiffre seul ne mène nulle part.
    if week >= 2:
        ctx = db.query_one(
            """
            SELECT count(*) AS n FROM daily_checkins
            WHERE user_id = %s AND contexts IS NOT NULL AND array_length(contexts, 1) > 0
            """,
            (user_id,),
        )
        if not ctx or int(ctx["n"]) == 0:
            out.append(
                {
                    "id": "contextes_vides",
                    "reply": (
                        "Tes chiffres montrent *combien*, jamais *où*. Note-moi ton niveau là, "
                        "maintenant, en cochant le contexte : au bout de deux semaines je peux "
                        "te dire quelles situations reviennent, et c'est ça qui rend une "
                        "exposition concevable."
                    ),
                    "widget": _widget("maintenant"),
                }
            )

    # 3. Aucun journal de pensées alors que le module cognitif est commencé. Le
    #    module 4 ne produit rien sans lui : la restructuration se mesure sur
    #    l'écart intensité avant / après, qui n'existe que dans ce format.
    if module >= 4:
        pensee = db.query_one(
            "SELECT count(*) AS n FROM journal_entries WHERE user_id = %s AND kind = 'pensee'",
            (user_id,),
        )
        if not pensee or int(pensee["n"]) == 0:
            out.append(
                {
                    "id": "pensees_vides",
                    "reply": (
                        "Tu es au module cognitif et je n'ai encore aucun journal de pensées. "
                        "C'est le seul format qui mesure si la restructuration marche chez toi : "
                        "l'intensité avant, l'intensité après. Une seule pensée suffit pour "
                        "commencer."
                    ),
                    "widget": _widget("journal", {"kind": "pensee"}),
                }
            )

    # 4. La panique déclarée à l'inscription, jamais un seul épisode enregistré.
    #    Deux explications possibles, opposées, et on ne peut pas trancher sans
    #    demander : soit il n'y en a pas eu, soit elles ne sont pas notées.
    if "panique" in (profile.get("difficultes") or []) and week >= 2:
        episodes = db.query_one(
            "SELECT count(*) AS n FROM panic_episodes WHERE user_id = %s", (user_id,)
        )
        if not episodes or int(episodes["n"]) == 0:
            out.append(
                {
                    "id": "paniques_non_notees",
                    "reply": (
                        "Tu as mis la panique en tête de tes difficultés, et je n'ai aucun "
                        "épisode enregistré depuis le début. Deux lectures opposées : soit il "
                        "n'y en a pas eu — c'est une donnée —, soit elles passent sans être "
                        "notées. Raconte-moi la dernière, même de mémoire."
                    ),
                    "widget": _widget("journal", {"kind": "libre"}),
                }
            )

    # 5. Le PHQ-2 mensuel. L'humeur basse change ce qui est proposé, et elle se
    #    déplace indépendamment de l'anxiété : la mesurer une fois à l'inscription
    #    ne dit rien de ce qu'elle fait deux mois plus tard.
    last_phq = db.query_one(
        """
        SELECT taken_on FROM assessments
        WHERE user_id = %s AND instrument = 'phq2' ORDER BY taken_on DESC LIMIT 1
        """,
        (user_id,),
    )
    if last_phq and (today - last_phq["taken_on"]).days >= 30:
        out.append(
            {
                "id": "phq2_du",
                "reply": (
                    "Le PHQ-2 date d'il y a plus d'un mois. Deux questions, trente secondes : "
                    "l'humeur se déplace indépendamment de l'anxiété, et elle change ce que "
                    "j'ai à te proposer."
                ),
                "widget": _widget("echelles", {"instrument": "phq2"}),
            }
        )

    return out


# --- Micro-leçons ------------------------------------------------------------


def _lesson(user_id: str, state: dict[str, Any], today: dt.date) -> dict[str, Any] | None:
    """Une fiche du corpus jamais lue, la plus proche du module en cours.

    C'est le dernier recours du classeur, et c'est celui qui garantit qu'il n'y a
    jamais rien à dire : trente fiches, une par jour au maximum, il y a de quoi
    tenir un mois sans jamais se répéter même quand tout le reste est fait.

    Les fiches déjà proposées sont marquées dans `notification_log` — la table porte
    déjà la contrainte d'unicité `(user_id, kind, sent_on)`, et son `kind` est du
    texte libre. Inventer une seconde table de suivi aurait créé un second endroit
    où se tromper.
    """
    seen = {
        row["kind"][6:]
        for row in db.query_all(
            "SELECT DISTINCT kind FROM notification_log WHERE user_id = %s AND kind LIKE 'lecon:%%'",
            (user_id,),
        )
    }
    module = state["module"]
    docs = db.query_all(
        """
        SELECT d.doc_id, d.title, d.evidence_level, d.up_module, d.sources,
               c.heading, c.content
        FROM kb_documents d
        LEFT JOIN kb_chunks c ON c.document_id = d.id AND c.chunk_index = 0
        ORDER BY d.up_module NULLS LAST, d.doc_id
        """
    )
    candidates = [d for d in docs if d["doc_id"] not in seen]
    if not candidates:
        return None

    # La plus proche du module en cours d'abord : lire la fiche sur l'exposition
    # situationnelle en semaine 2 n'aide personne. `up_module` peut être nul — une
    # fiche transversale —, auquel cas elle est classée après, mais elle reste
    # atteignable.
    def distance(doc: dict[str, Any]) -> tuple[int, int, str]:
        up = doc.get("up_module")
        return (0 if up is not None else 1, abs((up or 0) - module), doc["doc_id"])

    doc = sorted(candidates, key=distance)[0]

    # La marque est posée à la proposition, pas à la lecture : sinon la même fiche
    # reviendrait à chaque tour tant qu'elle n'est pas ouverte, et le classeur
    # tournerait en rond au lieu d'avancer dans le corpus.
    db.execute(
        """
        INSERT INTO notification_log (user_id, kind, sent_on, detail)
        VALUES (%s, %s, %s, %s::jsonb)
        ON CONFLICT (user_id, kind, sent_on) DO NOTHING
        """,
        (user_id, f"lecon:{doc['doc_id']}", today, '{"origine": "classeur"}'),
    )

    extract = _first_paragraph(doc.get("content") or "", skip=doc.get("heading"))
    level = f" · niveau de preuve {doc['evidence_level']}" if doc.get("evidence_level") else ""
    reply = (
        f"Rien n'est dû là tout de suite, alors on avance sur autre chose : "
        f"**{doc['title']}**{level}.\n\n{extract}\n\n"
        "La fiche entière est ouverte en dessous — c'est exactement ce que je lis, "
        "sans rien d'ajouté."
    )
    return _decision(
        reply,
        _widget("sources", {"doc_id": doc["doc_id"]}),
        engine="lecon",
        citations=[
            {
                "doc_id": doc["doc_id"],
                "title": doc["title"],
                "evidence_level": doc.get("evidence_level"),
                "sources": doc.get("sources") or [],
            }
        ],
    )


def _first_paragraph(content: str, limit: int = 420, skip: str | None = None) -> str:
    """Le premier paragraphe utile d'une fiche, coupé sur une phrase entière.

    Deux pièges évités. Le titre de section est répété en tête du contenu du chunk,
    **sans dièse** — le filtrer sur la syntaxe Markdown ne suffisait pas, et l'extrait
    proposé se réduisait à « Ce que c'est ». On écarte donc explicitement le libellé
    du chunk. Et couper au caractère près produisait des extraits tronqués en plein
    milieu d'un mot, ce qui se lit comme un bug d'affichage plutôt que comme une
    citation.
    """
    heading = (skip or "").strip().lower()
    for block in content.split("\n\n"):
        text = block.strip()
        if not text or text.startswith("#") or text.startswith("---"):
            continue
        if heading and text.lower() == heading:
            continue
        if len(text) <= limit:
            return text
        cut = text[:limit]
        stop = max(cut.rfind(". "), cut.rfind(" ! "), cut.rfind(" ? "))
        return (cut[: stop + 1] if stop > limit // 2 else cut.rstrip()) + " […]"
    return ""


# --- Explications ------------------------------------------------------------
#
# Ce qui s'apprend, par opposition à ce qui se fait. Deux règles :
#
# **Une seule à la fois.** Empiler la théorie du module et le mécanisme d'un exercice
# dans le même tour produit un mur de texte, et un mur de texte ne se lit pas.
#
# **Jamais deux fois la même**, sauf raison de sécurité. Le programme reproposait la
# justification du module à l'identique chaque jour pendant une à trois semaines —
# « Semaine 4, module 3 — Observer sans fuir. Apprendre à rester avec une émotion. »,
# tous les matins. Une phrase répétée quinze fois cesse d'être lue, puis fait
# soupçonner que rien n'est vraiment personnalisé. Ce qui est déjà dit n'est plus dit.
#
# Le suivi passe par `notification_log`, dont le `kind` est du texte libre et qui porte
# déjà la contrainte d'unicité. Même mécanique que les fiches du corpus : inventer une
# table de plus aurait créé un endroit de plus où se tromper.

# Délai minimum avant de rejouer une explication, en jours. `None` : jamais rejouée.
EXPLANATION_TTL: dict[str, int | None] = {
    "module": None,
    "activite": None,
    # Les contre-indications font exception, et c'est la seule. Un exercice
    # d'hyperventilation volontaire n'a pas les mêmes réserves selon l'état de santé
    # du moment, et « tu l'as lu il y a six mois » n'est pas une garantie utile.
    "securite": 30,
}


def _last_seen(user_id: str, kind: str) -> dt.date | None:
    row = db.query_one(
        "SELECT max(sent_on) AS jour FROM notification_log WHERE user_id = %s AND kind = %s",
        (user_id, kind),
    )
    return row["jour"] if row and row["jour"] else None


def _mark_seen(user_id: str, kind: str, today: dt.date) -> None:
    db.execute(
        """
        INSERT INTO notification_log (user_id, kind, sent_on, detail)
        VALUES (%s, %s, %s, '{"origine": "explication"}'::jsonb)
        ON CONFLICT (user_id, kind, sent_on) DO NOTHING
        """,
        (user_id, kind, today),
    )


def _due(user_id: str, family: str, ident: str, today: dt.date) -> str | None:
    """La clé de suivi si l'explication est à montrer, sinon `None`."""
    kind = f"explication:{family}:{ident}"
    last = _last_seen(user_id, kind)
    if last is None:
        return kind
    ttl = EXPLANATION_TTL.get(family)
    if ttl is None:
        return None
    return kind if (today - last).days >= ttl else None


def _doc_explanation(user_id: str, doc_id: str, today: dt.date) -> dict[str, Any] | None:
    """Une fiche du corpus servie comme explication, jamais deux fois.

    Sert les étapes qui ne portent pas d'activité — la saisie du créneau, le GAD-7,
    les questions ouvertes. Sans elle, ces étapes-là n'auraient jamais rien à
    expliquer, alors que ce sont les plus fréquentes : le check-in revient tous les
    jours, et personne ne lui a jamais dit pourquoi.
    """
    kind = _due(user_id, "fiche", doc_id, today)
    if not kind:
        return None
    doc = db.query_one(
        """
        SELECT d.title, d.evidence_level, c.heading, c.content
        FROM kb_documents d
        LEFT JOIN kb_chunks c ON c.document_id = d.id AND c.chunk_index = 0
        WHERE d.doc_id = %s
        """,
        (doc_id,),
    )
    if not doc:
        return None
    _mark_seen(user_id, kind, today)
    level = f" · niveau de preuve {doc['evidence_level']}" if doc.get("evidence_level") else ""
    return {
        "titre": f"{doc['title']}{level}",
        "corps": _first_paragraph(doc.get("content") or "", skip=doc.get("heading")),
        "kind": kind,
    }


def explanation_for(
    user_id: str, state: dict[str, Any], step: dict[str, Any], today: dt.date
) -> dict[str, Any] | None:
    """L'explication qui accompagne une proposition, ou `None`.

    Elle est déposée **à côté** de la proposition, pas dedans : c'est un autre registre
    — ce qu'il faut comprendre, contre ce qu'il y a à faire —, et l'écran les
    distingue visuellement. Les mélanger dans un même paragraphe est ce qui rendait la
    justification du module illisible : la théorie de la semaine et l'instruction du
    jour tenaient dans la même phrase, répétée tous les matins.
    """
    activity = step.get("activity") or {}

    # 1. La théorie du module, une fois, à l'entrée dans le module. Ce texte existait
    #    déjà — `MODULES[].explainer`, huit blocs écrits, exposés par l'API sous
    #    `phase_explainer` — et n'était affiché nulle part.
    kind = _due(user_id, "module", str(state["module"]), today)
    if kind:
        module = program.module_for_week(state["week"])
        _mark_seen(user_id, kind, today)
        return {
            "titre": f"Module {module['module']} — {module['title']}",
            "corps": module["explainer"],
            "kind": kind,
        }

    # 2. Le mécanisme de l'exercice proposé, la première fois qu'il l'est. C'est ce
    #    qui distingue deux exercices d'un même module, là où la justification du
    #    module les confond.
    if activity.get("mechanism"):
        kind = _due(user_id, "activite", activity["slug"], today)
        if kind:
            _mark_seen(user_id, kind, today)
            level = activity.get("evidence_level")
            return {
                "titre": f"Pourquoi {activity['title'].lower()}"
                + (f" · niveau de preuve {level}" if level else ""),
                "corps": activity["mechanism"],
                "kind": kind,
            }

    # 3. Les contre-indications, rappelées. La seule chose qu'on répète volontairement.
    if activity.get("contraindications"):
        kind = _due(user_id, "securite", activity["slug"], today)
        if kind:
            _mark_seen(user_id, kind, today)
            return {
                "titre": "À vérifier avant de commencer",
                "corps": activity["contraindications"],
                "kind": kind,
            }

    # 4. À défaut d'activité, la fiche du corpus que l'étape désigne. Les étapes les
    #    plus fréquentes sont justement celles qui n'ouvrent aucune activité du
    #    catalogue — le check-in du matin, le GAD-7 —, et sans ce recours elles
    #    n'auraient jamais rien à expliquer.
    doc_id = step.get("explain_doc")
    if doc_id:
        return _doc_explanation(user_id, str(doc_id), today)

    return None


# --- Suggestions -------------------------------------------------------------


def suggestions_for(
    state: dict[str, Any],
    plan: dict[str, Any] | None,
    *,
    exclude: set[str] | None = None,
    now: dt.datetime | None = None,
) -> list[str]:
    """Les propositions de la barre, calculées sur l'état réel.

    Elles étaient constantes, écrites en dur à six endroits, et donc régulièrement
    fausses : « Mes chiffres » au premier jour alors qu'aucun bilan n'est calculable
    avant dix jours de données, « Comment je me sens là » juste après un check-in du
    matin qui vient d'enregistrer exactement ça, « Respirer 5 min » alors que la
    séance du jour est déjà faite.

    Trois au maximum, et l'ordre est celui de l'utilité, pas celui du catalogue.
    """
    exclude = exclude or set()
    hour = (now or dt.datetime.now()).hour
    out: list[str] = []
    done_slugs = _done_slugs(plan)

    def add(label: str, key: str) -> None:
        if key not in exclude and label not in out and len(out) < 3:
            out.append(label)

    # Une saisie due passe avant tout : c'est la seule chose qui conditionne les
    # autres, puisque tous les signaux se calculent dessus.
    if not state["matin_done"] and hour < EVENING_FROM:
        add("Noter ma nuit", "matin")
    if not state["soir_done"] and hour >= EVENING_FROM:
        add("Noter ma journée", "soir")

    # La mesure instantanée n'est proposée que si elle apporte quelque chose : au
    # premier relevé du jour, ou pour suivre une variation. Après cinq, non.
    if state["mesures_instantanees"] < 3:
        add("Comment je me sens là", "maintenant")

    if "respiration-lente-10" not in done_slugs:
        add("Respirer 5 min", "breath")

    if state["gad7_due"]:
        add("Faire le GAD-7", "echelles")

    # Les chiffres ne sont proposés qu'une fois qu'ils disent quelque chose. Le
    # seuil est celui du bilan hebdomadaire — dix jours de données —, et il vaut
    # ici pour la même raison : en dessous, la courbe est du bruit.
    if state.get("jours_notes", 0) >= 10:
        add("Mes chiffres", "stats")

    add("Mon parcours", "jour")
    return out


def _done_slugs(plan: dict[str, Any] | None) -> set[str]:
    if not plan:
        return set()
    return {
        item["activity"]["slug"]
        for item in plan.get("items", [])
        if item.get("status") in {"fait", "partiel"}
    }


# --- Le classeur -------------------------------------------------------------


def choose(
    user: dict[str, Any],
    state: dict[str, Any],
    *,
    exclude: set[str] | None = None,
    today: dt.date | None = None,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    """L'étape suivante. Jamais `None` — il y a toujours quelque chose.

    `exclude` porte ce qui vient d'être fait : les types de widgets et les slugs
    d'activités à ne pas reproposer dans la foulée. Sans lui, valider la respiration
    du jour renverrait immédiatement « et si tu respirais ? ».
    """
    exclude = set(exclude or ())
    today = today or dt.date.today()
    now = now or dt.datetime.now()
    user_id = user["id"]
    profile = user.get("profile") or {}

    plan = _plan(user_id, profile, today)

    for step in _ranked(user, state, plan, exclude, today, now):
        if step is not None:
            step["suggestions"] = suggestions_for(
                state, plan, exclude=exclude | _occupied(step), now=now
            )
            step["explication"] = explanation_for(user_id, state, step, today)
            step.pop("activity", None)
            step.pop("explain_doc", None)
            return step

    # Inatteignable en pratique : `_lesson` ne rend la main que si le corpus entier
    # a été proposé, et le repli ci-dessous couvre ce cas plutôt que de laisser
    # remonter un `None` que l'appelant devrait gérer.
    fallback = _decision(
        "Tout ce qui était dû est fait, et tu as vu passer l'ensemble du corpus. "
        "Le plus utile maintenant, c'est de relire ce que tu écrivais il y a un mois : "
        "c'est là que les changements se voient, jamais au jour le jour.",
        _widget("memoire"),
        engine="classeur",
    )
    fallback["suggestions"] = suggestions_for(state, plan, exclude=exclude, now=now)
    return fallback


def _plan(user_id: str, profile: dict[str, Any], today: dt.date) -> dict[str, Any] | None:
    """Le programme du jour, ou `None` s'il n'a pas pu être construit.

    Un échec de construction ne doit jamais casser l'ouverture du fil : c'est le
    message d'accueil, il doit arriver même dégradé. Le classeur descend alors
    directement aux questions ouvertes et aux fiches, qui ne dépendent pas de lui.
    """
    try:
        return program.build_day(user_id, profile, today)
    except Exception:  # noqa: BLE001
        logger.exception("Programme du jour indisponible, classement dégradé")
        return None


def _occupied(step: dict[str, Any]) -> set[str]:
    widget = step.get("widget")
    return {widget["type"]} if widget else set()


def _ranked(
    user: dict[str, Any],
    state: dict[str, Any],
    plan: dict[str, Any] | None,
    exclude: set[str],
    today: dt.date,
    now: dt.datetime,
) -> list[dict[str, Any] | None]:
    """L'ordre de priorité, en clair. C'est la seule chose à relire pour comprendre
    ce que l'application décide."""
    if state["status"] == "entretien":
        return [
            _maintenance(state, exclude),
            _question(user, state, exclude, today),
            _lesson(user["id"], state, today) if "sources" not in exclude else None,
        ]

    return [
        # 1. La saisie du créneau. Rien ne se calcule sans elle.
        _moment(state, exclude, now),
        # 2. Le GAD-7 hebdomadaire : c'est lui qui dit si quelque chose bouge.
        _gad7(state, exclude),
        # 3. Ce que les données de la personne ont déclenché.
        _from_plan(plan, "adaptatif", exclude),
        # 4. Le module de la semaine.
        _from_plan(plan, "module", exclude),
        # 5. Le socle non fait. Absent du classement précédent, c'était la cause
        #    directe du « rien à faire » : trois activités quotidiennes calculées
        #    chaque matin et jamais proposées dans le fil.
        _from_plan(plan, "socle", exclude),
        # 6. La pratique corporelle, le soir seulement — c'est son créneau.
        _from_plan(plan, "corps", exclude) if now.hour >= EVENING_FROM else None,
        # 7. Ce qu'on ne sait pas encore et qui changerait les propositions.
        _question(user, state, exclude, today),
        # 8. Une fiche du corpus jamais lue.
        _lesson(user["id"], state, today) if "sources" not in exclude else None,
    ]


def _moment(
    state: dict[str, Any], exclude: set[str], now: dt.datetime
) -> dict[str, Any] | None:
    """La saisie due, si elle l'est. Mêmes bornes que `chat._moment_due`.

    Une saisie explicitement refusée aujourd'hui n'est pas remise en avant. C'est le
    seul endroit du classeur où « déjà proposé » compte autant que « pas encore
    fait » : reporter le check-in du soir puis se l'entendre reproposer à l'action
    suivante n'est pas de l'insistance utile, c'est du harcèlement — et le report est
    déjà enregistré comme une donnée. La saisie reste accessible par « Noter », qui
    est un geste volontaire.
    """
    if state.get("saisie_reportee"):
        return None
    hour = now.hour
    due: str | None = None
    if not state["matin_done"] and hour < EVENING_FROM:
        due = "matin"
    elif not state["soir_done"] and hour >= EVENING_FROM:
        due = "soir"
    elif not state["matin_done"] and not state["soir_done"]:
        due = "matin"
    if due is None or due in exclude:
        return None

    if due == "matin":
        reply = "La nuit d'abord : combien t'as dormi, et comment tu te sens là. Trente secondes."
        if state["streak"] >= 2:
            reply = (
                f"**{state['streak']} jours d'affilée.** La nuit d'abord : combien t'as dormi, "
                "et comment tu te sens là."
            )
    else:
        reply = (
            "La journée est finie — on la note. Le pic et la moyenne, pas un chiffre unique : "
            "sous anxiété la mémoire retient les pires moments."
        )
        if state["mesures_instantanees"]:
            reply = (
                f"T'as noté **{state['mesures_instantanees']} fois** comment tu te sentais "
                f"aujourd'hui (pic à **{state['pic_instantane']}/10**). Je te propose le pic et "
                "la moyenne calculés — vérifie, corrige si c'est faux."
            )
    step = _decision(reply, _widget(due), engine="classeur")
    # Pourquoi le sommeil se note au réveil et pas le soir, pourquoi on mesure tous les
    # jours : deux fiches du corpus, dites une fois chacune.
    step["explain_doc"] = "agenda-sommeil" if due == "matin" else "auto-monitoring"
    return step


def _gad7(state: dict[str, Any], exclude: set[str]) -> dict[str, Any] | None:
    if not state["gad7_due"] or "echelles" in exclude or "gad7" in exclude:
        return None
    step = _decision(
        "Le GAD-7 est dû cette semaine : sept questions, et c'est la seule mesure qui dise "
        "si quelque chose bouge vraiment — l'impression du moment, elle, suit la dernière "
        "mauvaise heure.",
        _widget("echelles", {"instrument": "gad7"}),
        engine="classeur",
    )
    step["explain_doc"] = "mesure-gad7"
    return step


def _from_plan(
    plan: dict[str, Any] | None, slot: str, exclude: set[str]
) -> dict[str, Any] | None:
    """Le premier item non fait d'un créneau du programme.

    La justification vient de `why_for_you`, écrite par `program.py` avec les
    chiffres de la personne. On ne la reformule pas : elle est déjà personnalisée,
    et la faire réécrire par un modèle n'ajouterait qu'un risque d'invention.
    """
    if not plan:
        return None
    for item in plan.get("items", []):
        if item["slot"] != slot:
            continue
        if item.get("status") in {"fait", "partiel"}:
            continue
        slug = item["activity"]["slug"]
        widget_type = item.get("widget")
        if slug in exclude or (widget_type and widget_type in exclude):
            continue
        # Le check-in est traité par `_moment` : le reproposer ici doublerait la
        # demande avec une formulation différente.
        if slug == "checkin-quotidien":
            continue

        activity = item["activity"]
        reply = item["why_for_you"]
        if widget_type is None:
            reply += (
                "\n\nRien à ouvrir : c'est une habitude à changer, pas un exercice à faire ici."
            )
        elif activity.get("duration_min"):
            reply += f"\n\n**{activity['title']}** — {activity['duration_min']} min."
        decision = _decision(
            reply,
            _widget(widget_type) if widget_type else None,
            engine="programme",
            citations=[program.citation_for(item)],
        )
        # Transportée pour `explanation_for`, qui en tire le mécanisme et les
        # contre-indications. Retirée par `choose()` avant de rendre la décision : ce
        # n'est pas un champ du fil.
        decision["activity"] = activity
        return decision
    return None


def _question(
    user: dict[str, Any], state: dict[str, Any], exclude: set[str], today: dt.date
) -> dict[str, Any] | None:
    for question in _open_questions(user["id"], user.get("profile") or {}, state, today):
        widget = question.get("widget")
        if widget and widget["type"] in exclude:
            continue
        return _decision(question["reply"], widget, engine="question")
    return None


def _maintenance(state: dict[str, Any], exclude: set[str]) -> dict[str, Any] | None:
    """Le régime d'entretien a lui aussi quelque chose à proposer tous les jours.

    C'est le sens du mot : ce qui distingue les personnes qui rechutent de celles qui
    ne rechutent pas, c'est de continuer les expositions après la guérison. Dire
    « tout est à jour, rien à faire » à quelqu'un en entretien est exactement le
    message qui produit la rechute.
    """
    if state["exposition_due"] and "exposition" not in exclude:
        since = state["jours_depuis_exposition"]
        when = f"{since} jours" if since is not None else "un moment"
        return _decision(
            f"Entretien : ta dernière exposition volontaire date de **{when}**. Une par "
            "semaine, même quand tout va bien — c'est ce qui empêche l'évitement de "
            "revenir sans bruit, par petites décisions confortables.",
            _widget("exposition"),
            engine="classeur",
        )
    if not state["checkin_done"] and "soir" not in exclude:
        return _decision(
            "Entretien : le check-in hebdomadaire, et c'est tout pour aujourd'hui côté "
            "saisie.",
            _widget("soir"),
            engine="classeur",
        )
    if state["gad7_due"] and "echelles" not in exclude:
        return _decision(
            "Le GAD-7 mensuel est dû. En entretien c'est lui qui sert de détecteur de "
            "rechute : quatre points au-dessus du seuil de rémission et le programme "
            "actif reprend.",
            _widget("echelles", {"instrument": "gad7"}),
            engine="classeur",
        )
    return None
