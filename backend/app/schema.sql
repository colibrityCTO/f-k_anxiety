-- ============================================================================
--  Sérénité — schéma PostgreSQL (idempotent, appliqué à chaque démarrage)
--
--  Prérequis : extension pgvector >= 0.7 pour le type halfvec et l'index HNSW
--  sur 3072 dimensions. Image recommandée : pgvector/pgvector:pg17
--  (sur Railway : template « Postgres + pgvector »).
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS vector;     -- halfvec / hnsw
CREATE EXTENSION IF NOT EXISTS pg_trgm;    -- appoint pour la recherche lexicale

-- ---------------------------------------------------------------------------
--  Utilisateurs
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email               text NOT NULL,
    password_hash       text NOT NULL,
    display_name        text,
    timezone            text NOT NULL DEFAULT 'Europe/Paris',
    -- Profil issu de l'onboarding : cibles principales, contre-indications
    -- médicales déclarées, préférences. Sert à personnaliser le programme.
    profile             jsonb NOT NULL DEFAULT '{}'::jsonb,
    -- Envoi du contenu du journal vers l'API LLM. Décision produit : l'IA est
    -- active pour tout le monde et ce n'est plus un réglage. La colonne reste,
    -- le code la lit encore, mais elle vaut true partout — voir la bascule
    -- juste après la table.
    ai_consent          boolean NOT NULL DEFAULT true,
    created_at          timestamptz NOT NULL DEFAULT now(),
    last_login_at       timestamptz
);
CREATE UNIQUE INDEX IF NOT EXISTS users_email_lower_idx ON users (lower(email));

-- Bascule de l'IA vers « toujours active ». Deux instructions, deux rôles :
-- `SET DEFAULT` vise les bases déjà créées, où le `CREATE TABLE` ci-dessus
-- n'est plus rejoué ; l'`UPDATE` rattrape les comptes existants restés à
-- false, qui n'ont plus d'interrupteur pour le faire eux-mêmes. Les deux sont
-- sans effet au passage suivant — ce fichier est rejoué à chaque démarrage.
ALTER TABLE users ALTER COLUMN ai_consent SET DEFAULT true;
UPDATE users SET ai_consent = true WHERE ai_consent = false;

-- ---------------------------------------------------------------------------
--  État du programme (Protocole Unifié : 8 modules répartis sur 12 semaines)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS program_state (
    user_id         uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    started_on      date NOT NULL DEFAULT CURRENT_DATE,
    current_week    integer NOT NULL DEFAULT 1,
    current_module  integer NOT NULL DEFAULT 1,
    status          text NOT NULL DEFAULT 'actif',   -- actif | entretien | pause
    -- Verrou de progression : on ne monte pas de semaine sans adhérence minimale
    week_started_on date NOT NULL DEFAULT CURRENT_DATE,
    updated_at      timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
--  Check-in quotidien : le cœur du suivi longitudinal
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS daily_checkins (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    entry_date        date NOT NULL,
    moment            text NOT NULL DEFAULT 'soir',      -- matin | soir
    anxiety_0_10      integer CHECK (anxiety_0_10 BETWEEN 0 AND 10),
    mood_0_10         integer CHECK (mood_0_10 BETWEEN 0 AND 10),
    sleep_hours       numeric(4,2) CHECK (sleep_hours >= 0 AND sleep_hours <= 24),
    sleep_quality_0_10 integer CHECK (sleep_quality_0_10 BETWEEN 0 AND 10),
    bed_time          time,
    wake_time         time,
    caffeine_units    integer CHECK (caffeine_units >= 0),
    alcohol_units     integer CHECK (alcohol_units >= 0),
    exercise_min      integer CHECK (exercise_min >= 0),
    panic_attacks     integer NOT NULL DEFAULT 0 CHECK (panic_attacks >= 0),
    avoidance_0_10    integer CHECK (avoidance_0_10 BETWEEN 0 AND 10),
    -- Contextes d'anxiété cochés (travail, santé, social, argent, famille…)
    contexts          text[] NOT NULL DEFAULT '{}',
    main_trigger      text,
    note              text,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, entry_date, moment)
);
CREATE INDEX IF NOT EXISTS daily_checkins_user_date_idx
    ON daily_checkins (user_id, entry_date DESC);

