export type SourceRef = { label: string; url?: string | null }

export type User = {
  id: string
  email: string
  display_name?: string | null
  timezone: string
  ai_consent: boolean
  profile: Record<string, unknown>
  created_at?: string | null
}

export type WidgetType =
  // V1
  | 'checkin'
  | 'breath'
  | 'journal'
  | 'gad7' // conservé : les items déjà dans le fil gardent ce type
  | 'stats'
  | 'analysis'
  | 'sources'
  | 'account'
  | 'logout'
  // V2
  | 'exposition'
  | 'meditation'
  | 'memoire'
  | 'echelles'
  // V3
  | 'interoceptif'
  | 'rapport'
  // V5 — le check-in unique éclaté en trois. `checkin` est conservé : les items déjà
  // dans le fil gardent leur type, et le passé ne se réécrit pas.
  | 'matin'
  | 'soir'
  | 'maintenant'
  | 'panique'
  | 'prevision'
  | 'onboarding'
  | 'jour'

export type JournalEntry = {
  id?: string
  entry_date?: string
  kind: 'libre' | 'pensee' | 'exposition' | 'inquietude'
  situation?: string | null
  emotions: string[]
  body_sensations: string[]
  intensity_before?: number | null
  intensity_after?: number | null
  /** Le pourcentage de croyance : mesure la restructuration, pas l'émotion. */
  belief_before_0_100?: number | null
  belief_after_0_100?: number | null
  /** Intéroceptif : ressemblance des sensations provoquées à celles des crises. */
  similarity_0_10?: number | null
  automatic_thought?: string | null
  thinking_trap?: string | null
  evidence_for?: string | null
  evidence_against?: string | null
  coping_plan?: string | null
  alternative_thought?: string | null
  prediction?: string | null
  prediction_probability?: number | null
  actual_outcome?: string | null
  learning?: string | null
  safety_behaviors_dropped: string[]
  worry_text?: string | null
  worry_actionable?: boolean | null
  next_action?: string | null
  free_text?: string | null
  created_at?: string
}

export type PushKey = {
  disponible: boolean
  cle_publique: string | null
  rappel: { actif: boolean; heure: string }
  appareils: {
    endpoint: string
    user_agent: string | null
    actif: boolean
    dernier_envoi: string | null
    derniere_erreur: string | null
  }[]
  explication: string
}

export type PushStatus = {
  planificateur_actif: boolean
  intervalle_s: number
  push_disponible: boolean
  rappel: { actif: boolean; heure: string }
  envois_recents: { kind: string; sent_on: string; created_at: string }[]
}

export type PushSubscriptionPayload = {
  endpoint: string
  p256dh: string
  auth: string
  user_agent?: string
}

export type InteroceptiveExercise = {
  slug: string
  name: string
  seconds: number
  how: string
  sensations: string[]
  evidence: string
  note?: string | null
}

export type InteroceptivePayload = {
  exercices: InteroceptiveExercise[]
  contre_indications: string[]
  mecanisme: string
  sources: SourceRef[]
  valide_le: string | null
  compte_par_exercice: Record<string, number>
}

export type ReportPayload = {
  genere_le: string
  periode: { debut: string; fin: string; jours: number }
  compte: { email: string; depuis: string | null }
  cadre: string
  programme: DayState
  signaux: Signal[]
  /**
   * L'agrégat du log d'attaque : la preuve rétrospective. « 0 fois sur 14 » s'appuie
   * sur les réponses de l'utilisateur, jamais sur une lecture de son texte libre —
   * l'application ne peut pas juger d'une phrase, et prétendre le faire serait
   * inventer.
   */
  episodes: PanicBilan
  quotidien: Record<string, string | number | null>[]
  echelles: { instrument: string; taken_on: string; total: number; severity: string | null }[]
  expositions: {
    label: string
    kind: string
    anticipated_anxiety: number | null
    attempts: number
    last_attempt_on: string | null
    best_learning: string | null
    mastered: boolean
  }[]
  apprentissages: {
    entry_date: string
    situation: string | null
    prediction: string | null
    prediction_probability: number | null
    actual_outcome: string | null
    learning: string | null
  }[]
  activites: {
    title: string
    faites: number
    non_faites: number
    effet_moyen: number | null
  }[]
}

export type ExposureItem = {
  id: string
  label: string
  kind: 'in_vivo' | 'interoceptif' | 'imaginaire'
  anticipated_anxiety?: number | null
  safety_behaviors: string[]
  attempts: number
  last_attempt_on?: string | null
  best_learning?: string | null
  mastered: boolean
}

export type Citation = {
  doc_id: string
  titre: string
  niveau_de_preuve?: string | null
  sources: SourceRef[]
  extraits: (string | null)[]
  recuperation?: Record<string, unknown>
}

