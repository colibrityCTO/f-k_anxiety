# FUCK ANXIETY

Programme quotidien de suivi des troubles anxieux. Deux applications : une API **FastAPI** et
un front **React + Vite + TypeScript**. Accessible uniquement aux utilisateurs connectés (JWT).

**Le suivi se passe entièrement dans un fil de conversation.** Un seul écran, une saisie en
bas, un bouton **+** qui ouvre les widgets. Tout ce qui relève du suivi est soit un message,
soit un widget dans le fil.

Deux choses en sortent, et chacune pour une raison précise :

- **QUICK CHILL**, le mode crise, en plein écran : un fil qui défile coûte de l'attention
  qu'on n'a pas pendant une attaque de panique. Le récapitulatif est déposé dans le fil
  **après**, donc la trace reste là où elle doit être.
- **La page Compte**, en haut à droite : changer son heure de rappel n'est pas un événement
  et n'a rien à faire dans un journal de santé. C'est le même raisonnement qui fait que
  consulter ses chiffres ne laisse plus de trace dans le fil.

Deux façons d'entrer une donnée :

1. **Tu écris.** « nuit pourrie, anxiété 8, j'ai eu une crise dans le métro et j'ai annulé mon
   dîner » → l'extraction déterministe lit `anxiété 8`, `sommeil 5 h`, `1 panique`,
   `évitement 7`, et le check-in arrive **pré-rempli** dans le fil. Rien n'est enregistré avant
   que tu valides.
2. **Tu ouvres le widget toi-même** avec le +. Le lanceur a deux niveaux et trois
   entrées : **Noter**, **Pratiquer** et **Mes données**. « Noter »
   n'est pas un formulaire mais une demande — le serveur choisit le matin, le soir ou
   la mesure instantanée selon l'heure et selon ce qui manque déjà, ce qui rend
   impossible de résumer une journée qui n'est pas finie ou de saisir deux fois la
   même nuit.

Chaque widget et chaque conclusion porte son panneau **« D'OÙ ÇA SORT »** : le mécanisme, le
niveau de preuve, les références cliquables, et les données personnelles exactes qui ont
déclenché la proposition.

---

## Il y a toujours une étape suivante

`next_step.choose()` **ne renvoie jamais rien de vide**. Le classement est déterministe
et se lit d'un coup dans `_ranked()` : la saisie du créneau, le GAD-7 s'il est dû, ce
que tes données ont déclenché, le module de la semaine, le socle, la pratique du soir,
une question dont la réponse manque encore, puis une fiche du corpus jamais lue. Le
modèle ne choisit pas — il ne rédige même pas la justification, qui vient de
`program.py` avec tes chiffres.

Il est rappelé **après chaque validation**, pas seulement à l'ouverture. C'est ce qui
manquait : l'ouverture proactive est verrouillée à un dépôt par créneau, donc valider
son check-in à 8 h fermait la journée jusqu'à 17 h — alors que vingt-huit activités et
une trentaine de fiches attendaient. Un refus explicite fait exception : reporter une
saisie ne la remet pas en avant dans la foulée, elle reste accessible par « Noter ».

**Ce qui est attendu et ce qui est proposé sont deux choses.** Le bandeau **Mon
parcours**, sous le titre, porte la date et les cinq chiffres du jour — socle, activités
faites en plus, jours d'affilée, jours réellement pratiqués, assiduité sur 7 jours. Ces
chiffres ne défilent jamais : ils restent à l'écran pendant qu'on parcourt le texte
déplié en dessous. Le compteur du socle ne compte que le socle : le programme
propose cinq à huit items par jour, mais les afficher tous dans un compteur revenait à
annoncer « 1/7 » à quelqu'un qui avait fait exactement ce qu'on lui demandait. Et il
n'y a pas de série à préserver : un compteur qui se remet à zéro punit le jour où
c'était le plus dur.