-- Le check-in est découpé en deux moments, et `moment` existait déjà pour ça.
--
-- Un formulaire unique le soir mélangeait trois références temporelles : la nuit
-- dernière (sommeil), la journée entière (anxiété, café, évitement) et l'instant
-- présent. Les travaux sur l'agenda du sommeil sont nets là-dessus : le rappel se
-- dégrade dès que l'agenda n'est pas rempli au réveil, et l'estimation
-- rétrospective porte un biais non constant. Le sommeil appartient donc au matin.

-- Pic d'anxiété de la journée, distinct de la moyenne. Sous anxiété, la mémoire
-- retient les pires moments : demander une « moyenne » rétrospective récolte en
-- réalité un pic déguisé en moyenne. Autant demander les deux et savoir lequel est
-- lequel. Quand des mesures instantanées existent, les deux sont proposés calculés.
ALTER TABLE daily_checkins ADD COLUMN IF NOT EXISTS anxiety_peak_0_10 integer;
DO $$ BEGIN
    ALTER TABLE daily_checkins ADD CONSTRAINT daily_checkins_peak_range
        CHECK (anxiety_peak_0_10 BETWEEN 0 AND 10);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Provenance de la durée de sommeil. Sans elle, une corrélation sommeil → anxiété
-- mélangerait deux instruments de mesure (déclaratif et bracelet) et son
-- coefficient ne voudrait rien dire. `corrige` = le capteur proposait une valeur,
-- l'utilisateur l'a rectifiée — ce qui est une information en soi sur le capteur.
ALTER TABLE daily_checkins ADD COLUMN IF NOT EXISTS sleep_source text;
DO $$ BEGIN
    ALTER TABLE daily_checkins ADD CONSTRAINT daily_checkins_sleep_source
        CHECK (sleep_source IS NULL OR sleep_source IN ('declare', 'capteur', 'corrige'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ---------------------------------------------------------------------------
--  Mesures instantanées : « comment je me sens maintenant »
--
--  Table distincte, et c'est une nécessité, pas un choix d'organisation :
--  `daily_checkins` porte `UNIQUE (user_id, entry_date, moment)` et ne peut donc
--  pas accueillir huit mesures dans la même journée.
--
--  Ce que cette table débloque : la résolution intra-journée. Avec un seul point
--  par jour, « café à 16 h → mauvaise nuit » est invisible. Et le soir, le pic et
--  la moyenne réels se calculent au lieu d'être reconstruits de mémoire.
--
--  Jamais demandée par l'application — uniquement à l'initiative de
--  l'utilisateur. La consultation obsessionnelle de ses propres notes est un
--  symptôme chez certains : une invite de plus serait une invite de trop.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS momentary_ratings (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    rated_at     timestamptz NOT NULL DEFAULT now(),
    entry_date   date NOT NULL DEFAULT CURRENT_DATE,
    anxiety_0_10 integer NOT NULL CHECK (anxiety_0_10 BETWEEN 0 AND 10),
    -- Où / avec qui / en train de quoi. C'est ce qui rend la mesure exploitable :
    -- un 8 seul n'apprend rien, un 8 « transports, seul » se recoupe.
    contexts     text[] NOT NULL DEFAULT '{}',
    note         text,
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS momentary_ratings_user_idx
    ON momentary_ratings (user_id, entry_date DESC, rated_at DESC);

-- ---------------------------------------------------------------------------
--  Épisodes de panique — le « log d'attaque »
--
--  Les champs viennent du programme 12 semaines, et sa finalité est explicite :
--  au bout de trois mois, ce log devient la preuve rétrospective que l'anxiété
--  passe toujours et que la catastrophe annoncée n'est pas arrivée. C'est cette
--  finalité qui impose `what_actually_happened` et `time_to_relief_min` : sans
--  eux, il n'y a rien à rendre en agrégat, donc aucune preuve à montrer.
--
--  Une ligne ici est déclarée par l'utilisateur, jamais déduite d'un capteur.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS panic_episodes (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id               uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    entry_date            date NOT NULL DEFAULT CURRENT_DATE,
    started_at            timestamptz NOT NULL DEFAULT now(),
    ended_at              timestamptz,
    -- Le triptyque « remarquer → nommer → respirer » : ce qui a précédé, la
    -- pensée du moment, puis ce qui a été fait.
    what_preceded         text,
    body_symptoms         text[] NOT NULL DEFAULT '{}',
    thought_in_moment     text,
    -- Les outils utilisés **et leur ordre** : c'est l'ordre qui dira lequel aide.
    tools_used            jsonb NOT NULL DEFAULT '[]'::jsonb,
    anxiety_before        integer CHECK (anxiety_before BETWEEN 0 AND 10),
    anxiety_peak          integer CHECK (anxiety_peak BETWEEN 0 AND 10),
    anxiety_after         integer CHECK (anxiety_after BETWEEN 0 AND 10),
    time_to_relief_min    integer CHECK (time_to_relief_min >= 0),
    what_actually_happened text,
    -- « Est-ce que ce que tu redoutais est arrivé ? » Une réponse de l'utilisateur,
    -- pas une inférence de l'application. C'est ce qui permet d'écrire « 0 fois sur
    -- 14 » comme un fait constaté : l'application ne peut pas juger d'un texte libre
    -- si la catastrophe a eu lieu, et prétendre le faire serait une invention.
    feared_outcome_happened boolean,
    created_at            timestamptz NOT NULL DEFAULT now()
);
-- `ALTER` séparé et non colonne du `CREATE TABLE` : ce fichier est rejoué à chaque
-- démarrage, et `CREATE TABLE IF NOT EXISTS` ne touche pas une table qui existe
-- déjà. Toute colonne ajoutée après la première création doit passer par ici.
ALTER TABLE panic_episodes
    ADD COLUMN IF NOT EXISTS feared_outcome_happened boolean;

CREATE INDEX IF NOT EXISTS panic_episodes_user_idx
    ON panic_episodes (user_id, entry_date DESC);

-- ---------------------------------------------------------------------------
--  Prévisions du lendemain
--
--  Une ligne est écrite la veille et **jamais réécrite** : la contrainte d'unicité
--  plus un `ON CONFLICT DO NOTHING` en tiennent la garantie. C'est ce qui rend
--  l'honnêteté vérifiable — on peut comparer après coup ce qui avait été annoncé à
--  ce qui est arrivé, et afficher l'erreur réelle. Autoriser la mise à jour
--  permettrait de « corriger » une prévision ratée, ce qui reviendrait à ne jamais
--  se tromper.
--
--  `baseline` est ce que la persistance (« demain = aujourd'hui ») aurait annoncé.
--  Sans elle, on ne pourrait pas dire si le modèle apporte quoi que ce soit : la
--  référence à battre n'est pas le hasard, c'est la persistance — l'essentiel de la
--  variance d'un jour sur l'autre vient de l'autocorrélation.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS daily_forecasts (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    target_date    date NOT NULL,          -- le jour prédit
    made_on        date NOT NULL,          -- le jour où la prédiction a été faite
    model          text NOT NULL,          -- persistance | regression | groupe
    predicted      numeric(4,2) NOT NULL,
    interval_low   numeric(4,2),
    interval_high  numeric(4,2),
    baseline       numeric(4,2),
    -- Ce qui est entré dans le calcul, pour que le panneau « d'où ça sort » puisse
    -- montrer les valeurs exactes et pas seulement le résultat.
    predictors     jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, target_date, model)
);
CREATE INDEX IF NOT EXISTS daily_forecasts_user_idx
    ON daily_forecasts (user_id, target_date DESC);

-- ---------------------------------------------------------------------------
--  Table de faits pour les statistiques collectives
--
--  **Rien n'est affiché à partir de cette table aujourd'hui**, et c'est délibéré.
--  L'exemple qui motivait la demande — « les personnes de 28 ans en Europe avec ce
--  niveau d'anxiété qui font une activité intense ont plus souvent une crise le
--  lendemain » — est une analyse de sous-groupe sur données de santé. Elle demande
--  des effectifs, pas du code.
--
--  Trois contraintes tenues par la structure elle-même :
--
--  1. **Consentement séparé.** Une ligne n'est écrite que si
--     `profile.consentements.cohorte` vaut `true`. Le refuser ne retire aucune
--     fonction — c'est une exigence de l'article 9 du RGPD, pas une politesse.
--  2. **Pseudonyme, et dit comme tel.** `user_key` est un HMAC du compte avec un sel
--     serveur. Ça n'est **pas** de l'anonymat : une donnée pseudonymisée reste une
--     donnée personnelle au sens de l'article 4(5), et le prétendre serait faux.
--  3. **Granularité volontairement grossière.** Tranches d'âge de dix ans, pays ou
--     continent, jamais de ville. Un tuple « 28 ans + ville + niveau d'anxiété » est
--     ré-identifiant à lui seul.
--
--  Le garde-fou des onze personnes par cellule vit dans le code (`cohort.py`), pas
--  ici : une contrainte SQL ne peut pas compter des personnes distinctes au moment
--  d'un SELECT d'agrégation.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cohort_facts (
    id             bigserial PRIMARY KEY,
    -- HMAC du compte. Volontairement pas de clé étrangère vers `users` : la table doit
    -- pouvoir survivre à la suppression d'un compte sans le trahir, et une contrainte
    -- référentielle rétablirait le lien qu'on cherche à couper.
    user_key       text NOT NULL,
    entry_date     date NOT NULL,
    -- Attributs de strate, grossiers par construction.
    age_band       text,           -- '20-29', '30-39'…
    region         text,           -- pays ou continent, jamais plus fin
    difficulties   text[] NOT NULL DEFAULT '{}',
    -- Mesures du jour, telles que les signaux les voient.
    anxiety_0_10       numeric(4,2),
    anxiety_peak_0_10  integer,
    sleep_hours        numeric(4,2),
    caffeine_units     integer,
    alcohol_units      integer,
    exercise_min       integer,
    avoidance_0_10     integer,
    panic_attacks      integer,
    -- Bracelet, quand il y en a un.
    hrv_rmssd_milli    numeric(6,2),
    resting_heart_rate integer,
    session_max_hr     integer,
    created_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_key, entry_date)
);
CREATE INDEX IF NOT EXISTS cohort_facts_strata_idx
    ON cohort_facts (age_band, region, entry_date DESC);

-- ---------------------------------------------------------------------------
--  Intégrations : jetons OAuth, chiffrés au repos
--
--  Un jeton d'accès Whoop donne accès à des mois de données physiologiques
--  continues. Il est donc chiffré (`app/crypto.py`, clé dérivée de `JWT_SECRET`)
--  et non stocké en clair — une sauvegarde qui traîne ne doit pas suffire.
--
--  `provider_user_id` sert aux webhooks : le service de push identifie le membre
--  par son identifiant chez lui, pas par le nôtre.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS oauth_tokens (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider          text NOT NULL,                  -- whoop | …
    provider_user_id  text,
    access_token      text NOT NULL,                  -- chiffré
    refresh_token     text,                           -- chiffré
    scopes            text[] NOT NULL DEFAULT '{}',
    expires_at        timestamptz,
    last_sync_at      timestamptz,
    last_error        text,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, provider)
);
CREATE INDEX IF NOT EXISTS oauth_tokens_provider_user_idx
    ON oauth_tokens (provider, provider_user_id);

