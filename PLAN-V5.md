# V5 — Analyse et plan d'implémentation

Réponse aux sept demandes : guidage quotidien, QUICK CHILL, onboarding, moteur de patterns
(individuel + cohorte), score du jour et prédiction J+1, Whoop, navigation dans le fil.

Chaque point suit la même structure : **ce qui existe déjà dans le code**, **ce qui manque
vraiment**, **ce que dit la preuve** quand la question l'exige, **comment on le fait**.

---

## 0. Périmètre de cette analyse — ce que je n'ai pas pu lire

Deux fichiers étaient joints et **macOS a refusé l'accès** à `~/Downloads` (erreur `EPERM`,
protection TCC) : `Программа 3 месяца тревожность.pdf` et `tracker.html`. Ni le shell ni les
outils de lecture n'ont pu les ouvrir.

Ce que ça change, et ce que ça ne change pas :

- **Le programme 3 mois** : `backend/app/program.py` implémente déjà 8 modules sur 12 semaines
  (Protocole Unifié) et `backend/knowledge/` contient 21 fiches sourcées. J'ai donc travaillé sur
  cette version-là. Si le PDF contient une progression différente (ordre des modules, contenu
  hebdomadaire), c'est `MODULES` dans `program.py` qu'il faudra corriger — la structure
  d'accueil est bonne, seul le contenu de la liste changerait.
- **`tracker.html`** : je n'ai aucune idée de ce qu'il contient. S'il s'agit d'un prototype de
  suivi avec des champs absents du schéma actuel, il faut le comparer à `daily_checkins` avant
  le lot 3.

Pour débloquer :

```bash
mkdir -p /Users/mikhailvasyuk/WindSurf/fuck_anxiety/_inbox && cp ~/Downloads/tracker.html ~/Downloads/"Программа 3 месяца тревожность.pdf" /Users/mikhailvasyuk/WindSurf/fuck_anxiety/_inbox/
```

Tout le reste de ce document est établi par lecture du code (13 700 lignes, backend + frontend)
et par recherche documentaire sourcée.

---

## 1. Verdict global

| # | Demande | Faisable ? | Ce qui bloque | Effort |
|---|---|---|---|---|
| 1 | Guidage quotidien à chaque ouverture | **Oui, en grande partie déjà écrit** | Le moteur `build_day()` n'est jamais appelé par le fil | Faible → moyen |
| 2 | Bouton QUICK CHILL | **Oui** | Rien de technique. Un vrai risque de conception (comportement de sécurité) | Moyen |
| 3 | Onboarding qui adapte le programme | **Oui** | Il n'existe **aucun** onboarding ; une règle adaptative est morte de ce fait | Moyen |
| 4 | Patterns individuels | **Oui, mais la statistique actuelle est trop permissive** | Seuil n≥6, pas de correction de multiplicité, autocorrélation ignorée | Moyen |
| 4b | Patterns de cohorte anonyme | **Oui techniquement, pas maintenant** | Effectifs (seuil de 11 personnes/cellule) + base légale art. 9 RGPD | Élevé |
| 5 | Score du jour + prédiction J+1 | **Oui, avec un plafond de performance à assumer** | Le modèle doit battre « demain = aujourd'hui », sinon ne rien afficher | Moyen |
| 6 | Whoop : import des données | **Oui** | OAuth + stockage des jetons | Moyen |
| 6b | Whoop : détection automatique des crises | **Non** | **L'API Whoop n'expose aucune série temporelle de FC** | — |
| 7 | Widgets qui polluent l'historique | **Oui** | Confusion entre widget de saisie et widget de consultation | Faible |

---

## 2. Analyse point par point

### P1 — « Qu'il me guide dans mon parcours quotidien : un conseil, une question, une activité »

#### Ce qui existe déjà

`build_day()` (`backend/app/program.py`) construit **déjà** exactement ce qui est demandé :

- le **socle** quotidien (check-in, respiration lente, journal libre) ;
- les activités du **module** de la semaine en cours ;
- jusqu'à 4 items **adaptatifs**, déclenchés par 8 règles à seuils explicites (sommeil corrélé,
  paniques récentes, évitement ≥ 5, caféine corrélée, sédentarité, anxiété en hausse, adhérence
  < 0,4, difficulté sociale déclarée) ;
- pour chaque item : `why_for_you` (la raison en français, avec les chiffres) et `triggered_by`
  (les observations exactes qui l'ont déclenché — déjà au format du panneau « D'OÙ ÇA SORT »).

#### Le vrai problème : ce moteur n'est pas branché

`build_day()` est exposé par `GET /program/day` (`routers/program.py:20`). **Le frontend ne
l'appelle jamais** : `frontend/src/lib/api.ts` ne contient que `/program/history`. Côté fil,
l'ouverture proactive est produite par `opening()` (`app/chat.py`), qui a **quatre branches
déterministes** : mode entretien, check-in manquant, GAD-7 dû, rien à faire.

Autrement dit : le guidage adaptatif est écrit, testé, sourcé — et invisible. C'est la
correction la plus rentable de tout ce document.

Quatre manques réels au-delà de ça :

1. **Une seule chose est proposée** à l'ouverture, alors que le plan du jour en contient 5 à 8.
2. **Pas de question**. Le fil ouvre un widget ; il ne pose jamais de question ouverte.
3. **Pas de séquencement dans la journée.** `daily_checkins.moment` (`matin` | `soir`) existe
   dans le schéma et **rien ne l'exploite**.
4. **Rien ne relance.** Un item non fait le matin n'est pas reproposé le soir.

#### Comment on le fait

- **P1.a — brancher `build_day()` sur `opening()`.** `opening()` prend le plan du jour et
  choisit **un seul** item, par ordre de priorité : sécurité > check-in manquant > mesure due >
  item adaptatif le plus fortement déclenché > item de module > entretien. Le message reprend
  `why_for_you` mot pour mot ; le panneau de traçabilité est alimenté par `triggered_by`, déjà
  au bon format. Aucune migration, aucun nouvel appel LLM.
- **P1.b — un widget `jour`.** La liste des items du jour avec leur `slot` (socle / module /
  adaptatif), leur état (fait / pas fait / reporté) et un bouton qui ouvre le widget
  correspondant. C'est la réponse à « guide-moi dans mon parcours » sans casser la règle « un
  seul écran ».