Le parcours n'est pas un widget du fil, et c'est délibéré : un programme est l'état du
jour, pas un événement. Déposé dans un fil chronologique il défilait avec le reste, et
l'information la plus consultée devenait la plus difficile à retrouver.

**Chaque conseil porte les chiffres de la personne.** Toute proposition est suivie
d'une ligne « Chez toi » tirée de son historique : une hypothèse pré-enregistrée
retenue sur son domaine, une corrélation qui a survécu à la correction de
multiplicité, l'effet déjà mesuré de l'exercice proposé chez elle, le moment de la
journée où son anxiété monte, ou la tendance des sept derniers jours. Trois règles :
toujours chiffré, jamais un signal non retenu, et quand rien n'est calculable la ligne
dit combien de jours il manque au lieu d'inventer une généralité.

**Un formulaire long ne s'affiche jamais d'un bloc.** Les saisies en plusieurs temps —
le matin, le soir, l'exposition intéroceptive, le questionnaire initial, la séquence de
crise — montrent une étape à la fois, sous une barre segmentée qui dit combien il en
reste. Une page longue est en elle-même un motif d'abandon ; et savoir où ça s'arrête
est ce qui permet de commencer.

---

## Trois décisions structurantes

**Les chiffres ne dépendent jamais du modèle.** L'extraction du texte libre est faite par des
expressions régulières (`app/capture.py`), les statistiques par du Python
(`app/signals.py`) sur l'historique entier. Le modèle rédige et choisit le widget ; il ne
calcule rien et n'écrit rien en base. Les valeurs déduites d'une formulation qualitative sont
affichées comme telles (« déduit de ta phrase — vérifie »).

**Rien n'est oublié.** Chaque check-in, entrée de journal, échelle, activité, message et
analyse est rendu en texte, embeddé et conservé dans `user_chunks` — définitivement, sans
fenêtre glissante. À chaque tour, la recherche porte sur deux corpus : les fiches de preuve et
ta mémoire personnelle.

> Honnêteté sur « toujours tout » : la fenêtre d'un modèle est finie, on n'y colle pas six mois
> de données brutes. La garantie tenue est plus forte qu'un fenêtrage : les **chiffres** sont
> recalculés sur l'historique entier et injectés déjà calculés ; les **textes** sont tous
> retrouvables par recherche sémantique, sans limite d'ancienneté ; aucune donnée n'est
> écrasée. Conséquence à connaître : le texte du journal part chez OpenAI pour être embeddé,
> une fois par entrée.

**Le passé ne se réécrit pas.** Un widget validé est figé : son corps devient un récapitulatif
en lecture seule. « Corriger » ouvre un widget neuf. Si un second check-in est validé le même
jour, le premier est marqué « remplacé » — pas supprimé.

---

## Architecture