-- ---------------------------------------------------------------------------
--  Données de bracelet, agrégées par jour
--
--  Ce que l'API Whoop expose, et **rien de plus** : il n'y a aucune série
--  temporelle de fréquence cardiaque dans l'API v2, uniquement des agrégats par
--  cycle ou par séance. Détecter une crise de panique demanderait la FC à la
--  minute ; c'est hors de portée avec cette source, et la table le reflète.
--
--  Séparée de `daily_checkins` volontairement : une valeur de capteur n'écrase
--  jamais une saisie, et l'inverse non plus. Le check-in garde sa propre colonne
--  `sleep_hours` avec sa provenance (`sleep_source`).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS wearable_daily (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider            text NOT NULL,
    entry_date          date NOT NULL,
    -- Récupération : c'est le meilleur usage réel de cette intégration. Une VFC
    -- nocturne et une FC de repos nettement dégradées par rapport à la base
    -- personnelle constituent un signal de risque **journalier** exploitable.
    hrv_rmssd_milli     numeric(6,2),
    resting_heart_rate  integer,
    recovery_score      integer,
    spo2_percentage     numeric(5,2),
    skin_temp_celsius   numeric(5,2),
    -- Sommeil mesuré. `sleep_hours` ici est la mesure du capteur ; la valeur
    -- déclarée reste dans `daily_checkins`. Les deux coexistent, et c'est le but.
    sleep_hours         numeric(4,2),
    sleep_efficiency    numeric(5,2),
    sleep_performance   numeric(5,2),
    respiratory_rate    numeric(5,2),
    -- Charge du cycle : moyenne et maximum, seuls agrégats disponibles.
    strain              numeric(5,2),
    average_heart_rate  integer,
    max_heart_rate      integer,
    kilojoule           numeric(8,1),
    raw                 jsonb NOT NULL DEFAULT '{}'::jsonb,
    updated_at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, provider, entry_date)
);
CREATE INDEX IF NOT EXISTS wearable_daily_user_idx
    ON wearable_daily (user_id, entry_date DESC);

