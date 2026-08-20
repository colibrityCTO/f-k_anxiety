# FUCK ANXIETY — brief

Document de mise au courant. Pour le détail technique, voir `README.md` ; pour les
décisions et leurs sources, `PLAN-V5.md` ; pour l'état d'avancement, `ROADMAP.md`.

---

## En une phrase

Une application de suivi quotidien des troubles anxieux qui applique un protocole
thérapeutique validé sur douze semaines, mesure ce qui se passe réellement chez la
personne, et **refuse d'affirmer ce que ses données ne montrent pas**.

## Le problème qu'elle traite

Quelqu'un d'anxieux qui veut s'en sortir a le choix entre une thérapie (efficace, mais
avec des mois d'attente et un coût) et des applications de méditation (accessibles, mais
qui ne mesurent rien et ne s'adaptent pas). Entre les deux, il n'y a rien qui fasse le
travail d'un carnet de suivi sérieux : noter, comparer, et dire ce qui marche **chez
cette personne-là**.

Le point de départ concret était un programme de douze semaines écrit à la main et un
prototype de tracker à cases à cocher. Ni l'un ni l'autre ne mesurait quoi que ce soit —
donc ni l'un ni l'autre ne pouvait dire si le programme fonctionnait.

## Ce que c'est, concrètement

Une application web installable sur téléphone (PWA). **Le suivi tient dans un seul
écran** : un fil de conversation. On écrit en langage naturel, ou on ouvre un des vingt
et un modules de saisie avec le bouton `+`. Pas d'onglets, pas de menus.

Deux choses seulement sortent du fil, chacune pour une raison précise :

- **Le mode crise**, en plein écran — un fil qui défile coûte de l'attention qu'on n'a
  pas pendant une attaque de panique.
- **La page Compte**, en haut à droite — changer son heure de rappel n'est pas un
  événement et n'a rien à faire dans un journal de santé.

---

## Les six choses qu'elle fait

### 1. Elle guide, chaque jour, avec une raison

À l'ouverture, l'application propose **une** chose — pas une liste. Le choix est calculé
par un moteur qui combine trois sources : le socle quotidien, le module de la semaine en
cours, et ce que les données de la personne ont déclenché. Chaque proposition porte sa
justification chiffrée :

> « Ton évitement moyen déclaré est de 8/10. L'évitement est le moteur du maintien de
> l'anxiété : c'est la cible la plus rentable. »

