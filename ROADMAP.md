# Feuille de route

## V1 — le fil (livrée)

Un seul écran, un seul fil. Pas de navigation, pas d'onglets, pas de pages. Tout ce que fait
l'application est soit un **message**, soit un **widget** dans la conversation — y compris se
déconnecter.

**Les deux façons d'entrer une donnée**

1. Tu écris librement. L'extraction déterministe lit les chiffres de ta phrase, l'assistant te
   répond et **pré-remplit** le widget correspondant. Rien n'est enregistré avant que tu
   valides : un modèle de langage ne doit pas pouvoir écrire une donnée de santé sans ton
   accord. Les valeurs déduites d'une formulation qualitative (« nuit pourrie » → 5 h) sont
   marquées « déduit de ta phrase — vérifie ».
2. Tu ouvres le widget toi-même avec le **+**.

**Acquis** : ouverture proactive une fois par jour ; widgets figés après validation
(« Corriger » ouvre un widget neuf, on ne réécrit jamais le passé) ; réponses pré-choisies
attachées au message de l'assistant ; panneau « D'OÙ ÇA SORT » partout ; mémoire personnelle
vectorisée sans limite d'ancienneté ; détection des idées suicidaires qui suspend tout le reste.

## V2 — approfondir (livrée)

- **Exposition** : échelle personnelle, prédiction avant / résultat après / apprentissage. Une
  tentative crée aussi une entrée de journal, sinon l'écart prédiction-réalité serait invisible
  dans l'analyse.
- **Méditation** : souffle, scan corporel, conscience émotionnelle, relaxation — minuteur et étapes.
- **Échelles** : GAD-7, PHQ-2, évitement dans un seul widget, chacune commentée selon **sa** DMCI.
- **Mémoire** : recherche dans son propre historique vectorisé.
- **Streaming SSE réel** : prose diffusée token par token, pied `---WIDGET---` retenu et jamais
  affiché. Un JSON unique n'aurait pas pu être streamé.
- **Correction d'un jour antérieur** au check-in, bornée à 60 jours, jamais dans le futur.

## V3 — tenir dans le temps (livrée)

**Quatorze widgets** au total. Les quatre apports de cette version :

| Apport | Détail |
|---|---|
| **Sensations** (intéroceptif) | 8 exercices avec minuteur — hyperventilation, apnée, paille, rotation, escaliers, tension, fixation, secouer la tête. Porte de contre-indications validée **une fois** et datée dans le profil : sans elle, l'API refuse d'enregistrer. Le bouton de lancement reste inactif tant que la prédiction n'est pas écrite. |
| **Régime d'entretien** | Bascule automatique au critère de sortie (GAD-7 ≤ 5 sur 4 mesures **et** plus aucun item d'exposition non maîtrisé). En entretien : check-in hebdomadaire, GAD-7 mensuel, et une exposition volontaire par semaine — c'est ce qui distingue ceux qui rechutent de ceux qui ne rechutent pas. Retour automatique en programme actif si le GAD-7 remonte de 4 points (la DMCI) au-dessus du seuil de rémission. |
| **Bilan hebdomadaire** | Déposé de lui-même dans le fil, au plus une fois tous les 7 jours et seulement à partir de 10 jours renseignés. C'est une **proposition** : générer coûte un appel au modèle, un clic suffit à le lancer. |
| **Rapport imprimable** | Widget Rapport → document noir sur blanc : cadre et limites en tête, signaux avec leur méthode, GAD-7 et ses seuils, échelle d'expositions, apprentissages, activités faites et non faites, suivi quotidien. Aucune dépendance PDF : la fenêtre d'impression du navigateur suffit. |
| **PWA + rappel** | Manifest, icônes, service worker (coque hors-ligne, **jamais** l'API en cache : une donnée de santé périmée est une donnée fausse). Rappel quotidien à l'heure choisie, qui ne part que si le check-in manque encore. |

## V4 — ce qui reste

- **Notification push serveur** (clé VAPID + service de push). C'est la seule façon d'avoir un
  rappel fiable application fermée ; aujourd'hui le rappel dépend d'une application ouverte ou en
  arrière-plan, et l'interface le dit.
- **Édition d'une entrée de journal passée** — seul le check-in est rétroactif pour l'instant.
- **Analyse hebdomadaire vraiment automatique** (worker planifié) plutôt qu'une proposition déposée
  à l'ouverture.
- **Chiffrement au repos** du contenu du journal, avec la conséquence à assumer : la recherche
  plein texte côté serveur devient impossible.
- **Export des données** (JSON) et suppression de compte en autonomie.

## Hors périmètre, volontairement

Pas de diagnostic. Pas de conseil médicamenteux. Pas de gamification : ni badge, ni série à
préserver, ni félicitation pour une variation inférieure au seuil de signification clinique —
célébrer du bruit entraîne à surveiller du bruit, ce qui est une forme d'hypervigilance.