-- ---------------------------------------------------------------------------
--  Séances
--
--  C'est ce qui rend testable l'hypothèse « séance intense puis crise le
--  lendemain » : `max_heart_rate` et `zone_durations` suffisent, alors qu'une
--  détection d'épisode ne serait pas possible.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS wearable_workouts (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider            text NOT NULL,
    provider_id         text NOT NULL,
    entry_date          date NOT NULL,
    started_at          timestamptz,
    ended_at            timestamptz,
    sport               text,
    strain              numeric(5,2),
    average_heart_rate  integer,
    max_heart_rate      integer,
    kilojoule           numeric(8,1),
    distance_meter      numeric(10,1),
    -- Millisecondes par zone de fréquence cardiaque, telles que l'API les renvoie.
    zone_durations      jsonb NOT NULL DEFAULT '{}'::jsonb,
    raw                 jsonb NOT NULL DEFAULT '{}'::jsonb,
    updated_at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, provider, provider_id)
);
CREATE INDEX IF NOT EXISTS wearable_workouts_user_idx
    ON wearable_workouts (user_id, entry_date DESC);

-- ---------------------------------------------------------------------------
--  Journal : pensées (TCC), expositions, inquiétudes, entrées libres
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS journal_entries (
    id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    entry_date              date NOT NULL DEFAULT CURRENT_DATE,
    kind                    text NOT NULL DEFAULT 'libre',
        -- libre | pensee | exposition | inquietude
    -- Commun
    situation               text,
    emotions                text[] NOT NULL DEFAULT '{}',
    body_sensations         text[] NOT NULL DEFAULT '{}',
    intensity_before        integer CHECK (intensity_before BETWEEN 0 AND 10),
    intensity_after         integer CHECK (intensity_after BETWEEN 0 AND 10),
    -- Journal de pensées (module 4)
    automatic_thought       text,
    thinking_trap           text,          -- surestimation | catastrophisation | autre
    evidence_for            text,
    evidence_against        text,
    coping_plan             text,          -- « et si c'était vrai, comment je gère ? »
    alternative_thought     text,
    -- Exposition (modules 6-7) — logique de violation d'attente
    prediction              text,
    prediction_probability  integer CHECK (prediction_probability BETWEEN 0 AND 100),
    actual_outcome          text,
    learning                text,
    safety_behaviors_dropped text[] NOT NULL DEFAULT '{}',
    -- Inquiétude (module 5)
    worry_text              text,
    worry_actionable        boolean,
    next_action             text,
    free_text               text,
    created_at              timestamptz NOT NULL DEFAULT now(),
    updated_at              timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS journal_entries_user_date_idx
    ON journal_entries (user_id, entry_date DESC);

-- Journal de pensées en trois colonnes : pensée → à combien j'y crois → pensée
-- plus réaliste. Le pourcentage de croyance manquait, et c'est lui qui mesure le
-- mouvement propre de la restructuration cognitive : `intensity_before/after`
-- mesure l'émotion, pas l'adhésion à la pensée. Sans ces deux colonnes, on ne
-- peut pas savoir si la restructuration marche chez cette personne.
ALTER TABLE journal_entries ADD COLUMN IF NOT EXISTS belief_before_0_100 integer;
ALTER TABLE journal_entries ADD COLUMN IF NOT EXISTS belief_after_0_100 integer;
DO $$ BEGIN
    ALTER TABLE journal_entries ADD CONSTRAINT journal_entries_belief_range
        CHECK (
            (belief_before_0_100 IS NULL OR belief_before_0_100 BETWEEN 0 AND 100)
            AND (belief_after_0_100 IS NULL OR belief_after_0_100 BETWEEN 0 AND 100)
        );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Exposition intéroceptive : à quel point les sensations provoquées ressemblent à
-- celles des crises réelles. C'est ce qui décide **quel exercice compte** pour
-- cette personne — provoquer un vertige chez quelqu'un dont les crises sont
-- digestives n'apprend rien. Logique de l'évaluation intéroceptive de Schmidt &
-- Trakowski, déjà citée dans `app/data/interoceptive.py`.
ALTER TABLE journal_entries ADD COLUMN IF NOT EXISTS similarity_0_10 integer;
DO $$ BEGIN
    ALTER TABLE journal_entries ADD CONSTRAINT journal_entries_similarity_range
        CHECK (similarity_0_10 IS NULL OR similarity_0_10 BETWEEN 0 AND 10);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ---------------------------------------------------------------------------
--  Catalogue d'activités (semencé depuis app/data/activities.py)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS activities (
    slug              text PRIMARY KEY,
    title             text NOT NULL,
    category          text NOT NULL,   -- respiration | meditation | cognitif |
                                       -- exposition | comportemental | hygiene | mesure
    short_label       text,
    duration_min      integer NOT NULL DEFAULT 10,
    up_module         integer NOT NULL DEFAULT 1,
    evidence_level    text NOT NULL DEFAULT 'B',   -- A | B | C
    targets           text[] NOT NULL DEFAULT '{}',
    -- Les trois champs qui servent à répondre « d'où ça sort ? »
    mechanism         text NOT NULL,
    sources           jsonb NOT NULL DEFAULT '[]'::jsonb,
    kb_doc_id         text,            -- fiche du corpus RAG correspondante
    instructions      jsonb NOT NULL DEFAULT '[]'::jsonb,
    contraindications text,
    is_core           boolean NOT NULL DEFAULT false,  -- socle quotidien
    active            boolean NOT NULL DEFAULT true,
    updated_at        timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
--  Journal des activités : ce qui a été fait ET ce qui n'a pas été fait
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS activity_logs (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    activity_slug  text NOT NULL REFERENCES activities(slug) ON DELETE CASCADE,
    entry_date     date NOT NULL DEFAULT CURRENT_DATE,
    -- propose : calculé par build_day et pas encore fait. C'est lui qui donne un
    -- dénominateur à l'assiduité — sans lui, seuls des « fait » étaient écrits et
    -- la part des activités réalisées valait 1.0 en permanence.
    status         text NOT NULL,   -- propose | fait | partiel | pas_fait | reporte
    duration_min   integer,
    anxiety_before integer CHECK (anxiety_before BETWEEN 0 AND 10),
    anxiety_after  integer CHECK (anxiety_after BETWEEN 0 AND 10),
    skip_reason    text,            -- pourquoi ça n'a pas été fait : donnée précieuse
    notes          text,
    created_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, activity_slug, entry_date)
);
CREATE INDEX IF NOT EXISTS activity_logs_user_date_idx
    ON activity_logs (user_id, entry_date DESC);