```
fuck_anxiety/
├── mockup/v1-chat.html          maquette autonome du fil (sans backend, pour itérer sur l'UX)
├── backend/
│   ├── app/
│   │   ├── main.py              routers, CORS, /health, /meta, ingestion au premier démarrage
│   │   ├── db.py                psycopg2 + ThreadedConnectionPool
│   │   ├── schema.sql           schéma idempotent : halfvec(3072) + HNSW, fil, mémoire
│   │   ├── security.py          bcrypt + JWT HS256
│   │   ├── capture.py           français libre → valeurs structurées (déterministe)
│   │   ├── chat.py              orchestrateur : réponse + widget à ouvrir + suggestions
│   │   ├── next_step.py         le classeur : ce qu'il y a à proposer, maintenant
│   │   ├── memory.py            mémoire personnelle vectorisée (rendu, écriture, recherche)
│   │   ├── signals.py           statistiques sur tout l'historique + drapeaux rouges
│   │   ├── search.py            recherche hybride du corpus (vectoriel + plein texte, RRF)
│   │   ├── embeddings.py        OpenAI text-embedding-3-large, 3072 dimensions
│   │   ├── llm_client.py        Anthropic principal + OpenAI fallback, singletons
│   │   ├── analysis.py          analyse traçable, avec repli local sans LLM
│   │   ├── program.py           programme 12 semaines, couche adaptative, régime d'entretien
│   │   ├── data/interoceptive.py 8 exercices intéroceptifs et leurs contre-indications
│   │   ├── ingest.py            knowledge/*.md → chunks → embeddings → pgvector
│   │   └── routers/chat.py      le fil : thread, message, widget, submit, memory
│   ├── knowledge/               21 fiches sourcées = corpus de preuve
│   └── tests/                   smoke_chat.py, smoke_v2.py, smoke_v3.py, smoke_e2e.py, seed_demo.py
├── frontend/
│   ├── Dockerfile              build en deux étapes, image finale sans outillage
│   ├── server.mjs              serveur statique + relais /api (zéro dépendance)
│   ├── src/
│   │   ├── screens/Auth.tsx     le seul écran hors du fil
│   │   ├── screens/Chat.tsx     le fil
│   │   ├── components/          Composer, Message, WidgetHost, Charts, Markdown, WhyBox…
│   │   ├── widgets/             les widgets du fil
│   │   └── lib/reminder.ts      rappel quotidien (Notification API)
│   └── public/                  manifest PWA, service worker, icônes
└── ROADMAP.md                   V1 / V2 / V3
```

### Les routes du fil

| Route | Rôle |
|---|---|
| `GET /chat/thread` | le fil, l'état du jour, et l'ouverture proactive (créée une fois par jour) |
| `POST /chat/message` | texte libre → réponse + widget pré-rempli éventuel |
| `POST /chat/message/stream` | idem, en streaming SSE token par token |
| `POST /chat/widget` | l'utilisateur ouvre un widget depuis la grille |
| `POST /chat/widget/{id}/submit` | enregistre la donnée, fige l'item, renvoie la relance |
| `POST /chat/widget/{id}/skip` | « pas maintenant » — c'est une donnée, pas un échec |
| `GET /chat/interoceptif` | exercices, contre-indications, répétitions déjà faites |
| `GET /chat/rapport` | tout ce qu'il faut pour le rapport imprimable |
| `GET /chat/memory` | ce qui est en mémoire, et ce qu'une requête y retrouve |
| `POST /chat/memory/reindex` | indexe l'historique déjà en base (idempotent) |