/** Un item du fil : soit un message, soit un widget. Jamais autre chose. */
export type ThreadItem = {
  id: string
  /** Curseur de pagination du fil : monotone, jamais réutilisé. */
  seq: number
  role: 'user' | 'assistant'
  kind: 'text' | 'widget'
  content?: string | null
  widget_type?: WidgetType | null
  payload: { prefill?: Record<string, unknown>; a_verifier?: string[] }
  saved_values: Record<string, unknown>
  /**
   * `remplace` : un widget du même type validé plus tard a pris sa place.
   * `perime`   : la journée est passée sans validation — personne ne l'a remplacé.
   */
  status?: 'ouvert' | 'valide' | 'reporte' | 'remplace' | 'perime' | null
  suggestions: string[]
  citations: Citation[]
  engine?: string | null
  created_at?: string
  /**
   * Vue de consultation : elle n'a écrit aucune donnée. Le serveur n'en renvoie
   * jamais plus d'une, et la retire dès qu'une autre est ouverte.
   */
  ephemeral?: boolean
}

export type DayState = {
  date: string
  /** Vrai dès qu'un des deux moments est renseigné. */
  checkin_done: boolean
  matin_done: boolean
  soir_done: boolean
  /** Nombre de « comment je me sens là » notés aujourd'hui. */
  mesures_instantanees: number
  pic_instantane: number | null
  anxiety_today: number | null
  week: number
  module: number
  module_title: string
  module_goal: string
  streak: number
  gad7_due: boolean
  gad7_last: number | null
  gad7_last_on: string | null
  /** `actif` ou `entretien` — bascule automatique au critère de sortie. */
  status: string
  critere: {
    gad7_ok?: boolean
    expositions_ok?: boolean
    expositions_restantes?: number
    remission?: boolean
    rechute_probable?: boolean
    gad7_mesures?: { date: string; total: number }[]
  }
  exposition_due: boolean
  jours_depuis_exposition: number | null
}

export type MemoryStats = {
  total: number
  vectorises: number
  par_source: { source_kind: string; n: number; vectorises: number; depuis: string | null }[]
}

/** Une page du fil. `oldest_seq` est le curseur à repasser pour remonter. */
export type ThreadPage = {
  items: ThreadItem[]
  total: number
  has_more: boolean
  oldest_seq: number | null
}

/** La première page : elle seule porte l'état du jour et l'ouverture proactive. */
export type Thread = ThreadPage & {
  state: DayState
  memoire: MemoryStats
}

// --- QUICK CHILL -----------------------------------------------------------

export type PanicTool = {
  slug: string
  name: string
  step: 'respirer' | 'ancrer' | 'froid' | 'jeu'
  seconds: number
  how: string
  pattern: { inhale: number; hold: number; exhale: number } | null
  evidence: string
  mechanism: string
  /** La réserve à afficher **avec** l'outil, pas ailleurs. */
  caveat: string | null
  sources: SourceRef[]
  contraindications: string | null
}

export type PanicBilan = {
  episodes: number
  tous_termines: boolean
  duree_mediane_min: number | null
  duree_max_min: number | null
  redoute_renseigne: number
  redoute_arrive: number
  outils: [string, number][]
  derniers: {
    date: string
    pic: number | null
    apres: number | null
    minutes: number | null
    ce_qui_est_arrive: string | null
    redoute_arrive: boolean | null
  }[]
  /** Composée côté serveur : c'est un fait construit sur des comptes. */
  phrase: string | null
}

export type PanicContext = {
  cadrage: string
  zones: string[]
  pensees: { label: string; reframe: string }[]
  outils: PanicTool[]
  sources: SourceRef[]
  froid_valide_le: string | null
  bilan: PanicBilan
  usage_7j: number
  seuil_usage: number
  /** Garde-fou anti-comportement de sécurité : usage élevé **et** GAD-7 stable. */
  alerte_usage: string | null
}

export type PanicEpisodeIn = {
  what_preceded?: string | null
  body_symptoms: string[]
  thought_in_moment?: string | null
  tools_used: { slug: string; seconds?: number }[]
  anxiety_before?: number | null
  anxiety_peak?: number | null
  anxiety_after?: number | null
  time_to_relief_min?: number | null
  what_actually_happened?: string | null
  feared_outcome_happened?: boolean | null
  confirm_cold_contraindications?: boolean
}

// --- Charge du jour et prévision -------------------------------------------

