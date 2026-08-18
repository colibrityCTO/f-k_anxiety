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
    status         text NOT NULL,   -- fait | partiel | pas_fait | reporte
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
