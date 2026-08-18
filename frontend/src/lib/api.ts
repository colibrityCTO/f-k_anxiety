import type {
  Activity,
  EngineStatus,
  ExposureItem,
  HistoryPayload,
  Instrument,
  InteroceptivePayload,
  JournalEntry,
  KbDoc,
  KbDocDetail,
  ForecastPayload,
  Integrations,
  ProgramDay,
  PanicContext,
  PanicEpisodeIn,
  PushKey,
  PushStatus,
  PushSubscriptionPayload,
  ReportPayload,
  MemoryRow,
  MemoryStats,
  Thread,
  ThreadItem,
  ThreadPage,
  User,
  WidgetType,
} from './types'

const BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? '/api'
const TOKEN_KEY = 'fa.token'

export const getToken = () => localStorage.getItem(TOKEN_KEY)
export const setToken = (token: string | null) =>
  token ? localStorage.setItem(TOKEN_KEY, token) : localStorage.removeItem(TOKEN_KEY)

export const AUTH_EXPIRED_EVENT = 'fa:auth-expired'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  headers.set('Content-Type', 'application/json')
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)

  const response = await fetch(`${BASE}${path}`, { ...init, headers })

  if (response.status === 401) {
    setToken(null)
    window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT))
    throw new ApiError(401, 'Session expirée.')
  }
  if (!response.ok) {
    let detail = `Erreur ${response.status}`
    try {
      const body = await response.json()
      if (typeof body.detail === 'string') detail = body.detail
      else if (Array.isArray(body.detail))
        detail = body.detail.map((d: { msg?: string }) => d.msg ?? '').join(' · ')
    } catch {
      /* réponse non JSON */
    }
    throw new ApiError(response.status, detail)
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

const get = <T>(path: string) => request<T>(path)
const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) })
const patch = <T>(path: string, body: unknown) =>
  request<T>(path, { method: 'PATCH', body: JSON.stringify(body) })

type AuthResponse = { access_token: string; expires_in: number; user: User }
/**
 * `retired` : identifiants des vues que le serveur a retirées du fil (consulter
 * ses chiffres n'est pas un événement de l'historique). Le front doit les enlever
 * de son propre état, sinon elles resteraient affichées jusqu'au rechargement.
 */
type ItemsResponse = { items: ThreadItem[]; retired?: string[]; risk?: boolean }

export const api = {
  // --- Compte (seul endroit hors du fil) ----------------------------------
  register: (email: string, password: string, display_name?: string) =>
    post<AuthResponse>('/auth/register', { email, password, display_name }),
  login: (email: string, password: string) => post<AuthResponse>('/auth/login', { email, password }),
  me: () => get<User>('/auth/me'),
  // `ai_consent` n'est pas modifiable : l'IA est active sur tous les comptes et
  // le serveur refuse de la remettre à false.
  updateMe: (payload: Partial<Pick<User, 'display_name' | 'profile'>>) =>
    patch<User>('/auth/me', payload),

  // --- Le fil --------------------------------------------------------------
  thread: () => get<Thread>('/chat/thread'),
  // --- QUICK CHILL --------------------------------------------------------
  //
  // Le contexte est chargé **au démarrage**, pas au moment du pic : en crise il n'y
  // a peut-être pas de réseau, et il ne doit surtout pas y avoir d'attente.
  panique: () => get<PanicContext>('/chat/panique'),
  prevision: () => get<ForecastPayload>('/chat/prevision'),

  // --- Intégrations --------------------------------------------------------
  integrations: () => get<Integrations>('/integrations'),
  whoopAuthorize: () => post<{ url: string }>('/integrations/whoop/authorize'),
  whoopSync: (days = 30) =>
    post<{ importe: Record<string, number> }>(`/integrations/whoop/sync?days=${days}`),
  whoopDisconnect: (purge: boolean) =>
    request<{ supprime: Record<string, number> }>(
      `/integrations/whoop?purge=${purge ? 'true' : 'false'}`,
      { method: 'DELETE' },
    ),
  recordPanic: (episode: PanicEpisodeIn) =>
    post<{ items: ThreadItem[]; bilan: unknown }>('/chat/panique', episode),

  /** Page précédente du fil. `before` est le `seq` du plus ancien item affiché. */
  threadBefore: (before: number, limit = 50) =>
    get<ThreadPage>(`/chat/thread?before=${before}&limit=${limit}`),
  send: (text: string) => post<ItemsResponse>('/chat/message', { text }),
  openWidget: (type: WidgetType, label?: string, prefill?: Record<string, unknown>) =>
    post<ItemsResponse>('/chat/widget', { type, label, prefill: prefill ?? {} }),
  submitWidget: (itemId: string, values: Record<string, unknown>) =>
    post<ItemsResponse>(`/chat/widget/${itemId}/submit`, { values }),
  skipWidget: (itemId: string) => post<ItemsResponse>(`/chat/widget/${itemId}/skip`),

  // --- Mémoire personnelle -------------------------------------------------
  memory: (q?: string) =>
    get<{ stats: MemoryStats; resultats?: MemoryRow[]; recents?: MemoryRow[] }>(
      `/chat/memory${q ? `?q=${encodeURIComponent(q)}` : ''}`,
    ),
  reindexMemory: () => post<{ stats: MemoryStats; vectorises: number }>('/chat/memory/reindex'),

  // --- Contenu des widgets -------------------------------------------------
  exposures: () => get<ExposureItem[]>('/exposures'),
  interoceptive: () => get<InteroceptivePayload>('/chat/interoceptif'),
  report: (days = 90) => get<ReportPayload>(`/chat/rapport?days=${days}`),
  instruments: () => get<{ instruments: Instrument[] }>('/assessments/instruments'),
  history: (days = 30) => get<HistoryPayload>(`/program/history?days=${days}`),
  /** Le parcours du jour : socle, module de la semaine, et items adaptatifs. */
  programDay: () => get<ProgramDay>('/program/today'),
  activity: (slug: string) => get<Activity>(`/activities/${slug}`),
  knowledge: () => get<KbDoc[]>('/knowledge'),
  knowledgeDoc: (docId: string) => get<KbDocDetail>(`/knowledge/${docId}`),
  engineStatus: () => get<EngineStatus>('/insights/engine'),

  // --- Journal : relire et corriger une entrée passée ----------------------
  journal: (kind?: string, days = 90) =>
    get<JournalEntry[]>(`/journal?days=${days}${kind ? `&kind=${kind}` : ''}`),
  updateJournal: (id: string, payload: Partial<JournalEntry>) =>
    patch<JournalEntry>(`/journal/${id}`, payload),

  // --- Notifications push --------------------------------------------------
  pushKey: () => get<PushKey>('/push/key'),
  pushSubscribe: (payload: PushSubscriptionPayload) =>
    post<{ abonnement: unknown }>('/push/subscribe', payload),
  pushUnsubscribe: (payload: PushSubscriptionPayload) =>
    post<{ supprimes: number }>('/push/unsubscribe', payload),
  pushReminder: (enabled: boolean, time: string) =>
    post<{ rappel: { actif: boolean; heure: string }; note: string; push_disponible: boolean }>(
      '/push/reminder',
      { enabled, time },
    ),
  pushTest: () => post<{ envoyes: number; revoques: number; echecs: number }>('/push/test'),
  pushStatus: () => get<PushStatus>('/push/status'),

  // --- Tes données ---------------------------------------------------------
  exportData: () => get<Record<string, unknown>>('/auth/export'),
  deleteAccount: (email: string) =>
    post<{ supprime: boolean; lignes_effacees: Record<string, number> }>('/auth/delete', { email }),
}

