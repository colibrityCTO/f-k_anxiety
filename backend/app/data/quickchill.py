"""QUICK CHILL — les outils du pic d'anxiété, et ce que la preuve dit de chacun.

Trois décisions de conception, qui comptent autant que le contenu.

**L'ordre : remarquer → nommer → respirer.** Pas respirer d'abord. Nommer une
sensation réduit la réponse de l'amygdale et les indicateurs physiologiques de
réactivité, par inhibition préfrontale — et c'est une régulation *implicite*, elle
ne demande pas d'effort de contrôle. Surtout, l'ordre change ce qu'on apprend :
nommer d'abord **réinterprète** la sensation (« c'est mon système sympathique, pas
mon cœur »), respirer d'abord la **supprime**. La suppression, répétée, fabrique un
comportement de sécurité.

**Le risque assumé, et mesuré.** Un mode panique est par construction un candidat
au comportement de sécurité : si l'application devient ce qui *empêche* la
catastrophe, elle entretient l'anxiété en empêchant la prédiction catastrophique
d'être mise à l'épreuve (Craske et al. 2014). La littérature n'est pas univoque —
un essai spécifique sur le travail respiratoire chez des personnes craignant les
sensations respiratoires n'a **pas** retrouvé l'effet délétère attendu. Ce n'est
donc pas une raison de renoncer, c'est une raison de compter les usages et de le
dire (`USAGE_ALERT_PER_WEEK`).

**Le cadrage du texte n'est pas cosmétique.** « Quelque chose à faire pendant que
ça passe » plutôt que « respire et ça s'arrête ». La seconde formulation promet un
contrôle qui n'existe pas, et c'est elle qui crée la dépendance.
"""

from __future__ import annotations

from typing import Any

# Au-delà de ce nombre d'ouvertures par semaine, l'application le dit et propose de
# rebasculer vers l'exposition intéroceptive — à condition que le GAD-7 ne bouge pas
# au-delà de sa DMCI. Le seuil est arbitraire et assumé comme tel : ce qui compte
# est qu'il soit fixé à l'avance et visible, pas qu'il soit exact.
USAGE_ALERT_PER_WEEK = 10

# Ce qu'on répond quand quelqu'un demande si ça va arrêter la crise.
FRAMING = (
    "Ça ne va pas empêcher la crise et ça ne l'écourtera pas forcément. Ça te donne "
    "quelque chose à faire pendant que ça passe — et ça passe toujours."
)

# --- Étape 1 : remarquer ----------------------------------------------------

BODY_AREAS: list[str] = [
    "poitrine",
    "gorge",
    "ventre",
    "tête",
    "mains",
    "jambes",
    "partout",
]

# --- Étape 2 : nommer -------------------------------------------------------
#
# Les quatre formulations viennent du programme 12 semaines, qui les donne comme les
# pensées typiques du moment. Les proposer écrites évite d'avoir à trouver ses mots
# au pire moment — et le fait de choisir est déjà un acte de nommage.

THOUGHTS: list[dict[str, str]] = [
    {
        "label": "Je vais mourir",
        "reframe": (
            "C'est la pensée, pas le fait. Une attaque de panique est une décharge "
            "d'adrénaline : très désagréable, sans danger pour le cœur."
        ),
    },
    {
        "label": "J'étouffe",
        "reframe": (
            "La sensation de manque d'air pendant une panique vient d'une "
            "hyperventilation — tu respires **trop**, pas trop peu. D'où l'expiration "
            "longue plutôt qu'une grande inspiration."
        ),
    },
    {
        "label": "Je deviens fou",
        "reframe": (
            "L'irréalité et la sensation de détachement sont des effets connus de "
            "l'hypocapnie. Elles s'arrêtent quand la respiration se rééquilibre."
        ),
    },
    {
        "label": "Je perds le contrôle",
        "reframe": (
            "L'activation monte, culmine, puis redescend d'elle-même — c'est "
            "physiologique, ça ne dépend pas de ta volonté. Rien à contrôler."
        ),
    },
]

# --- Étapes 3 à 6 : les outils, dans l'ordre de proposition -----------------
#
# L'ordre suit le niveau de preuve, pas l'efficacité ressentie. Le jeu arrive en
# dernier parce que son transfert vers la panique n'est pas démontré, et c'est dit.