Les autres routers servent le contenu des widgets : `/assessments/instruments` (les trois
échelles), `/program/history` (les courbes), `/exposures` (l'échelle d'expositions),
`/knowledge` (les fiches), `/insights/engine` (l'état des moteurs).

---

## Démarrage local

### 1. PostgreSQL avec pgvector

```bash
docker run -d --name fa-db -p 5432:5432 -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=serenite pgvector/pgvector:pg17
```

pgvector ≥ 0.7 est requis pour `halfvec` et l'index HNSW en 3072 dimensions. Avec une version
antérieure, `schema.sql` bascule sur `vector(3072)` sans index.

### 2. Backend

```bash
cd backend && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
```

```bash
cp .env.example .env && python -c "import secrets; print(secrets.token_urlsafe(64))"
```

Colle la valeur dans `JWT_SECRET`, ajoute `ANTHROPIC_API_KEY` et `OPENAI_API_KEY`, puis :

```bash
cd backend && uvicorn app.main:app --reload --port 8000
```

Au premier démarrage, le schéma est appliqué et le corpus ingéré automatiquement.

### 3. Frontend

```bash
cd frontend && npm install && npm run dev
```

`http://localhost:5173`. En développement, Vite relaie `/api` vers `127.0.0.1:8000` : pas de
CORS à gérer.

### ⚠️ Le chemin du projet ne doit pas contenir `*`

Le dossier s'appelait initialement `f**k_anxiety` : esbuild interprète `**` comme un motif glob
en chargeant `vite.config.ts`, et le build échoue avec `Must use "outdir" when there are
multiple input files`. D'où `fuck_anxiety`. Le nom affiché dans l'application est indépendant du
nom du dossier.

### Installation sur le téléphone

L'application est une PWA : « Ajouter à l'écran d'accueil » depuis le navigateur l'installe en
plein écran, avec sa propre icône. Le service worker garde la coque en cache pour qu'elle s'ouvre
sans connexion — mais **jamais l'API** : servir un check-in ou une analyse périmés depuis le cache
serait pire qu'afficher une erreur.

Le rappel quotidien (widget Compte) ne part que si le check-in du jour manque encore. Sans
notification push serveur, il n'est fiable que si l'application est installée et reste en
arrière-plan : rien ne peut réveiller une application entièrement fermée. C'est une limite du
navigateur, dite dans l'interface plutôt que masquée.

---

## Variables d'environnement

| Variable | Rôle | Défaut |
|---|---|---|
| `DATABASE_URL` | PostgreSQL + pgvector | localhost |
| `JWT_SECRET` | **à changer** | — |
| `ANTHROPIC_API_KEY` / `ANTHROPIC_MODEL` | moteur principal | `claude-opus-5` |
| `OPENAI_API_KEY` / `OPENAI_MODEL` | fallback **et** embeddings | `gpt-4o` |
| `EMBEDDING_MODEL` / `EMBEDDING_DIM` | embeddings | `text-embedding-3-large` / 3072 |
| `CORS_ORIGINS` | origines du front | localhost:5173 |
| `ALLOW_REGISTRATION` | `false` verrouille l'instance après création du compte | true |
| `AUTO_INGEST` | ingestion du corpus au premier démarrage | true |
| `WHOOP_CLIENT_ID` / `WHOOP_CLIENT_SECRET` / `WHOOP_REDIRECT_URI` | intégration Whoop — sans les trois, elle est absente de l'interface | — |

Côté front : `API_ORIGIN` (lue **au démarrage** par `server.mjs`) désigne le backend en
production. `VITE_API_URL` reste `/api` — en développement c'est Vite qui relaie, en production
c'est `server.mjs`.

`ANTHROPIC_MODEL=claude-sonnet-5` réduit sensiblement le coût pour une qualité qui reste très
bonne sur cette tâche.

## Sans clé d'API

L'application reste utilisable : les réponses sont produites par des règles explicites
(`chat.py::_deterministic`), l'analyse par `analysis.py::local_analysis`, et la recherche
fonctionne en mode plein texte. L'interface l'affiche au lieu de le masquer. Le consentement à
l'envoi du journal vers l'API est **désactivé par défaut** et se change dans le widget Compte.

## Déploiement Railway

Trois services dans le même projet.

**1. Postgres avec pgvector** — prends le template dédié, pas le Postgres standard : sans
l'extension `vector`, le schéma ne s'applique pas.

**2. Backend** — *Root Directory* = `backend`, builder Nixpacks (détecté via
`requirements.txt`), healthcheck `/health`. Variables :

```
DATABASE_URL=${{Postgres.DATABASE_URL}}
JWT_SECRET=<64 caractères aléatoires>
ANTHROPIC_API_KEY=…
OPENAI_API_KEY=…
VAPID_PUBLIC_KEY=…        # python -m app.vapid
VAPID_PRIVATE_KEY=…
VAPID_SUBJECT=mailto:toi@exemple.fr
ALLOW_REGISTRATION=true   # à passer à false une fois ton compte créé
```

**3. Frontend** — *Root Directory* = `frontend`, builder **Dockerfile**. Une seule variable :

```
API_ORIGIN=https://<domaine-du-backend>.up.railway.app
```

`server.mjs` sert `dist/` et relaie `/api` vers `API_ORIGIN`. Conséquences : le navigateur ne
voit qu'une seule origine (donc aucun CORS, aucun préflight), et l'URL du backend est un réglage
d'**exécution** — la changer ne demande pas de reconstruire le front. `VITE_API_URL` reste `/api`
et n'a plus à être touchée.

### Pourquoi un Dockerfile et pas Nixpacks pour le front

Railway monte un cache de build sur `/app/node_modules/.cache`, et `npm ci` commence par
supprimer `node_modules` en entier. Un point de montage ne peut pas être supprimé, d'où l'échec :

```
npm error EBUSY: resource busy or locked, rmdir '/app/node_modules/.cache'
"npm ci && npm run build" did not complete successfully: exit code: 240
```

Le Dockerfile contourne la cause au lieu de la contourner à moitié : aucun cache n'est monté à cet
endroit, l'image finale ne contient ni Vite ni TypeScript, et le build est reproductible.
Alternative si tu tiens à Nixpacks : remplacer `npm ci` par `npm install --no-audit --no-fund`,
qui ne vide pas `node_modules`.

## Tests

```bash
cd backend && PYTHONPATH=. python tests/smoke_chat.py
```

Exerce la boucle complète contre une vraie base : ouverture proactive non dupliquée, texte
libre → widget pré-rempli, **aucune écriture avant validation**, validation qui enregistre et
fige, refus de revalidation (409), GAD-7 et sa DMCI, respiration, « pas maintenant », mémoire
vectorisée, drapeau rouge sans widget proposé.

`smoke_v5_next_step.py` couvre la garantie qui manquait : le classeur propose toujours
quelque chose, valider ou reporter ne ferme pas la journée, les suggestions dépendent de
l'état réel, « Noter » est résolu côté serveur, les widgets retirés ne sont plus ouvrables,
et l'assiduité a enfin un dénominateur — elle valait 100 % en permanence.

```bash
cd backend && PYTHONPATH=. python tests/smoke_v2.py    # exposition, méditation, échelles, streaming, rétroactif
cd backend && PYTHONPATH=. python tests/smoke_v3.py    # intéroceptif, entretien, bilan hebdo, rapport
cd backend && PYTHONPATH=. python tests/smoke_e2e.py   # l'API métier (24 endpoints)
cd backend && PYTHONPATH=. python tests/smoke_v5_next_step.py  # le classeur : jamais de cul-de-sac
cd frontend && npx tsc --noEmit && npm run build
```

## Base de preuves

21 fiches dans `backend/knowledge/`, chacune avec ses références en front-matter, consultables
dans le widget Sources. Principales : Protocole Unifié (Barlow, *World Psychiatry* 2020 ; essai
d'équivalence *JAMA Psychiatry* 2017) ; NICE CG113 ; respiration lente (Laborde,
*Neurosci Biobehav Rev* 2022) ; MBSR non inférieur à l'escitalopram (Hoge, *JAMA Psychiatry*
2023) ; apprentissage inhibiteur (Craske 2014, 2022) ; médiation sommeil → anxiété
(*J Affect Disord* 2023) ; DMCI du GAD-7 ≈ 4 points (Toussaint 2020) ; méta-analyse de 176 ECR
d'applications (Linardon, *World Psychiatry* 2024).

Le niveau de preuve est indiqué activité par activité, **y compris quand il est faible** : le
temps d'inquiétude est en niveau B, avec la mention explicite qu'une étude chez des patients
diagnostiqués n'a pas retrouvé d'effet.

## Ce que l'application n'est pas

Aucun diagnostic. Aucun conseil médicamenteux. Pas un dispositif médical certifié. Elle ne
remplace pas une psychothérapie encadrée : c'est une intervention de « faible intensité » au
sens des recommandations NICE. Un module de sécurité détecte les formulations évoquant des
idées suicidaires, suspend tout le reste et affiche les ressources d'urgence — **3114** en
France, gratuit, 24 h/24.