- **P1.c — trois créneaux au lieu d'un.** Étendre l'ouverture proactive à matin / milieu de
  journée / soir, une invite maximum par créneau. L'idempotence se fait avec la même mécanique
  que `notification_log` (contrainte d'unicité `(user_id, kind, sent_on)`), donc rien à
  inventer : `kind = 'ouverture_matin' | 'ouverture_midi' | 'ouverture_soir'`.
  - Le matin : **une question et un conseil**, pas un widget — « qu'est-ce qui est prévu
    aujourd'hui qui t'inquiète ? ». La réponse alimente `main_trigger` et la prédiction (P5).
  - Le soir : le check-in.
  - Garde-fou : les invites contextuelles (JITAI) tiennent l'engagement, mais l'adhésion est
    hétérogène et modérée dans les essais — dans une étude à randomisation micro, 90 % d'usage
    actif en semaine 3, 59 % en semaine 6, et une demande de soutien dans un tiers des cas
    seulement après déclenchement. **Trois invites par jour est un plafond, pas une cible.**
- **P1.d — question du jour déterministe.** Une table de questions courtes, tirées selon le
  module et les signaux, pas générées par un LLM (reproductibilité, coût, et le modèle ne doit
  pas décider du contenu clinique). La réponse s'écrit dans `journal_entries` (`kind='libre'`)
  et part donc automatiquement dans la mémoire vectorisée.

**Contrainte à ne pas violer** : `ROADMAP.md` exclut explicitement la gamification. Le guidage
ne doit pas devenir une check-list culpabilisante. Un seul item est présenté comme attendu (le
check-in) ; tout le reste est optionnel, et **dit** comme optionnel.

---

### P2 — QUICK CHILL

#### Ce qui existe

Widget `breath` (5 min, ~6 cycles/min), activité `soupir-physiologique` (3 min), fiche
`knowledge/03-respiration-aigue.md`, widget `interoceptif` (8 exercices). Tout le contenu est
là. Le problème est le **chemin d'accès** : ouvrir `+`, choisir une tuile, attendre un
aller-retour réseau qui crée un `thread_item`. En pleine crise, c'est trois gestes de trop et
une dépendance réseau de trop.

#### Ce que dit la preuve, outil par outil

C'est le point qui demandait le plus de vérification : « il faut analyser ce qui aide ».

| Outil | Mécanisme | Niveau | Ce qu'il faut savoir |
|---|---|---|---|
| **Soupir cyclique / expiration allongée** | double inspiration → réouverture alvéolaire, évacuation du CO₂ ; expiration longue → influence parasympathique sur le nœud sinusal | **B** (ECR, 108 participants) | Supérieur à la méditation de pleine conscience sur l'humeur et la fréquence respiratoire. **Mais : aucun changement de VFC ni de FC de repos** dans cet essai — ne jamais promettre « ton pouls va descendre » |
| **Respiration lente ~6 c/min** | résonance cardio-respiratoire | **B** (méta-analyse) | Effet d'**entraînement**, à froid, sur des semaines. En pic, c'est l'expiration qui fait le travail |
| **Principe CART** (respirer *moins*, pas *plus fort*) | corrige l'hypocapnie de l'hyperventilation | **A−** pour le trouble panique (ECR ; essai multisite : réponse 83 %, rémission 54 %) | Sans capnomètre on ne mesure pas le CO₂. On garde le principe, on le dit, on ne prétend pas faire du CART |
| **Froid sur le visage / immersion** (TIPP en TCD) | réflexe d'immersion → bradycardie, **−10 à −25 % de FC** chez l'adulte non entraîné, renforcé par l'apnée | **C → B** : physiologie solide, essais cliniques rares et petits | Contre-indications réelles : troubles du rythme, cardiopathie, troubles alimentaires, Raynaud. **Doit passer par la même porte de contre-indications que l'intéroceptif** |
| **Ancrage 5-4-3-2-1** | réorientation attentionnelle externe | **C** — consensus clinique, pas d'ECR propre | À proposer en le disant : niveau C |
| **Jeu à forte charge visuo-spatiale** (type Tetris) | compétition pour les ressources visuo-spatiales limitées | **B pour les souvenirs intrusifs** (ECR aux urgences, ~20 min de jeu) ; **C par extrapolation pour la panique** | Le transfert de « souvenirs intrusifs post-traumatiques » vers « attaque de panique » **n'est pas démontré**. À proposer en dernier, étiqueté comme tel |

#### Le vrai enjeu : ne pas fabriquer un comportement de sécurité

Un « mode panique » est par construction un candidat au comportement de sécurité. Si
l'application devient ce qui *empêche* la catastrophe, elle entretient l'anxiété en empêchant la
prédiction catastrophique d'être mise à l'épreuve — c'est le mécanisme décrit par
l'apprentissage inhibiteur (Craske et al. 2014), déjà cité dans le corpus.

La littérature n'est pas univoque : la thèse d'un effet systématiquement délétère des
comportements de sécurité a été contestée, et un essai spécifique sur le travail respiratoire
chez des personnes craignant les sensations respiratoires **n'a pas retrouvé** d'effet néfaste
sur la sensibilité anxieuse. Ce n'est donc pas une raison de renoncer, c'est une raison de
concevoir en le sachant. Deux garde-fous **mesurables** :

1. **Compter les ouvertures.** Si QUICK CHILL est lancé plus de N fois par semaine et que le
   GAD-7 ne bouge pas au-delà de sa DMCI (4 points), l'application le dit et rebascule la
   proposition vers l'exposition intéroceptive. C'est calculable avec les tables existantes.
2. **Le cadrage du texte.** « Ça ne t'empêche pas de faire une crise et ça ne l'écourte pas
   forcément. Ça te donne quelque chose à faire pendant que ça passe » — plutôt que « respire
   et ça s'arrête ». La deuxième formulation *crée* la dépendance.

#### Comment on le fait

- **Bouton permanent dans `Composer`**, à côté du `+`. Pas dans la grille : accessible en un
  geste.
- **Écran plein, hors du fil** pendant la crise. Le fil défile, c'est coûteux cognitivement.
  C'est la seule exception assumée à « tout est dans le fil » — et un item récapitulatif est
  déposé dans le fil **après**, donc la règle est respectée là où elle compte (la trace).
- **Zéro appel réseau au lancement.** Séquences respiratoires, ancrage et jeu embarqués dans le
  bundle et dans le service worker. Une crise dans le métro, c'est une crise sans réseau. À
  noter : le service worker actuel ne met **jamais** l'API en cache (décision correcte) — le
  contenu de QUICK CHILL doit donc être du statique, pas une réponse d'API.
- **Séquence graduée** : (1) « où tu en es, 0-10 » en un tap → (2) respiration guidée, défaut
  expiration allongée 4 s / 8 s pendant 3 min → (3) « ça descend ? » → si non : ancrage, puis
  froid (derrière la porte de contre-indications), puis jeu → (4) 0-10 après → (5) écrire ce
  qui s'est passé, optionnel.
- **Nouvelle table `panic_episodes`** : début, fin, anxiété avant / pic / après, outils utilisés
  **et leur ordre**, lieu optionnel, ce qui a aidé. C'est la table qui alimente P4, P5 et P6 —
  sans elle, « détecter les crises » et « prédire » n'ont aucune vérité de référence.
- `daily_checkins.panic_attacks` est incrémenté **à la validation** de l'épisode, pas
  automatiquement : la règle « l'IA n'écrit rien sans validation » s'applique aussi ici.

---

### P3 — Onboarding

#### Ce qui existe : rien, et ça casse quelque chose

`users.profile` est un `jsonb` libre, écrit uniquement par `PATCH /auth/me`. Aucun écran, aucun
widget, aucune question à la première connexion.

Conséquence concrète, et c'est un **bug**, pas un manque : `program.py:adaptive_items` contient
une règle n° 8 qui lit `profile.get("difficultes")` et cherche la valeur `"social"` pour
proposer `experience-sociale`. **Personne n'écrit jamais cette clé.** La règle est morte.

#### Ce qu'il faut demander

Ordre et longueur comptent : 2 à 3 minutes maximum, sinon abandon.

1. **Cibles et valeurs** — « qu'est-ce que l'anxiété t'empêche de faire ? » (texte libre ;
   correspond à l'activité `objectifs-valeurs` du module 1).
2. **Difficultés principales**, cases à cocher : panique/sensations, social, inquiétude
   généralisée, santé, travail, agoraphobie, sommeil → écrit `profile.difficultes` → **débloque
   la règle 8** et permet d'en écrire d'autres.
3. **Ligne de base chiffrée** : GAD-7 (7 items) + PHQ-2 (2 items). Déjà implémentés dans
   `routers/assessments.py`. **Libres de droits** : Pfizer a levé le copyright du PHQ et du
   GAD-7 en 2010, aucune autorisation requise pour reproduire, traduire ou diffuser.
4. **Sensibilité anxieuse** (peur des sensations corporelles) — c'est le facteur qui décide s'il
   faut avancer l'exposition intéroceptive. ⚠️ **L'ASI-3 n'est pas libre** : publié par IDS
   Publishing, usage réservé aux professionnels qualifiés. **Ne pas l'embarquer.** Deux options
   honnêtes : (a) 3 items maison, explicitement présentés comme non validés ; (b) acquérir une
   licence. Je recommande (a) avec la mention, quitte à basculer sur (b) plus tard.
5. **Panique** : déjà eu des attaques ? combien le mois dernier ? à quoi ça ressemble ? — les
   sensations citées pré-remplissent la liste du widget `interoceptif`.
6. **Contre-indications médicales** : la porte existe déjà pour l'intéroceptif (validée une fois
   et datée dans le profil, l'API refuse d'enregistrer sans elle). La remonter dans l'onboarding
   évite de bloquer l'utilisateur au module 6 — et elle sert aussi au froid de QUICK CHILL.
7. **Retentissement fonctionnel** : le WSAS (5 items) est le standard, mais son statut de
   licence n'est pas clairement libre ; à défaut, un curseur maison assumé comme tel.
8. **Habitudes de départ** : cafés/jour, alcool/semaine, sport/semaine, heure de coucher →
   valeurs par défaut du check-in, ce qui réduit la friction quotidienne.
9. **Fuseau et heure de rappel** — `scheduler.py` lit déjà `profile.rappel.heure` et
   `profile.rappel.actif`.
10. **Sécurité** : une question de dépistage du risque suicidaire, avec le 3114 affiché quelle
    que soit la réponse.
11. **Consentements, deux cases séparées** : (a) traitement des données de santé, (b)
    contribution anonyme aux statistiques collectives (P4b). **La seconde doit être refusable
    sans perte de fonction** — c'est une exigence, pas une politesse.

#### Comment on le fait

- Nouveau widget `onboarding` multi-étapes, déposé par `GET /chat/thread` si
  `profile.onboarding.done_at` est absent — **même mécanique que l'ouverture proactive**, donc
  rien de neuf à inventer côté serveur.
- Écriture : `users.profile` structuré et **versionné** (`profile.onboarding = {version, done_at,
  difficultes, …}`), les échelles dans `assessments`, les objectifs dans `journal_entries`.
- **L'adaptation du programme, c'est là que ça devient utile.** Ajouter dans `program.py` des
  règles qui lisent le profil et pas seulement les signaux :
  - `panique` dans `difficultes`, ou sensibilité anxieuse haute → avancer
    `exposition-interoceptive` du module 6 vers le module 3 ;
  - `social` → `experience-sociale` dès le module 4 (la règle existe, il suffit que la clé soit
    écrite) ;
  - `inquietude` → `temps-inquietude` et `resolution-problemes` renforcés ;
  - rien de déclaré → parcours canonique inchangé.