TOOLS: list[dict[str, Any]] = [
    {
        "slug": "expiration-longue",
        "name": "Expiration allongée",
        "step": "respirer",
        "seconds": 180,
        "how": "Inspire 4 secondes par le nez. Expire 8 secondes par la bouche. C'est l'expiration qui fait le travail.",
        "pattern": {"inhale": 4, "hold": 0, "exhale": 8},
        "evidence": "B",
        "mechanism": (
            "L'expiration longue augmente l'influence parasympathique sur le nœud "
            "sinusal : le rythme cardiaque ralentit à chaque expiration. L'effet est "
            "mécanique avant d'être psychologique, ce qui explique sa rapidité."
        ),
        "caveat": (
            "Dans l'essai randomisé de référence, le soupir cyclique a amélioré "
            "l'humeur et baissé la fréquence respiratoire — mais **sans** modifier la "
            "variabilité cardiaque ni la fréquence cardiaque de repos. Ne t'attends "
            "pas à voir ton pouls chuter."
        ),
        "sources": [
            {
                "label": "Balban et al., Cell Reports Medicine 2023 — essai randomisé, 108 participants",
                "url": "https://www.cell.com/cell-reports-medicine/fulltext/S2666-3791(22)00474-8",
            },
        ],
        "contraindications": None,
    },
    {
        "slug": "soupir-cyclique",
        "name": "Soupir physiologique",
        "step": "respirer",
        "seconds": 120,
        "how": "Deux inspirations nasales d'affilée — une longue, puis une courte par-dessus. Puis une expiration buccale très longue.",
        "pattern": {"inhale": 3, "hold": 1, "exhale": 8},
        "evidence": "B",
        "mechanism": (
            "La double inspiration réinsuffle les alvéoles partiellement collabées, "
            "ce qui améliore l'échange gazeux et évacue le CO₂ accumulé."
        ),
        "caveat": None,
        "sources": [
            {
                "label": "Balban et al., Cell Reports Medicine 2023 — le soupir cyclique fait mieux que le box breathing sur l'humeur",
                "url": "https://www.cell.com/cell-reports-medicine/fulltext/S2666-3791(22)00474-8",
            },
        ],
        "contraindications": None,
    },
    {
        "slug": "ancrage",
        "name": "Ancrage 5-4-3-2-1",
        "step": "ancrer",
        "seconds": 120,
        "how": "Cinq choses que tu vois. Quatre que tu entends. Trois que tu touches. Deux que tu sens. Une que tu goûtes.",
        "pattern": None,
        "evidence": "C",
        "mechanism": (
            "Réorientation de l'attention vers l'extérieur. Pendant une panique, "
            "l'attention se resserre sur les sensations internes, ce qui les amplifie."
        ),
        "caveat": (
            "Niveau C : consensus clinique large, mais pas d'essai randomisé propre à "
            "cette technique. On te la propose en le disant."
        ),
        "sources": [],
        "contraindications": None,
    },
    {
        "slug": "froid",
        "name": "Froid sur le visage",
        "step": "froid",
        "seconds": 60,
        "how": "De l'eau très froide sur le visage, ou un pack froid sur les joues et les tempes, 30 à 60 secondes. En retenant ta respiration si tu peux, l'effet est plus fort.",
        "pattern": None,
        "evidence": "C",
        "mechanism": (
            "Réflexe d'immersion : le froid sur le visage déclenche une bradycardie "
            "réflexe. La baisse de fréquence cardiaque va de 10 à 25 % chez l'adulte "
            "non entraîné, et l'apnée la renforce."
        ),
        "caveat": (
            "La physiologie est solide, les essais cliniques en anxiété sont rares et "
            "petits. C'est un outil de secours, pas un traitement."
        ),
        "sources": [
            {
                "label": "Réponse cardiaque à l'immersion faciale en eau froide avec apnée",
                "url": "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10295257/",
            },
        ],
        # Cette liste est la raison d'être de la porte : le froid brutal n'est pas
        # anodin. Elle est validée une fois, datée dans le profil, et l'API refuse
        # d'enregistrer l'usage de cet outil sans elle.
        "contraindications": (
            "un trouble du rythme cardiaque, une maladie du cœur, un trouble du "
            "comportement alimentaire, un syndrome de Raynaud, ou une hypertension "
            "non contrôlée"
        ),
    },
    {
        "slug": "jeu",
        "name": "Jeu de placement",
        "step": "jeu",
        "seconds": 180,
        "how": "Place les blocs. Ça n'a aucun intérêt en soi — c'est la charge visuo-spatiale qui compte.",
        "pattern": None,
        "evidence": "C",
        "mechanism": (
            "Une tâche à forte charge visuo-spatiale entre en compétition pour des "
            "ressources cognitives limitées, ce qui laisse moins de place à l'imagerie "
            "mentale de la catastrophe."
        ),
        "caveat": (
            "**À lire avant de l'utiliser.** Le niveau B de cette approche porte sur "
            "les *souvenirs intrusifs* après un traumatisme, où un essai randomisé aux "
            "urgences a montré une réduction. Le transfert vers l'attaque de panique "
            "n'est **pas** démontré : ici, c'est du niveau C par extrapolation. "
            "Proposé en dernier pour cette raison."
        ),
        "sources": [
            {
                "label": "Iyadurai et al., Molecular Psychiatry 2018 — Tetris aux urgences, souvenirs intrusifs (pas panique)",
                "url": "https://www.nature.com/articles/mp201723",
            },
        ],
        "contraindications": None,
    },
]

TOOLS_BY_SLUG = {tool["slug"]: tool for tool in TOOLS}

COLD_GATE_SLUG = "froid"

SOURCES = [
    {
        "label": "Torre & Lieberman, Emotion Review 2018 — nommer un affect comme régulation émotionnelle implicite",
        "url": "https://journals.sagepub.com/doi/10.1177/1754073917742706",
    },
    {
        "label": "Lieberman et al., Psychological Science 2007 — mettre des mots sur ses émotions réduit la réponse de l'amygdale",
        "url": "https://journals.sagepub.com/doi/10.1111/j.1467-9280.2007.01916.x",
    },
    {
        "label": "Craske et al., Behav Res Ther 2014 — apprentissage inhibiteur, et le rôle des comportements de sécurité",
        "url": "https://pubmed.ncbi.nlm.nih.gov/24864005/",
    },
    {
        "label": "Meuret et al. 2020 — le travail respiratoire chez ceux qui craignent les sensations respiratoires : pas d'effet délétère retrouvé",
        "url": "https://pubmed.ncbi.nlm.nih.gov/32759117/",
    },
]