-- ---------------------------------------------------------------------------
--  Échelles psychométriques
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS assessments (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    instrument   text NOT NULL,        -- gad7 | phq2 | asi3_court | avoidance
    taken_on     date NOT NULL DEFAULT CURRENT_DATE,
    items        integer[] NOT NULL,
    total        integer NOT NULL,
    severity     text,
    created_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, instrument, taken_on)
);
CREATE INDEX IF NOT EXISTS assessments_user_idx
    ON assessments (user_id, instrument, taken_on DESC);

-- ---------------------------------------------------------------------------
--  Échelle d'expositions (hiérarchie personnelle)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS exposure_items (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id              uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    label                text NOT NULL,
    kind                 text NOT NULL DEFAULT 'in_vivo',  -- in_vivo | interoceptif | imaginaire
    anticipated_anxiety   integer CHECK (anticipated_anxiety BETWEEN 0 AND 10),
    safety_behaviors     text[] NOT NULL DEFAULT '{}',
    attempts             integer NOT NULL DEFAULT 0,
    last_attempt_on      date,
    best_learning        text,
    mastered             boolean NOT NULL DEFAULT false,
    created_at           timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS exposure_items_user_idx ON exposure_items (user_id, mastered);

-- ---------------------------------------------------------------------------
--  Analyses produites par l'IA, avec leur traçabilité complète
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS insights (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    scope         text NOT NULL,        -- quotidien | hebdomadaire | libre
    period_start  date NOT NULL,
    period_end    date NOT NULL,
    headline      text,
    body          text NOT NULL,        -- markdown
    -- signals : observations déterministes calculées par signals.py (données brutes
    -- + dates + formule). citations : chunks du corpus RAG effectivement utilisés.
    signals       jsonb NOT NULL DEFAULT '{}'::jsonb,
    citations     jsonb NOT NULL DEFAULT '[]'::jsonb,
    recommendations jsonb NOT NULL DEFAULT '[]'::jsonb,
    engine        text NOT NULL,        -- anthropic:<modèle> | openai:<modèle> | local
    risk_flag     boolean NOT NULL DEFAULT false,
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS insights_user_idx ON insights (user_id, created_at DESC);

-- ---------------------------------------------------------------------------
--  Conversation « explique-moi » (streaming SSE)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS chat_messages (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role        text NOT NULL,          -- user | assistant
    content     text NOT NULL,
    citations   jsonb NOT NULL DEFAULT '[]'::jsonb,
    engine      text,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS chat_messages_user_idx ON chat_messages (user_id, created_at);

-- ---------------------------------------------------------------------------
--  Corpus RAG : documents et chunks vectorisés
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS kb_documents (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_id         text NOT NULL UNIQUE,      -- identifiant du front-matter
    title          text NOT NULL,
    category       text,
    evidence_level text,
    targets        text[] NOT NULL DEFAULT '{}',
    up_module      integer,
    duration_min   integer,
    sources        jsonb NOT NULL DEFAULT '[]'::jsonb,
    path           text,
    checksum       text,
    updated_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS kb_chunks (
    id           bigserial PRIMARY KEY,
    document_id  uuid NOT NULL REFERENCES kb_documents(id) ON DELETE CASCADE,
    chunk_index  integer NOT NULL,
    heading      text,
    content      text NOT NULL,
    metadata     jsonb NOT NULL DEFAULT '{}'::jsonb,
    tsv          tsvector GENERATED ALWAYS AS (to_tsvector('french', content)) STORED,
    created_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (document_id, chunk_index)
);

-- Colonne d'embedding : halfvec(3072) si pgvector >= 0.7 (permet l'index HNSW
-- au-delà de la limite de 2000 dimensions du type vector), sinon repli sur
-- vector(3072) sans index — acceptable, le corpus tient en quelques centaines
-- de chunks et le scan séquentiel reste rapide.
DO $$
DECLARE
    has_halfvec boolean;
BEGIN
    SELECT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'halfvec') INTO has_halfvec;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'kb_chunks' AND column_name = 'embedding'
    ) THEN
        IF has_halfvec THEN
            EXECUTE 'ALTER TABLE kb_chunks ADD COLUMN embedding halfvec(3072)';
        ELSE
            RAISE WARNING 'pgvector < 0.7 : halfvec indisponible, repli sur vector(3072) sans index HNSW';
            EXECUTE 'ALTER TABLE kb_chunks ADD COLUMN embedding vector(3072)';
        END IF;
    END IF;

    IF has_halfvec AND NOT EXISTS (
        SELECT 1 FROM pg_class WHERE relname = 'kb_chunks_embedding_hnsw_idx'
    ) THEN
        EXECUTE 'CREATE INDEX kb_chunks_embedding_hnsw_idx ON kb_chunks '
                'USING hnsw (embedding halfvec_cosine_ops) '
                'WITH (m = 16, ef_construction = 64)';
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS kb_chunks_tsv_idx ON kb_chunks USING gin (tsv);
CREATE INDEX IF NOT EXISTS kb_chunks_metadata_idx ON kb_chunks USING gin (metadata jsonb_path_ops);