export type ForecastPayload = {
  date: string
  /** La vérité de référence : elle ne se calcule pas. */
  anxiete_declaree: number | null
  charge: {
    /** `null` quand aucune association personnelle n'a survécu à la correction. */
    valeur: number | null
    raison: string | null
    methode?: string
    composantes: {
      facteur: string
      poids: number
      actif: boolean | null
      valeur?: number
      ta_moyenne?: number
      note?: string
    }[]
  }
  prevision: {
    target_date: string
    model: string
    predicted: number
    interval_low: number
    interval_high: number
    baseline: number
    predictors: Record<string, number | null>
    validation: {
      prédicteurs: string[]
      n_test: number
      mae_persistance: number | null
      mae_regression: number | null
      /** `persistance` tant que le modèle ne fait pas mieux — et il ne triche pas. */
      gagnant: string
      methode: string
      raison?: string
    }
    phrase: string
  } | null
  historique: {
    n: number
    mae: number | null
    mae_persistance: number | null
    /** Part des observations tombées dans la fourchette annoncée. */
    couverture: number | null
    detail: {
      date: string
      annonce: number
      observe: number
      erreur: number
      erreur_persistance: number | null
      dans_intervalle: boolean | null
      modele: string
    }[]
  }
}

// --- Intégrations ----------------------------------------------------------

export type Integrations = {
  whoop: {
    /** Le serveur a-t-il des identifiants ? Sinon l'intégration n'est pas proposée. */
    configure: boolean
    connecte: boolean
    scopes?: string[]
    expire_le?: string | null
    derniere_synchro?: string | null
    derniere_erreur?: string | null
    volume?: { jours?: number; seances?: number; dernier_jour?: string | null }
    /** Ce que cette source peut et ne peut pas faire, dit là où la question se pose. */
    limite: string
  }
}

export type MemoryRow = {
  source_kind: string
  entry_date: string | null
  content: string
  mode?: string
}

export type Instrument = {
  instrument: string
  title: string
  prompt: string
  options: { value: number; label: string }[]
  items: string[]
  explanation: string
  sources: SourceRef[]
  limits: string
}

export type HistoryPayload = {
  quotidien: Record<string, number | string | null>[]
  gad7: { taken_on: string; total: number; severity: string }[]
  assiduite: { entry_date: string; faites: number; total: number }[]
}

export type Signal = {
  id: string
  label: string
  value: unknown
  delta?: number | null
  verdict?: string
  method?: string
  observations: Record<string, unknown>[]
  n?: number
  /**
   * Corrélations (V5). `value` reste le coefficient en **niveau brut**, conservé pour
   * compatibilité ; `value_variations` est celui calculé sur les variations d'un jour
   * sur l'autre, seul défendable — l'anxiété est fortement autocorrélée, et deux
   * séries qui dérivent ensemble corrèlent sans lien. L'écart entre les deux est en
   * soi une information à afficher.
   *
   * `retenu` est faux quand l'association ne survit pas à la correction de
   * multiplicité : dans ce cas elle ne doit **pas** être présentée comme un fait.
   */
  value_variations?: number | null
  ic?: [number | null, number | null]
  p?: number | null
  retenu?: boolean
  n_brut?: number
}

export type SignalsPayload = {
  periode: { debut: string; fin: string; jours: number }
  signaux: Signal[]
  drapeaux_rouges: string[]
  brut: Record<string, number>
}

export type Insight = {
  id: string
  headline?: string | null
  body: string
  citations: Citation[]
  engine: string
  risk_flag: boolean
  period_start: string
  period_end: string
  signals: SignalsPayload
}

export type Activity = {
  slug: string
  title: string
  duration_min: number
  evidence_level: string
  mechanism: string
  sources: SourceRef[]
  instructions: string[]
  contraindications?: string | null
  kb_doc_id?: string | null
}

/** Un item du parcours du jour, tel que `build_day()` le calcule. */
export type ProgramDayItem = {
  activity: Activity
  slot: 'socle' | 'corps' | 'module' | 'adaptatif'
  /** La justification personnalisée, avec les chiffres de la personne. */
  why_for_you: string
  /** Les observations exactes qui ont déclenché l'item — le panneau « d'où ça sort ». */
  triggered_by: Record<string, unknown>[]
  status?: 'fait' | 'partiel' | 'pas_fait' | 'reporte' | null
  /** Le widget que l'item ouvre, ou `null` pour un conseil d'hygiène. */
  widget?: string | null
}

export type ProgramDay = {
  entry_date: string
  week: number
  module: number
  module_title: string
  module_goal: string
  phase_explainer: string
  items: ProgramDayItem[]
  checkin_done: boolean
  adherence_7j: number
  streak: number
  /** Jours réellement pratiqués, distinct de la semaine calendaire. */
  jours_pratiques: number
  gad7_due: boolean
  notices: string[]
}

export type KbDoc = {
  doc_id: string
  title: string
  category?: string | null
  evidence_level?: string | null
  sources: SourceRef[]
}

export type KbDocDetail = KbDoc & { content: string }

export type EngineStatus = {
  moteurs_disponibles: string[]
  moteur_principal: string | null
  fallback: string | null
  recherche_vectorielle: boolean
  modele_embeddings: string | null
  consentement_utilisateur: boolean
  mode_effectif: 'llm' | 'local_deterministe'
  explication: string
}
