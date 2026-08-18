"""Catalogue d'activités du programme.

Source de vérité unique, semée en base par `app/ingest.py::seed_activities`.
Chaque activité porte les trois éléments nécessaires pour répondre à
« d'où ça sort ? » :

- `mechanism` : par quel mécanisme l'activité agit ;
- `evidence_level` : A (essais randomisés / recommandations), B (preuve
  prometteuse mais partielle), C (consensus clinique) ;
- `sources` : les références vérifiables, avec URL.

`kb_doc_id` pointe vers la fiche détaillée du corpus RAG (backend/knowledge/),
ce qui permet à l'interface d'ouvrir l'explication longue et à l'IA de citer
exactement le même document.
"""

from __future__ import annotations

from typing import Any

# Raccourcis de sources réutilisées
S_UP_BARLOW = {
    "label": "Barlow & Farchione, World Psychiatry 2020 — Protocole Unifié transdiagnostique",
    "url": "https://onlinelibrary.wiley.com/doi/10.1002/wps.20748",
}
S_UP_RCT = {
    "label": "Barlow et al., JAMA Psychiatry 2017 — essai randomisé d'équivalence (N=223)",
    "url": "https://jamanetwork.com/journals/jamapsychiatry/fullarticle/2646395",
}
S_NICE = {
    "label": "NICE CG113 — anxiété généralisée et trouble panique chez l'adulte",
    "url": "https://www.nice.org.uk/guidance/cg113/chapter/Recommendations",
}
S_LABORDE = {
    "label": "Laborde et al., Neurosci Biobehav Rev 2022 — méta-analyse respiration lente et VFC",
    "url": "https://www.sciencedirect.com/science/article/abs/pii/S0149763422002007",
}
S_HOGE = {
    "label": "Hoge et al., JAMA Psychiatry 2023 — MBSR non inférieur à l'escitalopram",
    "url": "https://jamanetwork.com/journals/jamapsychiatry/fullarticle/2798510",
}
S_CRASKE14 = {
    "label": "Craske et al., Behav Res Ther 2014 — apprentissage inhibiteur et optimisation de l'exposition",
    "url": "https://pubmed.ncbi.nlm.nih.gov/24864005/",
}
S_CRASKE22 = {
    "label": "Craske et al., Behav Res Ther 2022 — OptEx Nexus, approche par récupération inhibitrice",
    "url": "https://pubmed.ncbi.nlm.nih.gov/35325683/",
}
S_SCHMIDT = {
    "label": "Schmidt & Trakowski 2004 — exposition intéroceptive dans le trouble panique",
    "url": "https://anxietyinstitute.com/wp-content/uploads/2021/12/Schmidt-_-Trakowski-2004.pdf",
}
S_SLEEP_MED = {
    "label": "J Affect Disord 2023 — l'amélioration du sommeil médie l'amélioration de l'anxiété (dCBT-I)",
    "url": "https://www.sciencedirect.com/science/article/pii/S0165032723008194",
}
S_EXERCISE = {
    "label": "eClinicalMedicine 2025 — activité physique et risque d'anxiété : méta-analyse dose-réponse (11 cohortes)",
    "url": "https://www.thelancet.com/journals/eclinm/article/PIIS2589-5370(25)00217-2/fulltext",
}
S_GAD7 = {
    "label": "Toussaint et al., J Affect Disord 2020 — sensibilité au changement et DMCI du GAD-7 (≈4 points)",
    "url": "https://pubmed.ncbi.nlm.nih.gov/32090765/",
}
S_APPS = {
    "label": "Linardon et al., World Psychiatry 2024 — méta-analyse de 176 ECR d'applications de santé mentale",
    "url": "https://onlinelibrary.wiley.com/doi/full/10.1002/wps.21183",
}
S_WORRY = {
    "label": "Dippel et al., 2023 — méta-analyse du report de l'inquiétude",
    "url": "https://www.piekeren.com/wp-content/uploads/2024/03/Dippel.2023_Worry-postponement-meta-analysis.pdf",
}
S_BALBAN = {
    "label": "Balban et al., Cell Reports Medicine 2023 — soupir cyclique vs respiration en boîte vs méditation",
    "url": "https://www.cell.com/cell-reports-medicine/fulltext/S2666-3791(22)00474-8",
}
S_CAFFEINE = {
    "label": "ECR croisé contre placebo 2025 — caféine 150 mg dans le trouble panique",
    "url": "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12287556/",
}