-- ---------------------------------------------------------------------------
--  Le fil de conversation : l'unique écran de l'application.
--
--  Un seul fil continu par utilisateur. Un item est soit un message, soit un
--  widget. Un widget validé est figé : `status` passe à 'valide' et `values`
--  conserve ce qui a été enregistré. On ne réécrit jamais le passé —
--  « Corriger » crée un nouvel item.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS thread_items (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    seq           bigserial,
    role          text NOT NULL,                      -- user | assistant
    kind          text NOT NULL DEFAULT 'text',       -- text | widget
    content       text,
    widget_type   text,                               -- checkin | breath | journal | gad7 |
                                                      -- stats | analysis | sources | account | logout
    payload       jsonb NOT NULL DEFAULT '{}'::jsonb, -- pré-remplissage proposé
    -- `values` est un mot réservé en SQL : la colonne s'appelle saved_values.
    saved_values  jsonb NOT NULL DEFAULT '{}'::jsonb, -- ce qui a été validé
    status        text,                               -- NULL | ouvert | valide | reporte
    -- Réponses pré-choisies proposées par l'IA, attachées à son message.
    suggestions   jsonb NOT NULL DEFAULT '[]'::jsonb,
    citations     jsonb NOT NULL DEFAULT '[]'::jsonb,
    engine        text,
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS thread_items_user_idx ON thread_items (user_id, seq);

-- Widgets de consultation : ils n'écrivent rien, donc ils n'ont pas d'histoire.
--
-- `stats`, `sources`, `compte`… sont des *vues*. Les garder dans le fil empilait
-- des en-têtes inutiles entre l'utilisateur et son dernier message, définitivement.
-- Un item éphémère est retiré quand le même type est rouvert, et cesse de l'être
-- s'il finit par produire quelque chose (une analyse validée est un résultat).
ALTER TABLE thread_items ADD COLUMN IF NOT EXISTS ephemeral boolean NOT NULL DEFAULT false;

-- Index partiel : le fil affiché ne lit que les items durables et le dernier
-- éphémère. Le partiel garde l'index petit alors que la table, elle, ne l'est pas.
CREATE INDEX IF NOT EXISTS thread_items_durable_idx
    ON thread_items (user_id, seq) WHERE NOT ephemeral;

-- Rattrapage de l'historique déjà en base. Sans lui, la colonne ne corrigerait que
-- les items à venir et les fils existants resteraient encombrés — or c'est
-- précisément eux qui posent le problème. Les conditions sont ce qui rend
-- l'opération sûre : uniquement des widgets de consultation, jamais validés
-- (`status = 'ouvert'`) et sans aucune valeur enregistrée. Le bilan hebdomadaire
-- est exclu : sa présence dans le fil est le verrou qui l'empêche d'être redéposé.
UPDATE thread_items SET ephemeral = true
WHERE kind = 'widget'
  AND NOT ephemeral
  AND status = 'ouvert'
  AND saved_values = '{}'::jsonb
  AND widget_type IN ('stats', 'analysis', 'sources', 'memoire', 'rapport', 'account', 'logout')
  AND coalesce(payload->'prefill'->>'scope', '') <> 'hebdomadaire';

-- ---------------------------------------------------------------------------
--  Mémoire personnelle vectorisée.
--
--  Tout ce que produit l'utilisateur est rendu en texte, embeddé et conservé
--  ici définitivement — sans troncature ni fenêtre glissante. C'est ce qui
--  permet de retrouver n'importe quel élément de l'historique, quelle que soit
--  son ancienneté. Table distincte du corpus de fiches, toujours filtrée par
--  user_id : aucune requête ne peut traverser les comptes.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_chunks (
    id           bigserial PRIMARY KEY,
    user_id      uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source_kind  text NOT NULL,    -- checkin | journal | assessment | activity | message | insight
    source_id    text,             -- identifiant d'origine, garantit l'idempotence
    entry_date   date,
    content      text NOT NULL,
    metadata     jsonb NOT NULL DEFAULT '{}'::jsonb,
    tsv          tsvector GENERATED ALWAYS AS (to_tsvector('french', content)) STORED,
    created_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, source_kind, source_id)
);