- **Réversibilité** : « refaire l'onboarding » depuis le widget `account`, en écrivant une
  nouvelle version — jamais en écrasant l'ancienne. Cohérent avec « le passé ne se réécrit pas ».

---

### P4 — Moteur d'analyse des patterns

#### Ce qui existe

`signals.py` calcule 14 signaux, dont 5 corrélations de Pearson décalées : sommeil J → anxiété
J+1, qualité de sommeil J → J+1, caféine J → J, alcool J → J+1, sport J → J. Chaque signal porte
ses observations brutes, sa méthode et son `n`. La traçabilité est exemplaire.

#### Cinq limites réelles, et ce qu'on fait

1. **`n ≥ 6` pour déclencher une corrélation, c'est beaucoup trop peu.** Avec 6 paires, un
   `r = 0,7` n'est pas significatif — et le verdict « association marquée » se déclenche dès
   `|r| ≥ 0,6`. L'application affiche donc du bruit comme un fait. → **Monter à `n ≥ 14`** pour
   afficher un verdict, et remplacer l'adjectif par un **intervalle de confiance** (transformée
   de Fisher, quelques lignes de Python pur, aucune dépendance).
2. **Multiplicité des tests.** 5 corrélations × plusieurs décalages × plusieurs fenêtres : on
   trouvera toujours « quelque chose ». → **Correction de Benjamini-Hochberg** sur la famille de
   tests, et n'afficher que ce qui survit. Sans ça, l'application **fabrique des croyances** —
   exactement ce dont un anxieux n'a pas besoin.
3. **Pearson ignore la tendance et l'autocorrélation.** L'anxiété est fortement autocorrélée
   d'un jour sur l'autre ; deux séries qui dérivent ensemble corrèlent sans lien causal. →
   Corréler les **écarts au niveau personnel** : différences premières, ou résidus après retrait
   d'une moyenne mobile 7 jours.
4. **Rien ne teste les combinaisons** — et c'est précisément la demande (« activité intensive +
   niveau d'anxiété → panique le lendemain »). → Un fichier `hypotheses.py` avec une **liste
   fermée d'hypothèses pré-enregistrées** (~15), écrites à l'avance, chacune testée sur les
   données personnelles avec sa taille d'effet, son `n` et son intervalle. **Une hypothèse
   pré-enregistrée qui survit vaut quelque chose ; une règle trouvée par fouille libre sur 30
   jours ne vaut rien** — et il faut le coder ainsi, pas seulement l'écrire dans un commentaire.
5. **Pas de résolution intra-journée.** Avec un check-in par jour, « café à 16 h → mauvaise
   nuit » est invisible. → `daily_checkins.moment` (`matin` | `soir`) **existe déjà** dans le
   schéma et n'est pas exploité : l'utiliser double la résolution sans migration.

#### P4b — La cohorte anonyme

L'exemple donné (« les personnes de 28 ans en Europe avec ce niveau d'anxiété qui font une
activité intensive ont plus souvent une crise le lendemain ») est une **analyse de sous-groupe
sur données de santé**. Techniquement simple, juridiquement lourd. Trois contraintes non
négociables :

- **Base légale.** Données de santé = catégorie particulière (art. 9 RGPD). Le consentement doit
  être explicite, spécifique, **distinct** de celui du service, et refusable sans perte de
  fonction.
- **Anonyme ≠ pseudonyme.** Une donnée pseudonymisée reste une donnée personnelle et le RGPD
  s'applique intégralement (art. 4(5)). Un tuple « 28 ans + Europe + niveau d'anxiété + type
  d'activité » est ré-identifiant dès que l'effectif est petit. Il faut le dire, pas le
  maquiller.
- **Taille de cellule minimale.** La référence en santé est de ne rien publier sous
  **11 individus** (politique de suppression de cellules du CMS ; seuil de risque de
  ré-identification d'environ 9 % correspondant à une cellule de 11 chez Santé Canada). Le
  k-anonymat reste le minimum de fait selon l'EMA. Concrètement : **aucun insight collectif
  affiché si la cellule contient moins de 11 utilisateurs distincts** — 11 *personnes*, pas 11
  observations.

**Par ordre de coût croissant :**

- **Étape A — maintenant.** Ne rien afficher de collectif. Construire la table de faits sous
  consentement séparé et attendre les effectifs : `cohort_facts(user_key, age_band, region, …)`
  où `user_key` est dérivé par HMAC avec un sel serveur. Bandes d'âge de 5 ou 10 ans, région au
  niveau pays ou continent, **jamais la ville**. Assumer dans l'interface que c'est un
  pseudonyme, pas un anonymat.
- **Étape B — à quelques centaines d'utilisateurs.** Hypothèses pré-enregistrées testées sur la
  cohorte, suppression des petites cellules, rapport rédigé et relu. Pas d'affichage
  automatique.
- **Étape C — seulement si l'échelle le justifie.** Bruit différentiel sur les agrégats publiés,
  ou analytique fédérée. Le construire avant d'en avoir besoin serait du théâtre de la vie
  privée.

**À dire dans l'interface** : avec un seul utilisateur il n'y a pas de cohorte. Un insight
collectif affiché trop tôt serait faux — et un insight faux chez un anxieux coûte plus cher
qu'une absence d'insight.

---

### P5 — Score d'anxiété du jour et prédiction J+1

#### Le score du jour — faisable immédiatement, entièrement déterministe

Ne pas fabriquer un score composite opaque. **Deux chiffres distincts** :

- **l'anxiété déclarée** (0-10, déjà là) : c'est la vérité de référence, elle ne se calcule pas ;
- **un « indice de charge »** : un cumul de facteurs de risque du jour — sommeil sous ta
  moyenne, café au-dessus, alcool la veille, zéro activité, évitement élevé, exposition prévue.
  Chaque composante est pondérée par les **coefficients personnels calculés en P4**, jamais par
  des poids universels inventés.

Deux précautions d'affichage qui ne sont pas cosmétiques : séparer visuellement les deux chiffres
(sinon on surveille le score au lieu de vivre), et le **nommer « charge du jour », pas « ton
niveau d'anxiété »** — un score étiqueté « anxiété » qui monte est anxiogène par lui-même.

#### La prédiction J+1 — faisable, avec un plafond à assumer

Ce que dit la littérature sur la prévision individuelle de l'anxiété (capteurs de smartphone +
EMA horaire) : les modèles au niveau du **groupe** expliquent beaucoup (R² robuste ≈ 0,75), les
modèles **individuels** nettement moins — **R² robuste moyen ≈ 0,39**, avec une prédiction
non nulle chez 97 % des participants. Et l'essentiel de cette variance vient de
l'autocorrélation : « demain ressemblera à aujourd'hui ».

Conséquence de conception, et c'est le point central : **la référence à battre n'est pas le
hasard, c'est la persistance** (J+1 = J). Si le modèle ne bat pas la persistance en validation
honnête, il ne faut pas l'afficher. C'est mesurable, donc c'est décidable.

Méthode recommandée, dans l'ordre :

1. **Persistance** comme référence, affichée telle quelle au démarrage ;
2. **Régression linéaire personnelle** à quelques prédicteurs (anxiété du jour, sommeil, café,
   alcool, activité, évitement, + Whoop si branché), ajustée sur l'historique de la personne,
   validée en **avance glissante** — jamais sur des données déjà vues ;
3. Un modèle **groupé uniquement pour le démarrage à froid** (moins de ~30 jours), en le disant.

Trois règles d'affichage :

- **Un intervalle, pas un point** : « demain, probablement entre 4 et 7 ». Un chiffre unique
  sera lu comme une promesse.
- **Jamais de prédiction de crise de panique présentée comme un événement annoncé.** « Journée à
  surveiller », et pourquoi — jamais « tu vas faire une crise ». Une prédiction anxiogène est
  auto-réalisatrice.
- **Table `daily_forecasts`** (date visée, valeur prédite, intervalle, modèle, prédicteurs
  utilisés) écrite la veille et **jamais réécrite**. C'est ce qui permet d'afficher l'erreur
  réelle après coup — la seule façon de rester honnête sur la qualité du modèle, et cohérent
  avec « le passé ne se réécrit pas ».

**Statistiques** : `Charts.tsx` et le widget `stats` existent. À ajouter : la courbe
prédit/observé, l'erreur moyenne comparée à la persistance, et le tableau des coefficients
personnels avec leur `n` et leur intervalle.

---

### P6 — Whoop

#### Ce qui est disponible — vérifié dans la documentation officielle

API **v2**, OAuth 2.0 code d'autorisation. La v1 n'est plus supportée. Quotas : 100 req/min,
10 000 req/jour.

| Ressource | Contenu utile pour nous | Scope |
|---|---|---|
| `GET /v2/recovery` | **VFC (`hrv_rmssd_milli`)**, **FC de repos**, SpO₂, température cutanée, score de récupération | `read:recovery` |
| `GET /v2/activity/sleep` | stades, durées, efficacité, fréquence respiratoire | `read:sleep` |
| `GET /v2/cycle` | strain du jour, **FC moyenne**, **FC max**, kilojoules | `read:cycles` |
| `GET /v2/activity/workout` | sport, début/fin, **FC moyenne**, **FC max**, `zone_durations` (temps par zone en ms), distance, altitude | `read:workout` |
| `GET /v2/user/body_measurement` | taille, poids, **FC max** | `read:body_measurement` |
| Webhooks | `recovery.updated`, `sleep.updated`, `workout.updated` et leurs `.deleted` | — |