ACTIVITIES: list[dict[str, Any]] = [
    # ---------------------------------------------------------------- SOCLE ---
    {
        "slug": "checkin-quotidien",
        "title": "Check-in du jour",
        "short_label": "Check-in",
        "category": "mesure",
        "duration_min": 2,
        "up_module": 1,
        "evidence_level": "A",
        "targets": ["suivi", "inquietude", "humeur"],
        "is_core": True,
        "kb_doc_id": "auto-monitoring",
        "mechanism": (
            "Trois effets distincts : la mesure modifie le comportement observé (réactivité de "
            "la mesure), elle corrige la mémoire biaisée par l'anxiété (qui ne retient que les "
            "pires moments), et elle rend visibles des régularités personnelles — sommeil → "
            "anxiété du lendemain, caféine → pics — invisibles sans série temporelle."
        ),
        "sources": [S_APPS, S_NICE],
        "instructions": [
            "Notez votre anxiété du jour de 0 à 10, spontanément, sans réfléchir longtemps.",
            "Renseignez le sommeil de la nuit précédente : heures, qualité.",
            "Cochez les contextes où l'anxiété est montée aujourd'hui.",
            "Indiquez caféine, alcool, minutes d'activité physique.",
            "En une phrase : le déclencheur principal de la journée.",
        ],
        "contraindications": (
            "Ne mesurez pas votre pouls et ne notez pas chaque sensation : un auto-monitoring "
            "excessif devient de l'hypervigilance corporelle et entretient l'anxiété."
        ),
    },
    {
        "slug": "respiration-lente-10",
        "title": "Respiration lente 10 minutes (≈6 cycles/min)",
        "short_label": "Respiration lente",
        "category": "respiration",
        "duration_min": 10,
        "up_module": 3,
        "evidence_level": "A",
        "targets": ["somatique", "stress-aigu", "sommeil", "inquietude"],
        "is_core": True,
        "kb_doc_id": "respiration-lente",
        "mechanism": (
            "À ~0,1 Hz, la respiration entre en résonance avec la boucle du baroréflexe : "
            "l'amplitude des variations du rythme cardiaque augmente, les indices d'activité "
            "vagale (RMSSD, haute fréquence) montent, et la sensibilité du baroréflexe "
            "s'améliore. L'expiration est la phase active de l'effet parasympathique."
        ),
        "sources": [S_LABORDE, {
            "label": "Laborde et al. 2021 — dose-réponse d'une séance à 6 cycles/min sur l'activité vagale",
            "url": "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8656666/",
        }],
        "instructions": [
            "Assis, dos soutenu, une main sur le ventre.",
            "Inspirez par le nez 5 secondes en gonflant le ventre, pas la poitrine.",
            "Expirez 5 secondes, sans forcer, bouche entrouverte ou par le nez.",
            "Suivez le guide visuel de l'application pendant 10 minutes.",
            "Si 5-5 est inconfortable, commencez à 4-6 et allongez progressivement.",
        ],
        "contraindications": (
            "À pratiquer à froid, en entraînement quotidien. Si vous avez des attaques de "
            "panique, ne l'utilisez pas comme bouée de sauvetage en pleine crise : elle "
            "deviendrait un comportement de sécurité et bloquerait l'apprentissage."
        ),
    },
    {
        "slug": "journal-libre",
        "title": "Journal du soir (entrée libre)",
        "short_label": "Journal",
        "category": "cognitif",
        "duration_min": 8,
        "up_module": 2,
        "evidence_level": "A",
        "targets": ["suivi", "humeur", "inquietude"],
        "is_core": True,
        "kb_doc_id": "modele-trois-composantes",
        "mechanism": (
            "Mettre en mots découpe l'émotion en trois composantes manipulables (pensées, "
            "sensations, comportements) et fournit les données textuelles sur lesquelles "
            "l'analyse repère vos schémas récurrents."
        ),
        "sources": [S_UP_BARLOW, S_APPS],
        "instructions": [
            "Qu'est-ce qui s'est passé aujourd'hui ? Les faits d'abord.",
            "Qu'avez-vous ressenti dans le corps, et où précisément ?",
            "Qu'avez-vous fait, ou évité de faire, à cause de l'anxiété ?",
            "Un point positif de la journée, même minuscule.",
        ],
        "contraindications": None,
    },
    # ------------------------------------------------------------ MODULE 1-2 ---
    {
        "slug": "objectifs-valeurs",
        "title": "Clarifier mes objectifs et ce qui compte pour moi",
        "short_label": "Objectifs",
        "category": "comportemental",
        "duration_min": 20,
        "up_module": 1,
        "evidence_level": "A",
        "targets": ["motivation", "evitement"],
        "is_core": False,
        "kb_doc_id": "protocole-unifie",
        "mechanism": (
            "Le module 1 du Protocole Unifié : l'ambivalence face au changement est la première "
            "cause d'abandon. Formuler des objectifs en termes de ce que vous voulez retrouver "
            "(et non de ce que vous voulez éviter) fournit la motivation nécessaire aux "
            "expositions, qui sont volontairement inconfortables."
        ),
        "sources": [S_UP_BARLOW, S_UP_RCT],
        "instructions": [
            "Listez 3 choses que l'anxiété vous empêche de faire aujourd'hui.",
            "Pour chacune : à quoi ressemblerait votre vie si elle redevenait possible ?",
            "Notez les avantages à ne rien changer — ils existent, et les ignorer est une erreur.",
            "Choisissez un objectif concret et mesurable pour les 4 prochaines semaines.",
        ],
        "contraindications": None,
    },
    {
        "slug": "psychoeducation-cycle",
        "title": "Comprendre mon cycle de maintien (ARC)",
        "short_label": "Mon cycle",
        "category": "cognitif",
        "duration_min": 15,
        "up_module": 2,
        "evidence_level": "A",
        "targets": ["inquietude", "panique", "social", "evitement"],
        "is_core": False,
        "kb_doc_id": "modele-trois-composantes",
        "mechanism": (
            "Le tableau Antécédent – Réaction – Conséquence montre que ce qui entretient "
            "l'anxiété n'est presque jamais le déclencheur, mais la conséquence de votre "
            "réaction : le soulagement immédiat de l'évitement renforce la peur."
        ),
        "sources": [S_UP_BARLOW, S_NICE],
        "instructions": [
            "Prenez un épisode d'anxiété précis des dernières 48 h.",
            "Antécédent : que s'est-il passé juste avant ? (lieu, personne, pensée, sensation)",
            "Réaction : pensées / sensations / comportement, les trois séparément.",
            "Conséquence : à court terme (soulagement ?) et à long terme (que se passe-t-il la fois suivante ?).",
        ],
        "contraindications": None,
    },
    # -------------------------------------------------------------- MODULE 3 ---
    {
        "slug": "meditation-souffle",
        "title": "Méditation de conscience du souffle",
        "short_label": "Méditation souffle",
        "category": "meditation",
        "duration_min": 10,
        "up_module": 3,
        "evidence_level": "A",
        "targets": ["inquietude", "humeur", "stress-aigu"],
        "is_core": False,
        "kb_doc_id": "mindfulness-mbsr",
        "mechanism": (
            "Entraîne la décentration (voir une pensée comme un événement mental et non comme "
            "une information sur le réel) et réduit le temps passé en rumination orientée vers "
            "le futur."
        ),
        "sources": [S_HOGE, S_APPS],
        "instructions": [
            "Assis, yeux fermés ou regard bas, portez l'attention sur la sensation du souffle aux narines.",
            "Quand l'esprit part — il partira, c'est normal et ce n'est pas un échec — notez « pensée » et revenez au souffle.",
            "Ne cherchez pas à modifier votre respiration : vous l'observez seulement.",
            "10 minutes. La qualité de la séance n'est pas un indicateur de progrès ; la régularité l'est.",
        ],
        "contraindications": None,
    },
    {
        "slug": "scan-corporel",
        "title": "Scan corporel",
        "short_label": "Scan corporel",
        "category": "meditation",
        "duration_min": 20,
        "up_module": 3,
        "evidence_level": "A",
        "targets": ["somatique", "sensibilite-anxieuse", "sommeil"],
        "is_core": False,
        "kb_doc_id": "mindfulness-mbsr",
        "mechanism": (
            "Réduit l'évitement expérientiel : rester avec une sensation désagréable sans fuir "
            "désactive progressivement le réflexe d'évitement. C'est aussi la préparation "
            "directe à l'exposition intéroceptive du module 6."
        ),
        "sources": [S_HOGE],
        "instructions": [
            "Allongé ou assis, parcourez le corps des pieds à la tête, zone par zone.",
            "Sur chaque zone : quelles sensations exactement ? température, pression, picotement, rien ?",
            "Sur une zone tendue ou désagréable : restez 3 respirations sans chercher à la relâcher.",
            "Terminez par la sensation du corps entier.",
        ],
        "contraindications": (
            "Peut augmenter l'anxiété au début en cas de forte anxiété somatique : raccourcissez "
            "la séance plutôt que d'abandonner. En cas d'antécédent de traumatisme, préférez un "
            "ancrage externe (sons, contact des pieds au sol)."
        ),
    },
    {
        "slug": "conscience-emotionnelle",
        "title": "Observer une émotion en trois composantes",
        "short_label": "Conscience émotionnelle",
        "category": "meditation",
        "duration_min": 12,
        "up_module": 3,
        "evidence_level": "B",
        "targets": ["humeur", "inquietude", "evitement"],
        "is_core": False,
        "kb_doc_id": "conscience-emotionnelle",
        "mechanism": (
            "Cible les deux dérives qui entretiennent l'anxiété : le jugement de l'émotion (qui "
            "ajoute de la honte à la peur) et la projection dans le futur (l'inquiétude est une "
            "simulation de futur). Prérequis des expositions : on ne s'expose pas à ce qu'on ne "
            "sait pas observer."
        ),
        "sources": [S_UP_BARLOW],
        "instructions": [
            "3 minutes d'ancrage sur le souffle et le contact du corps.",
            "Repérez l'émotion présente et nommez-la en un mot.",
            "Balayez : quelles pensées ? quelles sensations, et où ? quelle envie d'agir ?",
            "À chaque jugement ou projection, notez mentalement « jugement » / « futur » et revenez au corps.",
            "Notez l'émotion, son intensité, et si vous avez agi ou non sur l'envie.",
        ],
        "contraindications": None,
    },
    {
        "slug": "relaxation-musculaire",
        "title": "Relaxation musculaire progressive",
        "short_label": "Relaxation musculaire",
        "category": "relaxation",
        "duration_min": 15,
        "up_module": 3,
        "evidence_level": "A",
        "targets": ["somatique", "tension", "sommeil", "inquietude"],
        "is_core": False,
        "kb_doc_id": "relaxation-appliquee",
        "mechanism": (
            "Réduit directement la tension musculaire (composante somatique majeure de l'anxiété "
            "généralisée) et développe une compétence de discrimination : percevoir la montée de "
            "tension assez tôt pour intervenir."
        ),
        "sources": [S_NICE, {
            "label": "NICE — synthèse : la relaxation appliquée est recommandée à égalité avec la TCC pour le TAG",
            "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC3230126/",
        }],
        "instructions": [
            "Contractez un groupe musculaire 5 secondes (mains, avant-bras, épaules, visage, ventre, jambes, pieds).",
            "Relâchez brutalement et observez la différence 15 secondes.",
            "Enchaînez les groupes du bas vers le haut.",
            "Après 2 semaines, passez à la version sans contraction, puis au mot-signal, puis à la version rapide de 30 secondes en situation réelle.",
        ],
        "contraindications": "Ne contractez pas une zone blessée ou douloureuse : passez-la.",
    },
    {
        "slug": "soupir-physiologique",
        "title": "Soupir physiologique (pic d'anxiété)",
        "short_label": "Soupir cyclique",
        "category": "respiration",
        "duration_min": 3,
        "up_module": 3,
        "evidence_level": "B",
        "targets": ["stress-aigu", "somatique"],
        "is_core": False,
        "kb_doc_id": "respiration-aigue",
        "mechanism": (
            "La double inspiration réinsuffle les alvéoles collabées et améliore l'échange "
            "gazeux ; l'expiration longue accentue l'influence parasympathique sur le nœud "
            "sinusal. L'effet est mécanique, donc rapide."
        ),
        "sources": [S_BALBAN, S_LABORDE],
        "instructions": [
            "Inspirez par le nez normalement, puis ajoutez une seconde petite inspiration par-dessus.",
            "Expirez lentement et complètement par la bouche.",
            "5 cycles, puis évaluez votre anxiété avant/après dans l'application.",
        ],
        "contraindications": (
            "En cas d'attaques de panique, ne l'utilisez pas systématiquement pour empêcher une "
            "crise : cela devient un comportement de sécurité."
        ),
    },
    # -------------------------------------------------------------- MODULE 4 ---
    {
        "slug": "journal-pensees",
        "title": "Journal de pensées (restructuration cognitive)",
        "short_label": "Journal de pensées",
        "category": "cognitif",
        "duration_min": 15,
        "up_module": 4,
        "evidence_level": "A",
        "targets": ["inquietude", "social", "panique", "humeur"],
        "is_core": False,
        "kb_doc_id": "flexibilite-cognitive",
        "mechanism": (
            "Cible les deux pièges de pensée retenus par le Protocole Unifié : la surestimation "
            "de la probabilité et la catastrophisation. L'objectif n'est pas de penser positif "
            "mais d'élargir l'éventail des interprétations, puis de tester la nouvelle hypothèse."
        ),
        "sources": [S_UP_BARLOW, S_NICE, {
            "label": "Méta-analyse de la TCC de faible intensité pour l'anxiété généralisée (2024)",
            "url": "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10763350/",
        }],
        "instructions": [
            "Situation, puis émotion et intensité de 0 à 10.",
            "Pensée automatique : la phrase exacte qui vous a traversé.",
            "Quel piège ? surestimation de la probabilité, ou catastrophisation ?",
            "Preuves pour / preuves contre, factuelles.",
            "« Et si c'était vrai — comment je ferais face ? » C'est souvent la question la plus utile.",
            "Pensée alternative crédible, puis réévaluez l'émotion de 0 à 10.",
        ],
        "contraindications": (
            "Si vous refaites le même journal sur le même sujet chaque jour, l'outil s'est "
            "transformé en recherche de réassurance. Passez à l'exposition."
        ),
    },
    # -------------------------------------------------------------- MODULE 5 ---
    {
        "slug": "temps-inquietude",
        "title": "Temps d'inquiétude programmé",
        "short_label": "Temps d'inquiétude",
        "category": "cognitif",
        "duration_min": 20,
        "up_module": 5,
        "evidence_level": "B",
        "targets": ["inquietude", "rumination", "sommeil"],
        "is_core": False,
        "kb_doc_id": "temps-inquietude",
        "mechanism": (
            "Contrôle du stimulus : l'inquiétude cesse d'être déclenchée par n'importe quel "
            "contexte. Second effet, souvent le plus frappant : relues quelques heures plus tard, "
            "la majorité des inquiétudes ont perdu leur charge émotionnelle."
        ),
        "sources": [S_WORRY, {
            "label": "Psychology Tools — Worry Postponement (protocole d'après Borkovec et al., 1983)",
            "url": "https://www.psychologytools.com/resource/worry-postponement",
        }],
        "instructions": [
            "Fixez un créneau quotidien de 20 minutes, jamais dans les 2-3 h avant le coucher.",
            "Hors créneau : notez l'inquiétude en une ligne et revenez à votre tâche.",
            "Pendant le créneau : triez actionnable / hypothétique.",
            "Actionnable → une action, une date. Hypothétique → pas de solution, pratiquez l'acceptation.",
            "Minuteur obligatoire : on arrête à l'heure.",
        ],
        "contraindications": (
            "Niveau de preuve B : les effets sont bien établis en population non clinique mais une "
            "étude chez des patients avec trouble d'anxiété généralisée n'a pas retrouvé d'effet. "
            "Outil d'appoint, pas pilier. Ne doit pas devenir 20 minutes de rumination."
        ),
    },
    {
        "slug": "resolution-problemes",
        "title": "Résolution de problèmes en 5 étapes",
        "short_label": "Résolution de problèmes",
        "category": "cognitif",
        "duration_min": 20,
        "up_module": 5,
        "evidence_level": "A",
        "targets": ["inquietude", "evitement", "humeur"],
        "is_core": False,
        "kb_doc_id": "resolution-problemes",
        "mechanism": (
            "L'inquiétude chronique est en partie un évitement cognitif : réfléchir donne "
            "l'impression d'agir tout en évitant l'incertitude. Passer à une action datée "
            "interrompt ce mécanisme et produit des données réelles."
        ),
        "sources": [S_NICE],
        "instructions": [
            "Définissez le problème en une phrase concrète et observable.",
            "Générez au moins 5 solutions sans les juger, y compris les mauvaises.",
            "Avantages / inconvénients, rapidement.",
            "Choisissez « suffisamment bien » : chercher la solution parfaite est un évitement.",
            "Première action : quoi, quand, où. Puis notez le résultat réel.",
        ],
        "contraindications": None,
    },
    {
        "slug": "inventaire-securite",
        "title": "Inventaire de mes comportements de sécurité",
        "short_label": "Comportements de sécurité",
        "category": "comportemental",
        "duration_min": 15,
        "up_module": 5,
        "evidence_level": "A",
        "targets": ["evitement", "social", "panique"],
        "is_core": False,
        "kb_doc_id": "evitements-securite",
        "mechanism": (
            "Tant qu'un comportement de sécurité est présent, votre cerveau garde une "
            "explication alternative disponible (« je n'ai rien senti parce que… ») et la "
            "prédiction catastrophique n'est jamais réellement mise à l'épreuve. Le retrait des "
            "signaux de sécurité est une stratégie fondamentale d'optimisation de l'exposition."
        ),
        "sources": [S_CRASKE14, S_UP_BARLOW],
        "instructions": [
            "Pendant 3 jours, notez tout ce que vous faites pour réduire l'anxiété sur le moment.",
            "Incluez le subtil : s'asseoir près de la sortie, préparer ses phrases, garder son téléphone, vérifier ses symptômes.",
            "Pour chacun : quelle catastrophe est-il censé empêcher ?",
            "Classez du plus facile au plus difficile à abandonner.",
            "Retirez-en un seul à la fois — c'est déjà une exposition à part entière.",
        ],
        "contraindications": (
            "Un médicament prescrit n'est pas un comportement de sécurité à supprimer de votre "
            "initiative. N'arrêtez ni ne modifiez jamais un traitement sans votre médecin."
        ),
    },
    # -------------------------------------------------------------- MODULE 6 ---
    {
        "slug": "exposition-interoceptive",
        "title": "Exposition intéroceptive",
        "short_label": "Exposition intéroceptive",
        "category": "exposition",
        "duration_min": 15,
        "up_module": 6,
        "evidence_level": "A",
        "targets": ["panique", "somatique", "sensibilite-anxieuse"],
        "is_core": False,
        "kb_doc_id": "exposition-interoceptive",
        "mechanism": (
            "Provoquer volontairement les sensations redoutées, en sécurité, crée une violation "
            "d'attente : l'écart entre la prédiction (« je vais m'évanouir ») et le résultat réel "
            "est ce qui produit l'apprentissage concurrent « ces sensations sont désagréables mais "
            "pas dangereuses »."
        ),
        "sources": [S_SCHMIDT, S_CRASKE14, {
            "label": "Lee et al., BMC Psychiatry 2006 — hypersensibilité et exposition intéroceptives",
            "url": "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC1559685/",
        }],
        "instructions": [
            "Écrivez la prédiction AVANT : que va-t-il se passer, et avec quelle probabilité (0-100 %) ?",
            "Choisissez l'exercice : hyperventilation 60 s, apnée 30 s, rotation sur chaise 60 s, escaliers rapides 60 s, paille fine 60-120 s.",
            "Faites la durée entière, sans l'écourter et sans compensation.",
            "Restez avec les sensations 1 minute après, sans respiration de secours.",
            "Notez ce qui s'est réellement produit, l'anxiété maximale, le temps de retour à la normale.",
            "Répétez le même exercice 3 à 5 fois, plusieurs jours de suite.",
        ],
        "contraindications": (
            "Avis médical requis avant de commencer en cas de maladie cardiaque ou respiratoire "
            "(dont l'asthme), épilepsie, hypertension non contrôlée, glaucome, antécédent d'AVC, "
            "grossesse, blessure cervicale ou dorsale, trouble de l'oreille interne, diabète mal "
            "équilibré."
        ),
    },
    # -------------------------------------------------------------- MODULE 7 ---
    {
        "slug": "echelle-exposition",
        "title": "Construire mon échelle d'expositions",
        "short_label": "Échelle d'expositions",
        "category": "exposition",
        "duration_min": 25,
        "up_module": 7,
        "evidence_level": "A",
        "targets": ["evitement", "social", "panique", "inquietude"],
        "is_core": False,
        "kb_doc_id": "exposition-situationnelle",
        "mechanism": (
            "Une hiérarchie explicite transforme un évitement diffus en une liste d'items "
            "testables, et permet de varier l'intensité et les contextes — deux leviers dont "
            "l'effet est empiriquement soutenu (violation d'attente, variabilité contextuelle)."
        ),
        "sources": [S_CRASKE14, S_CRASKE22, S_UP_BARLOW],
        "instructions": [
            "Listez tout ce que vous évitez : situations, lieux, conversations, sensations, sujets de pensée.",
            "Notez pour chacun l'anxiété anticipée de 0 à 10.",
            "Précisez les comportements de sécurité associés à chaque item.",
            "Rangez du plus facile au plus difficile. Commencez par un item à 4-6/10.",
        ],
        "contraindications": None,
    },
    {
        "slug": "exposition-in-vivo",
        "title": "Exposition en situation réelle",
        "short_label": "Exposition in vivo",
        "category": "exposition",
        "duration_min": 30,
        "up_module": 7,
        "evidence_level": "A",
        "targets": ["evitement", "social", "panique"],
        "is_core": False,
        "kb_doc_id": "exposition-situationnelle",
        "mechanism": (
            "Ce n'est pas la baisse d'anxiété pendant la séance qui prédit le bénéfice, mais la "
            "violation d'attente : l'écart entre ce que vous prédisiez et ce qui est arrivé. On "
            "ne désapprend pas la peur, on construit un apprentissage concurrent plus fort qu'il "
            "faut ensuite rendre récupérable dans un maximum de contextes."
        ),
        "sources": [S_CRASKE14, S_CRASKE22],
        "instructions": [
            "Prédiction écrite : que va-t-il se passer ? probabilité ? à quel point serait-ce ingérable ?",
            "Faites-le sans comportement de sécurité et sans distraction (pas de téléphone).",
            "Restez dans la situation, attention dirigée vers l'extérieur.",
            "Après : ce qui est réellement arrivé, anxiété maximale, et l'apprentissage en une phrase.",
            "Répétez 3 à 5 fois le même item, en variant lieu, heure et personnes.",
        ],
        "contraindications": (
            "Ce n'est pas une épreuve de force. Si vous quittez la situation en panique en "
            "concluant « je n'y arriverai jamais », l'item était trop haut : redescendez. En cas "
            "de trouble sévère, d'antécédent traumatique ou d'idées suicidaires, l'exposition se "
            "fait accompagnée par un professionnel."
        ),
    },
    {
        "slug": "experience-sociale",
        "title": "Expérience comportementale sociale",
        "short_label": "Expérience sociale",
        "category": "exposition",
        "duration_min": 25,
        "up_module": 7,
        "evidence_level": "A",
        "targets": ["social", "evitement"],
        "is_core": False,
        "kb_doc_id": "anxiete-sociale",
        "mechanism": (
            "Combine violation d'attente et inversion de l'attention. Tant que vous scrutez vos "
            "propres sensations, vous ne pouvez pas recueillir la preuve que rien de grave ne "
            "s'est produit : vous n'avez pas regardé. La consigne d'attention externe est aussi "
            "importante que l'exposition elle-même."
        ),
        "sources": [S_CRASKE14, S_UP_RCT, {
            "label": "National Social Anxiety Center — apprentissage inhibiteur et anxiété sociale",
            "url": "https://nationalsocialanxietycenter.com/research-summaries/inhibitory-learning-in-exposure-therapy-for-social-anxiety-and-other-anxiety-related-disorders/",
        }],
        "instructions": [
            "Prédiction précise et chiffrée : « si je fais X, alors Y arrivera, probabilité Z % ».",
            "Faites l'inverse de votre comportement de sécurité habituel (ne préparez rien, faites la pause, regardez dans les yeux).",
            "Pendant l'interaction, votre tâche est d'observer l'autre et le décor — pas vous.",
            "Après : combien de personnes ont réellement réagi ? Que s'est-il passé ?",
            "Interdiction de post-mortem : si la rumination démarre, reportez-la au temps d'inquiétude.",
        ],
        "contraindications": None,
    },
    {
        "slug": "exposition-imaginaire",
        "title": "Exposition imaginaire (scénario redouté)",
        "short_label": "Exposition imaginaire",
        "category": "exposition",
        "duration_min": 20,
        "up_module": 7,
        "evidence_level": "B",
        "targets": ["inquietude", "evitement"],
        "is_core": False,
        "kb_doc_id": "exposition-situationnelle",
        "mechanism": (
            "Utile quand la situation redoutée ne peut pas être provoquée (maladie d'un proche, "
            "échec, jugement). Écrire puis relire le scénario jusqu'au bout empêche l'évitement "
            "cognitif qui maintient l'inquiétude en la laissant toujours inachevée."
        ),
        "sources": [S_UP_BARLOW, S_CRASKE22],
        "instructions": [
            "Écrivez le scénario redouté au présent, à la première personne, jusqu'à sa fin — pas seulement jusqu'au moment le plus effrayant.",
            "Relisez-le lentement, en entier, 15 à 20 minutes.",
            "Notez l'anxiété toutes les 5 minutes.",
            "Ne modifiez pas la fin pour la rendre rassurante : ce serait un évitement.",
        ],
        "contraindications": (
            "À éviter seul en cas d'antécédent de traumatisme : l'exposition à un souvenir "
            "traumatique relève d'un protocole spécifique, accompagné."
        ),
    },
    # ----------------------------------------------------- HYGIÈNE DE VIE -----
    {
        "slug": "regularite-sommeil",
        "title": "Régularité du sommeil et contrôle du stimulus",
        "short_label": "Sommeil",
        "category": "hygiene",
        "duration_min": 5,
        "up_module": 1,
        "evidence_level": "A",
        "targets": ["sommeil", "inquietude", "humeur", "somatique"],
        "is_core": False,
        "kb_doc_id": "sommeil",
        "mechanism": (
            "Le lien sommeil-anxiété est bidirectionnel : la privation de sommeil augmente la "
            "réactivité de l'amygdale et diminue le contrôle préfrontal. Une analyse de médiation "
            "sur données individuelles de deux grands essais randomisés montre que l'amélioration "
            "du sommeil médie significativement l'amélioration de l'anxiété."
        ),
        "sources": [S_SLEEP_MED, {
            "label": "Méta-analyse d'ECR : la TCC-I par internet améliore l'anxiété et la dépression comorbides",
            "url": "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4651423/",
        }],
        "instructions": [
            "Heure de lever fixe, 7 jours sur 7, week-end compris. C'est le levier principal.",
            "Le lit sert à dormir : après ~20 min sans dormir, levez-vous, lumière faible, revenez à la somnolence.",
            "Pas de rattrapage : pas de sieste longue, pas de coucher très précoce après une mauvaise nuit.",
            "10-20 min de lumière extérieure dans l'heure suivant le lever ; lumière tamisée le soir.",
            "Temps d'inquiétude en début de soirée, jamais au lit.",
        ],
        "contraindications": (
            "La restriction de sommeil (réduire volontairement le temps au lit) n'est pas incluse "
            "dans ce programme et ne doit pas être entreprise seul en cas de trouble bipolaire, "
            "d'épilepsie ou de somnolence diurne dangereuse."
        ),
    },
    {
        "slug": "activite-physique",
        "title": "Activité physique modérée",
        "short_label": "Activité physique",
        "category": "hygiene",
        "duration_min": 30,
        "up_module": 1,
        "evidence_level": "A",
        "targets": ["somatique", "humeur", "sensibilite-anxieuse", "inquietude"],
        "is_core": False,
        "kb_doc_id": "activite-physique",
        "mechanism": (
            "Trois voies, dont une spécifique : l'exercice produit précisément les sensations "
            "redoutées (cœur rapide, essoufflement, chaleur) dans un contexte sûr et explicable. "
            "C'est de l'exposition intéroceptive naturelle, qui réduit la sensibilité anxieuse."
        ),
        "sources": [S_EXERCISE, {
            "label": "Banyard et al., Int J Ment Health Nurs 2025 — exercice aérobie et de résistance sur anxiété et dépression",
            "url": "https://onlinelibrary.wiley.com/doi/full/10.1111/inm.70054",
        }],
        "instructions": [
            "Visez 150 min/semaine d'intensité modérée : vous pouvez parler mais pas chanter.",
            "Répartissez sur au moins 3 jours ; ajoutez 2 séances de renforcement si possible.",
            "Ne fuyez pas l'intensité qui fait monter le cœur — c'est justement la cible.",
            "Notez les minutes dans le check-in du jour.",
        ],
        "contraindications": (
            "Avis médical si pathologie cardiaque ou respiratoire connue. Attention aussi à "
            "l'usage de l'exercice comme décharge d'urgence de l'anxiété : cela peut devenir un "
            "évitement."
        ),
    },
    {
        "slug": "reduction-cafeine",
        "title": "Ajuster caféine et alcool",
        "short_label": "Caféine / alcool",
        "category": "hygiene",
        "duration_min": 5,
        "up_module": 1,
        "evidence_level": "B",
        "targets": ["panique", "somatique", "sommeil"],
        "is_core": False,
        "kb_doc_id": "cafeine-alcool",
        "mechanism": (
            "La caféine bloque l'adénosine et favorise la libération d'adrénaline : elle produit "
            "exactement les sensations qui déclenchent l'interprétation catastrophique. À doses "
            "élevées elle déclenche une attaque de panique chez environ la moitié des personnes "
            "ayant un trouble panique. L'alcool, lui, provoque une anxiété de rebond à la "
            "redescente (cortisol, adrénaline) et fragmente le sommeil."
        ),
        "sources": [S_CAFFEINE, {
            "label": "Synthèse — trouble anxieux induit par la caféine (> 400 mg)",
            "url": "https://en.wikipedia.org/wiki/Caffeine-induced_anxiety_disorder",
        }],
        "instructions": [
            "Notez votre consommation réelle pendant une semaine avant de changer quoi que ce soit.",
            "Réduisez de ~25 % par semaine : un sevrage brutal donne céphalées et irritabilité, ce qui fait échouer la tentative.",
            "Aucune caféine après 14 h (demi-vie de 5 à 6 heures).",
            "Si vous buvez de l'alcool avant les situations sociales, traitez-le comme un comportement de sécurité (module 5).",
        ],
        "contraindications": (
            "En cas de consommation d'alcool quotidienne et importante, l'arrêt brutal peut être "
            "médicalement dangereux (convulsions, delirium). Parlez-en à un médecin."
        ),
    },
    # ------------------------------------------------------------- MESURES ----
    {
        "slug": "gad7-hebdo",
        "title": "GAD-7 hebdomadaire",
        "short_label": "GAD-7",
        "category": "mesure",
        "duration_min": 3,
        "up_module": 1,
        "evidence_level": "A",
        "targets": ["suivi", "inquietude"],
        "is_core": False,
        "kb_doc_id": "mesure-gad7",
        "mechanism": (
            "Instrument de suivi validé, sensible au changement. Ses seuils (5/10/15) et sa "
            "différence minimale cliniquement importante (≈4 points) permettent de distinguer un "
            "progrès réel du bruit de mesure — et donc d'éviter de célébrer du bruit, ce qui "
            "entraînerait à surveiller ses variations, une forme d'hypervigilance."
        ),
        "sources": [S_GAD7, {
            "label": "GAD-7 — seuils 5/10/15 ; seuil diagnostique ≥ 10 (sensibilité 89 %, spécificité 82 %)",
            "url": "https://www.labvanced.com/content/research/en/questionnaires-and-scales/gad-7-scoring-and-interpretation",
        }],
        "instructions": [
            "Une fois par semaine, le même jour, à la même heure.",
            "Répondez sur les 2 dernières semaines, sans revenir sur vos réponses précédentes.",
            "Ne le remplissez pas plus souvent : l'échelle porte sur 2 semaines, cela n'aurait pas de sens.",
        ],
        "contraindications": (
            "Outil de dépistage et de suivi, pas de diagnostic. Il capte mal la fréquence des "
            "attaques de panique et l'évitement social, suivis séparément."
        ),
    },
    {
        "slug": "plan-prevention-rechute",
        "title": "Plan de prévention de la rechute",
        "short_label": "Plan de maintien",
        "category": "comportemental",
        "duration_min": 25,
        "up_module": 8,
        "evidence_level": "A",
        "targets": ["rechute", "suivi", "evitement"],
        "is_core": False,
        "kb_doc_id": "prevention-rechute",
        "mechanism": (
            "Après amélioration, l'anxiété remonte lors d'un stress : c'est attendu. Le danger "
            "n'est pas la remontée mais son interprétation (« ça n'a servi à rien ») qui relance "
            "les évitements. Distinguer faux pas et rechute, par écrit et à l'avance, casse cet "
            "enchaînement."
        ),
        "sources": [S_UP_BARLOW, {
            "label": "Suivi à 3 ans du Protocole Unifié — maintien des gains",
            "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC12244227/",
        }],
        "instructions": [
            "Listez ce qui a marché pour vous — l'application le génère depuis vos données réelles.",
            "Vos signaux d'alerte précoces, formulés concrètement.",
            "Votre socle d'entretien : respiration quotidienne, check-in hebdomadaire, GAD-7 mensuel, et une exposition volontaire par semaine.",
            "Votre seuil de recours : à quel moment vous consultez, et qui vous appelez.",
        ],
        "contraindications": None,
    },
]


ACTIVITIES_BY_SLUG: dict[str, dict[str, Any]] = {a["slug"]: a for a in ACTIVITIES}
CORE_SLUGS: list[str] = [a["slug"] for a in ACTIVITIES if a["is_core"]]