DO $$
DECLARE
    has_halfvec boolean;
BEGIN
    SELECT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'halfvec') INTO has_halfvec;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'user_chunks' AND column_name = 'embedding'
    ) THEN
        IF has_halfvec THEN
            EXECUTE 'ALTER TABLE user_chunks ADD COLUMN embedding halfvec(3072)';
        ELSE
            EXECUTE 'ALTER TABLE user_chunks ADD COLUMN embedding vector(3072)';
        END IF;
    END IF;

    IF has_halfvec AND NOT EXISTS (
        SELECT 1 FROM pg_class WHERE relname = 'user_chunks_embedding_hnsw_idx'
    ) THEN
        EXECUTE 'CREATE INDEX user_chunks_embedding_hnsw_idx ON user_chunks '
                'USING hnsw (embedding halfvec_cosine_ops) '
                'WITH (m = 16, ef_construction = 64)';
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS user_chunks_user_date_idx ON user_chunks (user_id, entry_date DESC);
CREATE INDEX IF NOT EXISTS user_chunks_tsv_idx ON user_chunks USING gin (tsv);

-- ---------------------------------------------------------------------------
--  Notifications push (Web Push / VAPID)
--
--  Un même compte peut être abonné depuis plusieurs appareils : la clé est
--  l'endpoint fourni par le navigateur. Un abonnement révoqué (404 ou 410 renvoyé
--  par le service de push) est désactivé et non supprimé, pour garder la trace de
--  la raison.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS push_subscriptions (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    endpoint     text NOT NULL UNIQUE,
    p256dh       text NOT NULL,
    auth         text NOT NULL,
    user_agent   text,
    active       boolean NOT NULL DEFAULT true,
    last_error   text,
    last_sent_at timestamptz,
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS push_subscriptions_user_idx ON push_subscriptions (user_id, active);

-- ---------------------------------------------------------------------------
--  Journal des notifications : ce qui rend le planificateur idempotent.
--
--  La contrainte d'unicité est la garantie qu'un rappel ne part qu'une fois par
--  jour et par type, quel que soit le nombre de tics ou de répliques du serveur.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS notification_log (
    id         bigserial PRIMARY KEY,
    user_id    uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind       text NOT NULL,      -- rappel_checkin | bilan_hebdo
    sent_on    date NOT NULL,
    detail     jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, kind, sent_on)
);