#### La contrainte décisive : aucune série temporelle de FC

**L'API Whoop n'expose pas la fréquence cardiaque instantanée.** Ni par seconde, ni par minute.
On dispose de la FC moyenne, de la FC max et du temps passé par zone — **agrégés** par séance ou
par cycle. Ce qui donne :

- ✅ **« Il a fait une activité, son cœur est monté au-dessus de 150, et il a noté une crise le
  lendemain » → faisable.** `max_heart_rate` et `zone_durations` d'une séance, croisés avec
  `panic_episodes` du lendemain. C'est exactement une hypothèse pré-enregistrée au sens de P4.
- ❌ **« Détecter nous-mêmes les crises d'angoisse et de panique » → pas faisable avec Whoop.**
  Repérer un pic autonome de 10 à 20 minutes exige la FC à la minute.

Trois voies, à ne pas confondre :

1. **Renoncer à la détection automatique et faire mieux ce qui est mesurable.** Après une séance
   à FC max élevée, l'application demande le lendemain « comment ça a été ? ». Coût faible,
   valeur réelle, aucune fausse alerte possible.
2. **Changer de source.** HealthKit et Google Health Connect donnent la FC à la minute pour un
   porteur de montre ; Polar et Garmin exposent des séries plus fines. Mais cela suppose une
   **application native**, pas une PWA. C'est une décision de produit, pas une ligne de code.
3. **Détecter au niveau du jour, pas de l'épisode.** Une VFC nocturne et une FC de repos
   nettement dégradées par rapport à la base personnelle constituent un **signal de risque
   journalier** exploitable directement dans la prédiction de P5. C'est faisable avec Whoop, et
   c'est probablement le meilleur usage de cette intégration.

#### Ce que dit la preuve sur la détection de panique par capteurs

Pour cadrer les attentes, dans les deux sens :

- **L'argument physiologique est solide.** Dans une étude d'enregistrement ambulatoire sur 24 h
  (43 patients avec trouble panique, 13 attaques naturelles capturées), une instabilité
  autonome et respiratoire significative est détectable **jusqu'à 47 minutes avant** le début —
  y compris pour des attaques rapportées comme soudaines et imprévisibles. Les dernières minutes
  sont dominées par une baisse du volume courant suivie d'une hausse brusque de la PCO₂.
- **Mais les modèles performants utilisent du matériel de recherche.** Les études qui annoncent
  de bons chiffres reposent sur de l'**ECG à 500 Hz** ou des capteurs de recherche (EDA, FC,
  température) — pas sur l'API agrégée d'un bracelet grand public. Et les revues récentes
  insistent sur l'absence de validation externe et sur le déséquilibre de classes : les crises
  sont rares, donc les fausses alertes sont nombreuses.
- **Conséquence éthique non contournable : une fausse alerte de panique est un déclencheur de
  panique.** Si une détection automatique voit le jour un jour, elle doit être formulée comme
  une observation — « ton corps est plus activé que d'habitude » — et jamais comme une
  prédiction d'attaque.

#### Comment on le fait

- `backend/app/integrations/whoop.py` : OAuth (autorisation + rafraîchissement), aucun secret
  côté front.
- Tables : `oauth_tokens` (jetons **chiffrés au repos**, `user_id`, `provider`, expiration),
  `wearable_daily` (une ligne par jour et par fournisseur : VFC, FC repos, FC max, sommeil,
  strain, minutes par zone), `wearable_workouts`.
- Endpoint de webhook + rattrapage périodique : **le scheduler existe déjà**, avec son verrou
  consultatif Postgres et son journal idempotent — la même mécanique se réutilise telle quelle.
- Les données Whoop entrent dans `signals.py` **comme n'importe quelle autre source** : mêmes
  seuils de `n`, mêmes corrections de multiplicité, même panneau « D'OÙ ÇA SORT ».
- Consentement séparé ; la révocation supprime les jetons **et** propose la suppression des
  données importées.

---

### P7 — Les widgets restent dans l'historique et gênent la navigation

#### Le diagnostic exact

Chaque widget ouvert crée une ligne dans `thread_items` (`kind='widget'`), et `Chat.tsx` rend
**tous** les items du fil sans pagination. Replier un widget (`WidgetHost`, classe `w-shut`) ne
masque que le corps : **l'en-tête reste**, avec son titre et son étiquette.

Ouvre trois fois « Mes chiffres », deux fois « Sources » et une fois « Compte » : six barres
inutiles s'installent définitivement entre toi et ton dernier message. Et comme le fil entier
est chargé à chaque ouverture, ça ne fait que grossir.

#### La distinction qui manque : consulter n'est pas saisir

| Nature | Widgets | Doit rester dans le fil ? |
|---|---|---|
| **Saisie** — produit une donnée de santé | `checkin`, `journal`, `echelles`/`gad7`, `exposition`, `interoceptif`, `meditation`, `breath` | **Oui.** C'est le registre, il est immuable. |
| **Consultation** — n'écrit rien | `stats`, `analysis`, `sources`, `memoire`, `rapport`, `account`, `logout` | **Non.** Ce sont des vues, elles n'ont pas d'histoire. |

Une vue de consultation dans un journal de santé n'a aucune valeur d'archive : personne n'a
besoin de savoir qu'on a regardé ses chiffres trois fois mardi.

#### Comment on le fait

1. **Colonne `ephemeral` sur `thread_items`.** Le serveur marque les widgets de consultation
   comme éphémères à la création. Deux effets : `GET /chat/thread` ne les renvoie pas s'ils ne
   sont plus les derniers, et ouvrir un widget de consultation **remplace** l'éphémère précédent
   du même type au lieu de s'empiler. Une seule ligne de migration
   (`ALTER TABLE … ADD COLUMN IF NOT EXISTS`) — `schema.sql` est déjà idempotent et rejoué à
   chaque démarrage.
   - *Variante sans migration* : filtrer sur `widget_type IN (…)` dans la requête. Faisable en
     une heure, moins propre. Je préfère la colonne : la liste des types de consultation va
     évoluer.
2. **Un widget replié disparaît, il ne laisse pas de barre.** Pour un widget **validé**, le bon
   rendu n'est pas un accordéon mais **une ligne de résumé dense** : « Check-in · anxiété 7 ·
   sommeil 5 h · 1 panique », dépliable au clic. `summarise()` dans `WidgetHost.tsx` produit
   déjà exactement ces cellules — il suffit de les rendre en ligne au lieu d'une grille dans un
   cadre.
3. **Pagination du fil.** Charger les 50 derniers items, remonter à la demande. Sans ça, le
   problème revient au bout de quelques mois quel que soit le rendu.
4. **Un séparateur de jour** (« Aujourd'hui », « Hier », « Mardi 12 »). Le fil n'en a aucun :
   c'est la deuxième cause de difficulté de navigation, après l'empilement.
5. **Une porte de sortie vers l'historique.** Puisque les vues de consultation quittent le fil,
   il faut un endroit pour retrouver une saisie ancienne — le widget `memoire` fait déjà
   exactement ça (recherche dans l'historique vectorisé, sans limite d'ancienneté). Le brancher
   sur les séparateurs de jour (« aller à cette date »).

**Effet de bord à assumer** : les widgets de consultation ne seront plus retrouvables dans le
fil. C'est le but.

---

## 3. Plan d'implémentation par lots

Ordre choisi sur un critère simple : d'abord ce qui **répare** ou **débloque** le reste, ensuite
ce qui a le plus de valeur par unité de travail, en dernier ce qui dépend d'effectifs ou de
tiers.

### Lot 0 — Réparer et dégager *(aucune dépendance)*

1. `ephemeral` sur `thread_items` ; les vues de consultation se remplacent au lieu de s'empiler
2. Résumé en une ligne pour les widgets validés (`WidgetHost.summarise` déjà prêt)
3. Pagination du fil (50 items) + séparateurs de jour
4. **Brancher `build_day()` sur `opening()`** — le moteur existe et n'est pas appelé
5. `backend/tests/smoke_v5.py` : ouvrir trois fois `stats` ne crée pas trois items ; l'ouverture
   du jour reprend bien `why_for_you` et `triggered_by`

### Lot 1 — Onboarding *(débloque l'adaptation, répare la règle 8)*

6. Widget `onboarding` multi-étapes, déposé si `profile.onboarding.done_at` manque
7. `profile.onboarding` structuré et versionné ; échelles dans `assessments`
8. Deux consentements séparés (santé / cohorte), le second refusable sans perte de fonction
9. Règles d'adaptation lisant le profil dans `program.py` (panique → intéroceptif avancé, social,
   inquiétude)
10. Porte de contre-indications remontée depuis l'intéroceptif (sert aussi à QUICK CHILL)

