# FUCK ANXIETY

Programme quotidien de suivi des troubles anxieux. Deux applications : une API **FastAPI** et
un front **React + Vite + TypeScript**. Accessible uniquement aux utilisateurs connectés (JWT).

**Tout se passe dans un fil de conversation.** Pas de navigation, pas d'onglets, pas de pages :
un seul écran, une saisie en bas, un bouton **+** qui ouvre les widgets. Tout ce que fait
l'application est soit un message, soit un widget dans le fil — y compris se déconnecter.

Deux façons d'entrer une donnée :

1. **Tu écris.** « nuit pourrie, anxiété 8, j'ai eu une crise dans le métro et j'ai annulé mon
   dîner » → l'extraction déterministe lit `anxiété 8`, `sommeil 5 h`, `1 panique`,
   `évitement 7`, et le check-in arrive **pré-rempli** dans le fil. Rien n'est enregistré avant
   que tu valides.
2. **Tu ouvres le widget toi-même** avec le +. Valable pour les quatorze widgets.

Chaque widget et chaque conclusion porte son panneau **« D'OÙ ÇA SORT »** : le mécanisme, le
niveau de preuve, les références cliquables, et les données personnelles exactes qui ont
déclenché la proposition.

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
│   │   ├── widgets/             les 14 widgets
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

```bash
cd backend && PYTHONPATH=. python tests/smoke_v2.py    # exposition, méditation, échelles, streaming, rétroactif
cd backend && PYTHONPATH=. python tests/smoke_v3.py    # intéroceptif, entretien, bilan hebdo, rapport
cd backend && PYTHONPATH=. python tests/smoke_e2e.py   # l'API métier (24 endpoints)
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