// --- Streaming SSE du fil ---------------------------------------------------

export type StreamHandlers = {
  /** Le message de l'utilisateur, créé côté serveur, renvoyé immédiatement. */
  onItem?: (item: ThreadItem) => void
  onEngine?: (engine: string) => void
  /** Fragments de prose, à afficher au fur et à mesure. */
  onToken?: (token: string) => void
  /** Vues retirées du fil par le serveur : à enlever de l'état local. */
  onRetired?: (ids: string[]) => void
  /** Items définitifs (message de l'assistant, widget éventuel). */
  onItems?: (items: ThreadItem[]) => void
  onError?: (message: string) => void
  onDone?: () => void
}

/**
 * On passe par `fetch` et non par `EventSource` : ce dernier n'accepte ni POST
 * ni en-tête Authorization, alors que toute l'API exige un jeton.
 */
export async function sendStream(
  text: string,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const token = getToken()
  const response = await fetch(`${BASE}/chat/message/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ text }),
    signal,
  })

  if (response.status === 401) {
    setToken(null)
    window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT))
    handlers.onError?.('Session expirée.')
    return
  }
  if (!response.ok || !response.body) {
    handlers.onError?.(`Le serveur a répondu ${response.status}.`)
    return
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  // Un flux qui se termine sans `items` ni `error` laisserait le bloc provisoire
  // disparaître sans rien dire : on garde la trace pour pouvoir l'expliquer.
  let settled = false

  const dispatch = (raw: string) => {
    let event = 'message'
    const dataLines: string[] = []
    for (const line of raw.split(/\r\n|\r|\n/)) {
      if (line.startsWith('event:')) event = line.slice(6).trim()
      else if (line.startsWith('data:')) dataLines.push(line.slice(5).replace(/^ /, ''))
    }
    const data = dataLines.join('\n')
    switch (event) {
      case 'item':
        handlers.onItem?.(JSON.parse(data) as ThreadItem)
        break
      case 'engine':
        handlers.onEngine?.(data)
        break
      case 'token':
        handlers.onToken?.(data)
        break
      case 'retired':
        handlers.onRetired?.(JSON.parse(data) as string[])
        break
      case 'items':
        settled = true
        handlers.onItems?.(JSON.parse(data) as ThreadItem[])
        break
      case 'error':
        settled = true
        handlers.onError?.(data)
        break
      case 'done':
        handlers.onDone?.()
        break
      default:
        break
    }
  }

  /**
   * Ajoute un paquet au tampon en ramenant les fins de ligne à `\n`.
   *
   * `sse-starlette` termine ses lignes en CRLF — la spec SSE l'autorise, au même
   * titre que LF ou CR seul. Sans normalisation, la fin d'événement `\r\n\r\n`
   * ne contient aucun `\n\n` : plus aucun événement n'est détecté, et toute la
   * réponse est perdue. Un CR final est mis de côté : il peut être la première
   * moitié d'un CRLF coupé entre deux paquets.
   */
  const feed = (packet: string) => {
    const merged = buffer + packet
    const held = merged.endsWith('\r') ? '\r' : ''
    buffer = merged.slice(0, merged.length - held.length).replace(/\r\n|\r/g, '\n') + held
  }

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    feed(decoder.decode(value, { stream: true }))
    let separator = buffer.indexOf('\n\n')
    while (separator !== -1) {
      dispatch(buffer.slice(0, separator))
      buffer = buffer.slice(separator + 2)
      separator = buffer.indexOf('\n\n')
    }
  }
  if (buffer.trim()) dispatch(buffer)

  if (!settled) handlers.onError?.('Le flux a été interrompu avant la réponse.')
}