### Lot 2 — QUICK CHILL *(valeur immédiate, aucun prérequis)*

11. Bouton permanent dans `Composer` + écran plein hors du fil
12. Contenu 100 % local (bundle + service worker), zéro réseau au lancement
13. Séquence graduée : respiration → ancrage → froid (porte) → jeu, avec 0-10 avant/après
14. Table `panic_episodes` ; récapitulatif déposé dans le fil **après**
15. Compteur d'usage + règle « trop souvent et GAD-7 stable → rebasculer vers l'exposition »

### Lot 3 — Statistiques honnêtes *(prérequis de P5 et de la cohorte)*

16. `signals.py` : `n ≥ 14`, intervalles de confiance (Fisher), Benjamini-Hochberg, corrélation
    sur différences premières
17. `hypotheses.py` : liste fermée d'hypothèses pré-enregistrées avec taille d'effet et `n`
18. Exploitation de `daily_checkins.moment` (matin / soir), déjà dans le schéma

### Lot 4 — Score et prédiction

19. Indice de charge du jour, pondéré par les coefficients personnels du lot 3
20. `daily_forecasts` (jamais réécrite) + persistance comme référence + régression personnelle en
    validation glissante
21. Courbe prédit/observé et erreur réelle comparée à la persistance dans `stats`

### Lot 5 — Whoop

22. `integrations/whoop.py` : OAuth + rafraîchissement ; `oauth_tokens` chiffrés
23. `wearable_daily` / `wearable_workouts` ; webhooks + rattrapage dans le scheduler existant
24. Entrée des données Whoop dans `signals.py` et dans les prédicteurs du lot 4
25. Invite contextuelle après une séance à FC max élevée — **ce qui remplace** la détection
    automatique

### Lot 6 — Guidage étendu

26. Widget `jour` : le parcours du jour, items + états + boutons
27. Trois créneaux d'ouverture proactive, idempotents (même clé que `notification_log`)
28. Question du jour déterministe, écrite dans `journal_entries`

### Lot 7 — Cohorte *(dernier : dépend des effectifs, pas du code)*

29. `cohort_facts` alimentée sous consentement séparé, **rien d'affiché**
30. Seuil de 11 personnes par cellule, codé comme garde-fou et non comme réglage
31. Affichage collectif seulement quand les effectifs le permettent

---

## 4. Ce que je recommande de ne pas faire

- **Détection automatique des crises via Whoop** : impossible avec l'API (pas de série
  temporelle de FC), et une fausse alerte de panique est un déclencheur de panique.
- **Un score composite unique présenté comme « ton anxiété »** : on surveille le score au lieu
  de vivre, et un score qui monte est anxiogène par lui-même.
- **Fouille libre de patterns avec affichage de ce qu'elle trouve** : sur 30 jours et 6
  variables, on trouve toujours quelque chose, et l'application fabrique alors des croyances.
- **Embarquer l'ASI-3 sans licence** : usage réservé aux professionnels qualifiés.
- **Afficher un insight collectif avant d'avoir les effectifs** : sous 11 personnes par cellule,
  c'est à la fois faux et ré-identifiant.
- **Gamifier le guidage quotidien** : contredit une décision déjà prise et documentée dans
  `ROADMAP.md`, pour une bonne raison — célébrer du bruit entraîne à surveiller du bruit.

---

## 5. Sources