Trois créneaux dans la journée : le matin (la nuit et l'instant), le milieu de journée
(une question, rien à remplir), le soir (la journée écoulée). Un écran « Mon parcours »
montre le reste du programme du jour sans l'imposer.

### 2. Un mode crise, en un geste

Bouton permanent, **aucun appel réseau au lancement** — une crise dans le métro est une
crise sans réseau. La séquence est *remarquer → nommer → respirer*, dans cet ordre :
nommer une sensation la **réinterprète**, respirer d'abord la **supprime**, et la
suppression répétée transforme l'outil en béquille.

Puis, si ça ne descend pas : ancrage, froid sur le visage (derrière une porte de
contre-indications que le serveur fait respecter), tâche de charge mentale.

Chaque épisode est noté avec sa durée et ce qui s'est réellement passé. Au bout de
quelques semaines, ces lignes deviennent l'argument :

> **14 épisodes. Tous passés. Durée médiane 11 min. Ce que tu redoutais est arrivé
> 0 fois.**

### 3. Elle mesure, en trois moments

Le sommeil se note **au réveil** — le rappel se dégrade vite, et l'estimation
rétrospective surestime les nuits courtes. La journée se raconte **le soir**. Et « là,
maintenant » est un curseur unique, utilisable à volonté, **jamais réclamé par
l'application**.

Le bénéfice se voit le soir : le pic et la moyenne de la journée sont **calculés** sur
les mesures prises, au lieu d'être reconstruits de mémoire. Sous anxiété, la mémoire ne
retient que les pires moments.

### 4. Elle analyse, et refuse de conclure trop vite

C'est le point qui distingue le plus cette application des autres, et il se voit surtout
dans ce qu'elle **ne** dit pas.

Huit associations sont suivies (sommeil, caféine, alcool, sport, variabilité cardiaque…).
Chacune exige au minimum quatorze paires de jours, porte un intervalle de confiance, et
passe une correction de multiplicité — sans quoi, avec huit tests, on trouve toujours
« quelque chose ».

Surtout, les corrélations sont calculées sur les **variations d'un jour sur l'autre** et
pas sur les niveaux. La différence n'est pas cosmétique : sur des données de test où deux
séries dérivent ensemble sans aucun lien, le niveau brut donne **r = −0,995** et les
variations **r = −0,015**. Une application naïve annoncerait une découverte.

Pour les combinaisons — « activité intense plus anxiété haute, puis crise le
lendemain ? » — quinze hypothèses sont **écrites à l'avance**, chacune avec sa
justification clinique. Pas de fouille automatique : une règle trouvée en croisant tout
avec tout ne vaut rien, quel que soit son résultat statistique.

Et une association qui ne survit pas à la correction **ne déclenche rien** : ni activité
proposée, ni affirmation dans l'analyse.

### 5. Elle prévoit demain, avec son plafond dit

Une fourchette (« probablement entre 4 et 7 »), jamais un chiffre unique — un chiffre
serait lu comme une promesse. La fourchette est calibrée sur les variations de la
personne : quelqu'un de stable en reçoit une étroite.

La référence à battre n'est pas le hasard, c'est **la persistance** (« demain =
aujourd'hui ») : la littérature montre que l'essentiel de la variance vient de là. Si le
modèle personnel ne bat pas la persistance en validation honnête, l'application utilise
la persistance **et le dit**. Une prévision posée la veille n'est jamais réécrite, ce qui
permet d'afficher l'erreur réelle après coup.

**Aucune crise n'est jamais prédite.** Une prédiction anxiogène est auto-réalisatrice.

### 6. Elle lit un bracelet, sans promettre l'impossible

L'intégration Whoop importe la variabilité cardiaque, la fréquence de repos, le sommeil
mesuré et les séances. Elle sert deux choses : un signal de risque **journalier**
disponible avant que la journée commence, et le croisement « séance à plus de
150 battements → crise le lendemain ? ».

Ce qu'elle ne fait pas, et c'est dit dans l'interface : **détecter une crise**. L'API ne
fournit aucune série temporelle de fréquence cardiaque, seulement des agrégats. Les
travaux qui y parviennent utilisent de l'ECG à 500 Hz. Et même si c'était possible : une
fausse alerte de panique est un déclencheur de panique. À la place, une question le
lendemain d'une séance intense.

---

## Le principe qui traverse tout : « d'où ça sort »

Chaque proposition, chaque chiffre, chaque conclusion porte un panneau dépliable qui
donne quatre choses : le **mécanisme** d'action, le **niveau de preuve** (A, B ou C), les
**références cliquables**, et les **données personnelles exactes** qui ont déclenché la
proposition.

Trente-et-une fiches sourcées constituent le corpus. Le niveau de preuve est affiché
**y compris quand il est mauvais** :

- Le yoga : aucun effet retrouvé chez les patients dont le trouble est diagnostiqué selon
  les critères du DSM. C'est écrit sur l'activité.
- L'ACT : comparable à la TCC, **pas supérieure**. Écrit aussi.
- La tâche de charge mentale du mode crise : le niveau B porte sur les souvenirs
  intrusifs post-traumatiques, pas sur la panique. Proposée en dernier, avec la réserve.

## Ce que l'application refuse de faire

Ce sont des décisions, pas des manques :

- **Pas de gamification.** Ni badge, ni série à préserver, ni félicitation pour une
  variation sous le seuil de signification clinique — célébrer du bruit entraîne à
  surveiller du bruit, ce qui est une forme d'hypervigilance.
- **Le modèle de langage ne calcule rien et n'écrit rien.** Les statistiques sont du
  Python, exécuté sur l'historique complet. Le modèle rédige et choisit quel module
  ouvrir ; c'est l'utilisateur qui valide, toujours.
- **Le passé ne se réécrit pas.** Un module validé est figé ; « corriger » en ouvre un
  neuf.
- **Aucune statistique collective sous onze personnes** par comparaison — en dessous,
  c'est à la fois faux et ré-identifiant.
- **Aucun diagnostic, aucun conseil médicamenteux.** Un module de sécurité détecte les
  formulations évoquant des idées suicidaires, suspend tout le reste et affiche le 3114.

## Ce qui est en place et ce qui attend

**En place et vérifié** : les six fonctions ci-dessus, quatorze suites de tests
automatisés (157 vérifications sur la seule V5) qui tournent contre une vraie base de
données.

**En attente, et pas pour des raisons techniques :**

| | Ce qui manque |
|---|---|
| Whoop | des identifiants `developer.whoop.com` — le code est écrit et testé |
| Statistiques collectives | des utilisateurs. Le seuil est de onze personnes par comparaison |
| Recherche sémantique | une clé d'API d'embeddings ; sans elle, la recherche fonctionne en plein texte |

## Cadre

Ce n'est **pas un dispositif médical certifié** et ça ne remplace pas une psychothérapie
encadrée. C'est une intervention dite de « faible intensité » au sens des recommandations
NICE — l'étape 1 d'un parcours de soin, celle qui précède ou accompagne une prise en
charge. Un score élevé au GAD-7, ou l'absence d'amélioration après six à huit semaines,
déclenche un message qui dit que la suite recommandée est une TCC accompagnée : ce n'est
pas un échec de l'application, c'est la suite prévue.

Un rapport imprimable noir sur blanc rassemble tout ce qu'un professionnel a besoin de
lire : courbes, scores avec leurs seuils, épisodes avec leur issue, ce qui a été fait et
ce qui ne l'a pas été.

## Technique, en trois lignes

API **FastAPI** (Python) et front **React + Vite + TypeScript**, base **PostgreSQL** avec
`pgvector` pour la mémoire vectorisée. Vingt-trois tables, cinquante-sept routes, environ
vingt-deux mille lignes. Déployé sur Railway en trois services. Fonctionne **sans aucune
clé d'API** : les réponses passent alors par des règles explicites, et l'interface le dit
au lieu de le masquer.

## Les trois phrases à retenir

1. **Tout se mesure, et rien n'est affirmé sans preuve** — y compris quand la preuve
   manque, ce qui est dit explicitement.
2. **Le rôle du modèle de langage est de rédiger, pas de décider ni de calculer.**
3. **Ce qu'elle refuse de faire est aussi réfléchi que ce qu'elle fait** — pas de
   gamification, pas de détection de crise, pas de statistique collective prématurée.