**Interventions aiguës (QUICK CHILL)**
- Balban et al., *Cell Reports Medicine* 2023 — [Brief structured respiration practices enhance mood and reduce physiological arousal](https://www.cell.com/cell-reports-medicine/fulltext/S2666-3791(22)00474-8) (ECR, n = 108 ; soupir cyclique > méditation sur l'humeur ; **pas d'effet VFC/FC**)
- Meuret et al. — [essai randomisé de CART pour le trouble panique](https://www.ptsd.va.gov/professional/articles/article-pdf/id1548512.pdf) et [essai multisite de bilan naturaliste (réponse 83 %, rémission 54 %)](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC5344940/)
- [Breathing Retraining for Individuals Who Fear Respiratory Sensations: Examination of Safety Behavior and Coping Aid Hypotheses](https://pubmed.ncbi.nlm.nih.gov/32759117/) (2020 — n'a **pas** retrouvé l'effet délétère attendu)
- Blakey & Abramowitz — [The effects of safety behaviors during exposure therapy for anxiety: critical analysis from an inhibitory learning perspective](https://pubmed.ncbi.nlm.nih.gov/27475477/)
- Craske et al. — [Maximizing exposure therapy: an inhibitory learning approach](https://pubmed.ncbi.nlm.nih.gov/24864005/)
- [Resting Heart Rate Affects Heart Response to Cold-Water Face Immersion Associated with Apnea](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10295257/) et [Assessment of arrhythmias and heart rate response in healthy adolescents performing face immersion](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12234767/)
- Iyadurai et al., *Molecular Psychiatry* 2018 — [Preventing intrusive memories after trauma via a brief intervention involving Tetris](https://www.nature.com/articles/mp201723) (souvenirs intrusifs, **pas** panique)

**Panique et capteurs**
- Meuret et al., *Biological Psychiatry* 2011 — [Do unexpected panic attacks occur spontaneously?](https://www.ncbi.nlm.nih.gov/pubmed/21783179) (instabilité autonome détectable jusqu'à 47 min avant)
- [Panic Attack Prediction via Machine Learning and Wearable Electrocardiography](https://pmc.ncbi.nlm.nih.gov/articles/PMC12526660/) (JMIR 2025 — ECG 500 Hz, pas de validation externe)
- [Utility of wearable technology in predicting panic attacks: a scoping review](https://doi.org/10.1177/20552076251390475) (2025)

**Prédiction et guidage**
- [Digital Biomarkers of Anxiety Disorder Symptom Changes: Personalized Deep Learning Models](https://pmc.ncbi.nlm.nih.gov/articles/PMC8858490/) (R² groupe ≈ 0,75 ; **R² individuel ≈ 0,39**)
- [A Social Support Just-in-Time Adaptive Intervention: feasibility study with a microrandomized trial design](https://mental.jmir.org/2025/1/e74103) (90 % d'usage en semaine 3, 59 % en semaine 6)

**Instruments**
- [Pfizer To Offer Free Public Access To Mental Health Assessment Tools](https://www.pfizer.com/news/press-release/press-release-detail/pfizer_to_offer_free_public_access_to_mental_health_assessment_tools_to_improve_diagnosis_and_patient_care) (PHQ et GAD-7 libres depuis 2010)
- [IDS Publishing — Anxiety Sensitivity Index](http://www.idspublishing.com/asi.htm) (ASI-3 **non** libre, usage réservé)

**Données et vie privée**
- [EDPB — guidelines on anonymisation and pseudonymisation](https://www.edpb.europa.eu/sites/default/files/files/file1/edpb_replyec_questionnaireresearch_final.pdf) et [synthèse des nouvelles lignes directrices sur les données de santé](https://aumans-avocats.com/en/pseudonymisation-and-anonymization-of-health-data-what-are-the-consequences-of-the-edpbs-new-guidelines/)
- [CMS Cell Size Suppression Policy](https://resdac.org/articles/cms-cell-size-suppression-policy) (rien sous 11) et [Anonymization Primer: Risk Thresholds for Patient Re-identification](https://rlsciences.com/risk-thresholds-for-patient-re-identification/)

**Whoop**
- [WHOOP Developer Platform](https://developer.whoop.com/docs/introduction/) · [Recovery](https://developer.whoop.com/docs/developing/user-data/recovery/) · [Workout](https://developer.whoop.com/docs/developing/user-data/workout/) · [Migration v1 → v2](https://developer.whoop.com/docs/developing/v1-v2-migration/) · [Support (quotas)](https://developer.whoop.com/docs/developing/support/)

---

# Addendum — après lecture du PDF et de `tracker.html`

Les deux fichiers ont pu être lus (déplacés hors de `~/Downloads`). Cette section remplace la
réserve du § 0.

## 6. Ce que sont réellement ces deux fichiers

**`Программа 3 месяца тревожность.pdf`** — un programme de 12 semaines en 6 phases de 2 semaines,
combinant exposition intéroceptive (pour la panique), restructuration cognitive (pour le TAG),
pratiques respiratoires, **travail corporel** (yoga / relaxation musculaire / étirements) et
journal. Il contient trois choses que le code n'a pas :

1. un **cadre quotidien fixe** identique sur les 12 semaines, en trois moments (matin 5-7 min /
   journée à la demande / soir 10-15 min), 20 à 30 min au total ;
2. un **log d'attaque** avec des champs précis, dont la finalité est explicite : « ce log,
   au bout de 3 mois, devient votre preuve principale : l'anxiété passe toujours, il n'y a pas eu
   de catastrophe » ;
3. quatre **principes de conduite du programme** (régularité > intensité ; ne pas fuir au pic ;
   les rechutes sont normales ; un paramètre à la fois).

**`tracker.html`** — 84 jours, 6 phases, cases à cocher + une note libre par jour, série et
pourcentage de complétion, stockage local via `window.storage`. Progression pilotée par la
**complétion** (`currentDayPointer` = premier jour non complété), pas par le calendrier.

**Le constat qui explique ta demande initiale : ni l'un ni l'autre ne mesure quoi que ce soit.**
Pas de GAD-7, pas de note d'anxiété 0-10, pas de sommeil, pas de café. Uniquement des cases
cochées et du texte libre. Un tracker qui ne mesure rien ne peut pas dire si le programme marche
— d'où le problème de suivi. Et sa seule boucle de retour est une série de jours consécutifs,
c'est-à-dire précisément le mécanisme que `ROADMAP.md` a écarté.

Au passage : la série de `tracker.html` est fausse. `computeStreak()` itère depuis le jour 0 et
s'arrête au premier jour incomplet — ce n'est pas une série en cours, c'est « nombre de jours
complétés depuis le début ». Un trou au jour 3 fige le compteur à 2 pour toujours.

**Conclusion de cadrage : le PDF apporte du contenu et un rythme. Il n'apporte aucune couche de
mesure — celle de l'application est très supérieure et doit être conservée.**

---

## 7. Correspondance PDF ↔ `program.py`

| Semaines | PDF | `MODULES` actuel | Écart |
|---|---|---|---|
| 1-2 | Psychoéducation + base respiratoire (4-4-6) | M1 « Se repérer » (s. 1) puis M2 « Comprendre le mécanisme » (s. 2) | ≈ aligné |
| 3-4 | Relaxation musculaire + première mise en question des pensées + box breathing + temps d'inquiétude | M3 « Observer sans fuir » (s. 3-4) : conscience émotionnelle, scan corporel, PMR, souffle | PMR aligné ; **le travail cognitif arrive 2 semaines plus tard dans l'app** ; le temps d'inquiétude arrive en s. 7 |
| **5-6** | **Exposition intéroceptive — « étape clé »** | M4 « Assouplir les pensées » | **Écart de 3 semaines sur la pièce centrale** |
| 7-8 | Intensification intéroceptive + **début de l'exposition situationnelle** (hiérarchie 8-10 items, 0-100) | M5 « Repérer ce qui entretient » (s. 7) + M6 « Apprivoiser les sensations » (s. 8) | L'intéroceptif de l'app tombe ici ; le situationnel n'arrive qu'en s. 9 |
| 9-10 | **Acceptation / ACT** + yoga nidra + passage de l'exposition en entretien (3-4×/sem.) | M7 « Affronter, pour de vrai » (s. 9-11) | **Toute la phase ACT est absente de l'app** |
| 11-12 | Consolidation, « lettre à moi anxieux », plan de prévention écrit en 4 points | M7 (s. 11) + M8 « Consolider » (s. 12+) | ≈ aligné |

---

## 8. Les cinq divergences qui demandent une décision

### 8.1 Timing de l'exposition intéroceptive — **adopter le PDF, sous condition**

Le PDF la place en semaine 5 et l'appelle « étape clé » ; l'application en semaine 8. Pour
quelqu'un dont le problème principal est la panique et la peur des sensations, trois semaines de
retard sur la pièce maîtresse est un vrai coût.

**Décision recommandée** : ne pas déplacer le module pour tout le monde, mais laisser la règle
d'onboarding déjà prévue au § P3 le faire — `difficultes` contient `panique` → avancer
`exposition-interoceptive` en module 3 (semaine 5). Le parcours canonique reste celui du Protocole
Unifié, qui a l'essai d'équivalence pour lui. C'est le profil qui décide, pas une réécriture de
la liste.

### 8.2 Le critère de fin d'exposition — **garder l'application, ne pas suivre le PDF**

Le PDF dit : « rester jusqu'à ce que l'anxiété baisse d'au moins 50 % depuis le pic, ne pas partir
avant ». C'est le modèle de l'**habituation**. L'application est construite sur le modèle de
l'**apprentissage inhibiteur** (Craske et al. 2014) et son `README` dit explicitement : « la
question n'est plus *est-ce que mon anxiété est descendue ?* mais *qu'est-ce que j'ai appris ?* ».

Les deux ne sont pas compatibles, et ce n'est pas un détail de formulation : un critère de sortie
fondé sur la baisse d'anxiété apprend à surveiller son anxiété pendant l'exposition, ce qui est
précisément ce qu'on veut désapprendre. En pratique les deux disent « ne pars pas au pic » — c'est
la **raison affichée** qui doit rester celle de l'application.

**Décision : conserver la logique de violation d'attente.** Reprendre du PDF la consigne concrète
(« ne fuis pas au moment du pic — partir au pic renforce la peur »), qui est juste et bien
formulée, sans le seuil de 50 %.

### 8.3 Les protocoles respiratoires — **garder ceux de l'app, ajouter les noms du PDF**

Le PDF fait progresser la respiration par phase : diaphragmatique 4-4-6 (s. 1-2), puis
**box breathing** 4-4-4-4 comme « bouton d'urgence » (s. 3-4). L'application a la respiration
lente ~6 cycles/min en socle et le soupir physiologique en aigu.

Le choix de l'application est mieux étayé : dans l'ECR de Balban et al. (2023), le soupir cyclique
— à expiration allongée — a fait **mieux que le box breathing** sur l'humeur et la fréquence
respiratoire. Le 4-4-6 avec une apnée de 4 s n'est pas non plus la respiration de résonance
à 6 c/min, qui est ce que la méta-analyse de Laborde soutient.

**Décision** : garder la respiration lente en socle et le soupir cyclique en aigu, mais **ajouter
le 4-4-6 et le box breathing comme variantes nommées** dans le widget `breath`. Raison :
l'adhérence tient à la familiarité, et un utilisateur qui a suivi le PDF cherchera ces noms. Le
niveau de preuve de chaque variante est affiché — le corpus est déjà outillé pour ça.

### 8.4 La phase ACT (semaines 9-10) — **à ajouter, en niveau B**

Absente de l'application. Le PDF en fait un basculement de cadre : « l'objectif n'est pas de
supprimer l'anxiété — c'est impossible, et essayer en crée — mais d'agir malgré elle », avec la
question du soir qui change : « qu'est-ce que j'ai fait aujourd'hui qui compte pour moi, même
quand c'était anxieux ? ».

**Fiabilité vérifiée** : l'ACT réduit significativement l'anxiété (SMD ≈ −0,64 dans une
méta-analyse d'ECR), et sa flexibilité psychologique fonctionne comme mécanisme annoncé. Mais
**l'ACT ne fait pas mieux que la TCC** — elle est comparable, et les essais inclus sont notés à
risque de biais élevé (mesures auto-rapportées).

**Décision** : ajouter un module « Agir malgré » en **niveau de preuve B**, positionné comme le
PDF (semaines 9-10), avec la mention explicite « comparable à la TCC, pas supérieure ». Deux
activités nouvelles : `action-engagee` (la question du soir, quotidienne) et une fiche de corpus
`21-acceptation-action-engagee.md`. C'est peu de code : le mécanisme d'activités et de fiches
existe.

### 8.5 Le travail corporel quotidien — **à ajouter, avec une nuance de preuve importante**

Le PDF a une pratique corporelle **chaque soir sur les 12 semaines**, qui progresse : étirements
10 min (s. 1-2) → PMR (s. 3-4) → yoga doux axé souffle (s. 5-6) → yoga nidra 15-20 min (s. 9-10).
L'application n'a que `relaxation-musculaire` et `scan-corporel` : ni étirements, ni yoga, ni yoga
nidra, et **aucune notion de pratique corporelle quotidienne qui progresse**.

**Fiabilité vérifiée, et elle n'est pas uniforme :**

- **Yoga en général** : effets petits à court terme contre absence de traitement, mais — point
  décisif — **aucun effet retrouvé chez les patients dont le trouble anxieux est diagnostiqué
  selon les critères du DSM** ; les effets n'apparaissent que chez les personnes à anxiété élevée
  sans diagnostic formel. → **niveau C** pour un trouble caractérisé.
- **Yoga Kundalini dans le TAG** : supérieur à une éducation au stress, mais **inférieur à la
  TCC**. → utile en complément, jamais en remplacement.
- **Yoga nidra** : c'est le mieux soutenu du lot — méta-analyse de 73 essais, 5 201 participants,
  effets importants sur le stress, l'anxiété et la dépression **y compris contre comparateurs
  actifs**. → **niveau B**, et c'est aussi la pratique la plus accessible quand la méditation
  assise ou le travail respiratoire sont difficiles.

**Décision** : ajouter `etirements-soir` (niveau C, assumé : c'est de l'hygiène et du sommeil,
pas un traitement de l'anxiété), `yoga-doux` (niveau C, avec la nuance DSM affichée) et
`yoga-nidra` (niveau B). Et ajouter la notion de **pratique corporelle du soir qui suit la
phase** — c'est un quatrième `slot` dans `build_day()`, à côté de socle / module / adaptatif.

---

## 9. Ce que le PDF apporte et qu'il faut prendre tel quel

### 9.1 Le log d'attaque — il valide `panic_episodes` et le complète

Les champs du PDF, dont **quatre que je n'avais pas prévus** :

| Champ PDF | Colonne | Déjà prévu ? |
|---|---|---|
| Date / heure | `started_at`, `ended_at` | oui |
| **Ce qui a précédé** | `what_preceded` | **non** |
| Symptômes corporels | `body_symptoms text[]` | oui |
| **La pensée sur le moment** (« je meurs / j'étouffe / je deviens fou ») | `thought_in_moment` | **non** |
| Ce que j'ai fait | `tools_used jsonb` (outils + ordre) | oui |
| **Au bout de combien de temps c'est passé** | `time_to_relief_min` | **non** |
| **Ce qui s'est réellement passé** | `what_actually_happened` | **non** |
| Anxiété avant / pic / après | `anxiety_before/peak/after` | oui |

Et surtout : **la finalité change la conception**. Le PDF dit que ce log est la preuve
rétrospective. Il faut donc pouvoir le **rendre en agrégat**, et c'est une fonction à trois
lignes de SQL : *« 14 épisodes enregistrés. Tous sont passés. Durée médiane avant soulagement :
11 min. Catastrophe annoncée : 14 fois. Catastrophe survenue : 0 fois. »*

C'est la fonctionnalité la moins chère et la plus forte de tout ce document. Elle transforme le
suivi en argument. À mettre dans le widget `rapport` et dans le récapitulatif de QUICK CHILL.

### 9.2 « Заметил → Назвал → Подышал » — remarquer, nommer, puis respirer

Le PDF met **le nommage avant la respiration**. Ma séquence du § P2 commençait par la
respiration : le PDF a raison et je corrige.

**Fiabilité** : le nommage de l'affect (*affect labeling*) réduit la réponse de l'amygdale et les
indicateurs physiologiques de réactivité émotionnelle, dont la conductance cutanée, via une
inhibition par le cortex préfrontal ventrolatéral (démontrée par modélisation causale
dynamique). C'est une régulation **implicite** — elle ne demande pas d'effort de contrôle.

Et cet ordre résout le problème que j'ai soulevé au § P2 : nommer d'abord (« c'est mon système
sympathique, pas mon cœur »), c'est **réinterpréter** la sensation ; respirer d'abord, c'est la
**supprimer** — donc se rapprocher du comportement de sécurité. La séquence de QUICK CHILL
devient :

1. **Remarquer** — « où tu le sens ? » (carte du corps, 1 tap)
2. **Nommer** — « c'est quoi, la pensée ? » avec 4 étiquettes pré-écrites reprises du PDF (« je
   meurs », « j'étouffe », « je deviens fou », « je perds le contrôle ») + libre
3. **Respirer** — expiration allongée, 3 min
4. Si ça ne descend pas : ancrage → froid (porte de contre-indications) → jeu
5. 0-10 après, durée, « ce qui s'est réellement passé »

### 9.3 La ligne du matin — le gabarit exact, à reprendre mot pour mot

> « Aujourd'hui j'ai peur de ______. Aujourd'hui je vais faire ______ malgré ça. »

Deux trous, une phrase. C'est la « question du jour » du § P1.d, et le gabarit est meilleur que ce
que j'aurais écrit : il capture l'appréhension **et** l'action engagée dans le même geste, et le
second trou est déjà de l'ACT. Déterministe, aucun appel LLM. La réponse s'écrit en
`journal_entries` et alimente `main_trigger` et la prédiction du § P5.

### 9.4 Le journal de pensées en 3 colonnes — un champ manque en base

Le PDF : *Pensée → à combien j'y crois (0-100 %) → pensée plus réaliste*, avec trois questions de
mise en question (« le pire réaliste ? », « est-ce arrivé une seule fois en 17 ans ? », « qu'est-ce
que je dirais à un ami ? »).

`journal_entries` a `automatic_thought`, `thinking_trap`, `evidence_for`, `evidence_against`,
`coping_plan`, `alternative_thought`, `intensity_before/after` — mais **aucun pourcentage de
croyance**. `prediction_probability` existe, mais il porte sur les expositions, pas sur les
pensées.

**À ajouter** : `belief_before_0_100` et `belief_after_0_100` sur `journal_entries`. Sans eux, on
ne peut pas mesurer le mouvement propre de la restructuration cognitive — et donc pas savoir si
elle marche chez cette personne. C'est deux colonnes.

### 9.5 La similarité aux symptômes réels — un champ manque aussi

Le PDF, sur chaque exercice intéroceptif : « notez la peur 0-10, **et à quel point les symptômes
ont coïncidé avec ceux de l'attaque, 0-10** ».

Vérifié dans le code : `routers/chat.py` enregistre `prediction`, `prediction_probability`,
`anxiety_max` (→ `intensity_before`) et `anxiety_after`. **La similarité n'est pas capturée.**

C'est pourtant elle qui décide **quel exercice compte pour cette personne** : provoquer un vertige
chez quelqu'un dont les crises sont digestives n'apprend rien. C'est la logique de l'évaluation
intéroceptive de Schmidt & Trakowski — déjà cité dans `data/interoceptive.py`, dont le
commentaire note même que la paille n'a pas montré d'effet sur les peurs gastro-intestinales.

**À ajouter** : `similarity_0_10` sur la soumission intéroceptive, et une règle adaptative qui
classe les 8 exercices par similarité décroissante pour proposer d'abord ceux qui ressemblent aux
crises réelles. Faible coût, effet direct sur la pertinence du module 6.

### 9.6 La ligne de soutien du soir — à prendre, mais ce n'est pas de la gamification

> « une ligne de gratitude / soutien de soi — pas sur les accomplissements, mais sur le
> "j'ai tenu ça" »

La précision entre parenthèses est ce qui la sauve : ce n'est pas un badge ni une félicitation
pour une variation sous le seuil clinique — c'est de l'auto-compassion sur l'endurance. Aucune
contradiction avec l'exclusion de la gamification. À prendre.

### 9.7 Les quatre principes — deux sont déjà codés, deux sont à coder

| Principe | État |
|---|---|
| « Régularité > intensité » | déjà : règle 7 de `adaptive_items` allège si adhérence < 0,4 |
| « Ne pas fuir au pic » | déjà : porte de prédiction du widget intéroceptif |
| « Les rechutes sont normales, 17 ans ne se réécrivent pas linéairement » | **à coder** : quand la tendance d'anxiété monte de ≥ 0,7, l'app propose aujourd'hui `temps-inquietude` — il faut d'abord **dire** que la remontée est attendue |
| **« Un paramètre à la fois »** — si une semaine d'exposition aggrave nettement, réduire l'intensité, ne pas arrêter | **à coder** : nouvelle règle adaptative. Détectable avec ce qui existe (semaine de module 6-7 + `tendance_anxiete.delta ≥ 0,7` → proposer l'exercice le plus court plutôt que d'arrêter) |

---

## 10. Calendrier ou complétion : trois modèles, une recommandation

- **PDF** : une séquence de semaines, sans dates.
- **`tracker.html`** : piloté par la complétion — on n'est jamais en retard, mais on peut stagner
  indéfiniment au jour 3.
- **`program.py`** : piloté par le calendrier (`week_started_on`, `elapsed // 7`), avec un
  commentaire qui assume le choix : bloquer la progression sur l'assiduité « transformerait un
  outil de soin en système de punition ».

Le raisonnement du code est le bon. Mais sa conséquence est réelle : après trois semaines
d'arrêt, on revient en semaine 6 sans avoir rien fait, et le programme parle d'exposition
situationnelle à quelqu'un qui n'a pas fait la base.

**Recommandation — afficher les deux, ne pas choisir** : « semaine 6 du calendrier · 14 jours de
pratique effectués ». Et une seule règle de sécurité, pas un blocage : ne pas proposer un item de
module 6 ou 7 si le socle du module 3 n'a jamais été fait une seule fois. Ça se calcule avec
`activity_logs`, aucune migration.

---

## 11. Ce que l'addendum change au plan par lots

Rien à réordonner — les deux fichiers **confirment** l'ordre. Ils ajoutent des éléments dans les
lots existants et un lot de contenu.

**Lot 0** — inchangé, et renforcé : le cadre quotidien en 3 moments du PDF valide P1.c.

**Lot 1 (onboarding)** — ajouter : la question « depuis combien de temps ? » (17 ans dans le cas
présent : ça change le cadrage des attentes) et « un médecin a-t-il écarté une cause
organique ? », que le PDF pose comme préalable (« le médecin a déjà confirmé »).

**Lot 2 (QUICK CHILL)** — trois corrections :
- séquence réordonnée en **remarquer → nommer → respirer** (§ 9.2) ;
- `panic_episodes` avec les quatre champs du log d'attaque (§ 9.1) ;
- **la vue agrégée du log** — « tous sont passés, 0 catastrophe sur 14 » (§ 9.1). À ne pas
  reporter : c'est le meilleur rapport valeur / effort du document.

**Nouveau lot 2 bis — contenu du programme** (indépendant, parallélisable) :
1. `belief_before_0_100` / `belief_after_0_100` sur `journal_entries` (§ 9.4)
2. `similarity_0_10` sur l'intéroceptif + tri des exercices par similarité (§ 9.5)
3. Gabarit du matin « j'ai peur de ___ / je vais faire ___ malgré ça » (§ 9.3)
4. Ligne de soutien du soir (§ 9.6)
5. Nouvelles activités : `etirements-soir` (C), `yoga-doux` (C, nuance DSM), `yoga-nidra` (B),
   `action-engagee` (B) ; variantes `4-4-6` et box breathing dans `breath` (§ 8.3, § 8.5)
6. Quatrième `slot` « corps » dans `build_day()`, qui suit la phase (§ 8.5)
7. Module « Agir malgré » en semaines 9-10 + fiche `21-acceptation-action-engagee.md` (§ 8.4)
8. Règle adaptative « un paramètre à la fois » + message « les rechutes sont attendues » (§ 9.7)
9. Double affichage calendrier / jours pratiqués + garde-fou de prérequis (§ 10)

**Lot 3 (statistiques)** — les nouveaux champs deviennent des prédicteurs : `similarity_0_10`,
le delta de croyance, la durée jusqu'au soulagement. Et `panic_episodes` fournit enfin la
**vérité de référence** qui manquait pour le § P5 et le § P6.

---

## 12. Sources de l'addendum

- ACT : [Process of change and efficacy of ACT for anxiety and depression: meta-analysis of RCTs](https://pubmed.ncbi.nlm.nih.gov/39303882/) (SMD ≈ −0,64 sur l'anxiété ; **pas supérieure à la TCC** ; risque de biais élevé) · [Efficacy of internet-based ACT: systematic review and meta-analysis](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9789494/)
- Yoga : [Yoga for anxiety: systematic review and meta-analysis of RCTs](https://pubmed.ncbi.nlm.nih.gov/29697885/) (**aucun effet chez les patients diagnostiqués selon le DSM**) · Kundalini dans le TAG : supérieur à l'éducation au stress, **inférieur à la TCC**
- Yoga nidra : [Effects of Yoga Nidra on Stress, Anxiety, and Depression: systematic review and meta-analysis](https://nyaspubs.onlinelibrary.wiley.com/doi/full/10.1111/nyas.70149) (73 essais, 5 201 participants, effets importants y compris contre comparateurs actifs)
- Nommage de l'affect : [Torre & Lieberman, *Emotion Review* 2018 — Putting feelings into words: affect labeling as implicit emotion regulation](https://journals.sagepub.com/doi/10.1177/1754073917742706) · [Lieberman et al., *Psychological Science* 2007](https://journals.sagepub.com/doi/10.1111/j.1467-9280.2007.01916.x) · [The process of affect labeling, *Trends in Cognitive Sciences* 2025](https://www.cell.com/trends/cognitive-sciences/abstract/S1364-6613(25)00270-0)
- Respiration comparée : Balban et al., *Cell Reports Medicine* 2023 — [soupir cyclique > box breathing sur l'humeur](https://www.cell.com/cell-reports-medicine/fulltext/S2666-3791(22)00474-8)
- Exposition intéroceptive et similarité des sensations : Schmidt & Trakowski 2004, déjà cité dans `backend/app/data/interoceptive.py`
- Critère d'exposition : Craske et al., *Behav Res Ther* 2014 — [apprentissage inhibiteur](https://pubmed.ncbi.nlm.nih.gov/24864005/)

---

# Addendum 2 — page Compte séparée (demandé, à faire après)

## 13. Ce qui est demandé

Une **page Compte à part**, atteignable par un **bouton en haut à droite**, qui accueille les
réglages aujourd'hui dispersés dans le widget `account`.

## 14. La tension à trancher d'abord

Le principe fondateur de l'application est écrit en tête du `README` : « Tout se passe dans un fil
de conversation. Pas de navigation, pas d'onglets, pas de pages. » Une page Compte est donc une
**seconde exception** à cette règle — la première étant QUICK CHILL, dont l'exception est motivée
par la crise (un fil qui défile coûte de l'attention qu'on n'a pas à ce moment-là).

L'exception pour le Compte se motive autrement, et il faut le dire clairement plutôt que de faire
comme si la règle tenait encore :

- Les réglages ne sont pas un **événement**. Changer son heure de rappel n'a rien à faire dans un
  journal de santé — c'est précisément le raisonnement qui a rendu `account` éphémère au lot 0.
- Un éphémère est un demi-remède : le widget disparaît du fil, mais il faut toujours passer par
  le `+` et faire défiler pour l'atteindre.
- La suppression de compte et l'export ne se cherchent pas dans une grille de quatorze tuiles.

**Conclusion à assumer dans le `README`** : la règle devient « le *suivi* se passe entièrement
dans le fil ; la crise et l'administration en sortent ». C'est plus honnête que de garder une
règle déjà contredite deux fois.

## 15. Ce que la page contient

Regroupé par nature, pas par ordre d'apparition historique :

| Bloc | Contenu | Provenance |
|---|---|---|
| **Identité** | nom affiché, adresse, fuseau horaire | `users`, `PATCH /auth/me` |
| **Programme** | semaine et module en cours, statut actif/entretien, critère de sortie détaillé | `program_state`, `GET /chat/thread` |
| **Rappels** | heure du rappel quotidien, activation des notifications push, état de l'abonnement par appareil | `profile.rappel`, `push_subscriptions` |
| **Portes de sécurité** | contre-indications intéroceptives et du froid, avec leur date de validation | `profile.interoceptif_valide_le`, `profile.froid_valide_le` |
| **Onboarding** | réponses initiales, et « refaire l'onboarding » (nouvelle version, jamais un écrasement) | `profile.onboarding` — lot 1 du plan initial |
| **Consentements** | données de santé, et contribution anonyme à la cohorte — séparés, le second refusable sans perte de fonction | § P3, § P4b |
| **Intégrations** | Whoop : connexion, déconnexion, et suppression des données importées **et** de leurs traces en mémoire vectorisée | § P6, § 1 de l'addendum |
| **Mémoire** | volume conservé, réindexation | `GET /chat/memory` |
| **Tes données** | export JSON, suppression de compte | routes existantes |
| **Limites** | ce que l'application n'est pas, ressources d'urgence | statique |
| **Session** | déconnexion | remplace le widget `logout` |

## 16. Comment on le fait

**Le bouton.** Dans `.topbar` de `Chat.tsx`, à droite du `wordmark`. Une icône, pas un libellé :
la barre est étroite sur téléphone. Il porte un point quand quelque chose demande attention —
une porte de contre-indications non validée, un consentement jamais répondu, un abonnement push
révoqué par le navigateur.

**La navigation, sans routeur.** Le projet n'a aucune dépendance de routage et il n'en a pas
besoin pour un seul écran : un état `compte: boolean` dans `Chat.tsx`, comme `panicOpen`. Deux
précautions qui font la différence entre un panneau et une vraie page :

1. **`history.pushState`** à l'ouverture, et fermeture sur `popstate`. Sans ça, le bouton retour
   d'Android quitte l'application au lieu de refermer la page — c'est le défaut classique des
   panneaux plein écran dans une PWA.
2. **Le fil n'est pas démonté.** On superpose, on ne remplace pas : revenir doit retrouver la
   position de lecture exacte, et le `stickToBottom` du fil est déjà écrit pour ça.

**Ce qui disparaît.** Les widgets `account` et `logout` quittent la grille du lanceur et la table
`BODIES`. Mais **leur type reste accepté** par l'API et par `WidgetType` : des items `account`
existent déjà dans les fils, et le passé ne se réécrit pas. Ils se rendront comme un
récapitulatif figé renvoyant vers la page.

**Découpage des fichiers.**

```
frontend/src/screens/Compte.tsx        la page, un bloc par section
frontend/src/components/AccountLink.tsx  le bouton de la barre, avec son point d'attention
```

Le corps de `widgets/Account.tsx` (310 lignes) est réparti en sections de `Compte.tsx` — c'est un
déplacement, pas une réécriture : la logique de push, d'export et de suppression est déjà écrite
et testée.

**Ce qu'il ne faut pas faire au passage.** Ne pas profiter de la page pour ajouter un
interrupteur d'IA : la décision de la rendre toujours active est prise et documentée dans
`schema.sql`. Et ne pas déplacer `stats`, `analysis`, `rapport` ni `memoire` ici — ce sont des
lectures de *données*, elles restent dans le fil où le contexte de la conversation leur donne
leur sens.

## 17. Où ça s'insère

**Après le lot 2 (QUICK CHILL), avant le lot 3.** Deux raisons : la page est le bon endroit pour
poser les consentements séparés dont le lot 7 (cohorte) a besoin, et la porte du froid introduite
par QUICK CHILL doit être consultable et révocable quelque part.

Une dépendance à respecter : le widget `onboarding` du lot 1 écrit `profile.onboarding`, et la
page Compte le lit. Si l'onboarding n'est pas encore livré, la section affiche « pas encore
renseigné » plutôt qu'un bloc vide.
