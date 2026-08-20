import { Fragment, useCallback, useEffect, useRef, useState } from 'react'
import AccountLink from '../components/AccountLink'
import Composer from '../components/Composer'
import DayProgress from '../components/DayProgress'
import Markdown from '../components/Markdown'
import Message from '../components/Message'
import WidgetHost from '../components/WidgetHost'
import { api, sendStream } from '../lib/api'
import { cacheContext, flushQueue, loadContext } from '../lib/panic'
import { loadReminder, scheduleReminder } from '../lib/reminder'
import type { DayState, LaunchType, PanicContext, ThreadItem } from '../lib/types'
import { useAuth } from '../state/AuthContext'
import Compte from './Compte'
import QuickChill from './QuickChill'

/**
 * L'application entière : un fil, une saisie, un lanceur de widgets.
 *
 * Le fil est la source de vérité côté serveur — on n'invente pas d'item côté
 * client. Chaque action renvoie les items créés, qu'on fusionne par identifiant.
 * Seule exception : pendant le streaming, la prose s'affiche dans un bloc
 * provisoire, remplacé par l'item réel dès qu'il arrive.
 */
/** Dernier widget d'une liste d'items : c'est lui qui reste ouvert. */
function lastWidgetId(list: ThreadItem[]): string | null {
  for (let index = list.length - 1; index >= 0; index -= 1) {
    if (list[index].kind === 'widget') return list[index].id
  }
  return null
}

/**
 * Ce que la page Compte a d'urgent à dire, ou `null`.
 *
 * Sert le point sur le bouton. Volontairement limité à ce que l'utilisateur ne peut
 * pas deviner autrement : un consentement jamais répondu, un questionnaire initial
 * jamais rempli. Un point permanent serait ignoré au bout de deux jours.
 */
function accountAttention(user: { profile?: Record<string, unknown> } | null): string | null {
  const profile = user?.profile ?? {}
  const consents = (profile.consentements ?? {}) as Record<string, unknown>
  if (consents.cohorte === undefined) return 'une question de consentement attend une réponse'
  const onboarding = profile.onboarding as Record<string, unknown> | undefined
  if (!onboarding?.done_at) return 'questionnaire initial pas encore rempli'
  return null
}

/**
 * Le jour d'un item, en clair. Le fil n'avait aucun repère temporel : passé
 * quelques dizaines d'items, on ne savait plus si on lisait hier ou le mois
 * dernier. C'est la deuxième cause de difficulté de navigation, après
 * l'empilement des widgets.
 */
function dayKey(item: ThreadItem): string {
  return (item.created_at ?? '').slice(0, 10)
}

function dayLabel(key: string): string {
  if (!key) return ''
  const today = new Date()
  const asDay = (date: Date) =>
    `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(
      date.getDate(),
    ).padStart(2, '0')}`
  if (key === asDay(today)) return "Aujourd'hui"
  const yesterday = new Date(today)
  yesterday.setDate(today.getDate() - 1)
  if (key === asDay(yesterday)) return 'Hier'
  const [year, month, day] = key.split('-').map(Number)
  const date = new Date(year, month - 1, day)
  return date.toLocaleDateString('fr-FR', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    ...(date.getFullYear() === today.getFullYear() ? {} : { year: 'numeric' }),
  })
}

export default function Chat() {
  const [items, setItems] = useState<ThreadItem[]>([])
  const [state, setState] = useState<DayState | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [streaming, setStreaming] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  // Un seul widget ouvert à la fois : celui dont l'identifiant est ici.
  const [openId, setOpenId] = useState<string | null>(null)
  // Pagination : le fil est fait pour durer des années, on n'en charge qu'une page.
  const [hasMore, setHasMore] = useState(false)
  const [oldestSeq, setOldestSeq] = useState<number | null>(null)
  const [loadingMore, setLoadingMore] = useState(false)
  // Mode crise. Le contexte est mis en réserve **à l'ouverture**, quand le réseau
  // est là : en crise il n'y en a peut-être pas, et il ne doit y avoir aucune attente.
  const [panic, setPanic] = useState<{ context: PanicContext; stale: number | null } | null>(null)
  const [panicOpen, setPanicOpen] = useState(false)
  // La page Compte se superpose : le fil n'est pas démonté, donc revenir retrouve
  // la position de lecture exacte.
  const [compteOpen, setCompteOpen] = useState(false)
  const { user } = useAuth()
  const bottom = useRef<HTMLDivElement | null>(null)
  const view = useRef<HTMLDivElement | null>(null)
  const abort = useRef<AbortController | null>(null)

  const scroll = useCallback((behavior: ScrollBehavior = 'auto') => {
    requestAnimationFrame(() => bottom.current?.scrollIntoView({ behavior, block: 'end' }))
  }, [])

  /**
   * Coller au dernier message — et y rester le temps que le fil se stabilise.
   *
   * Un seul saut ne suffit pas : le fil prend sa hauteur définitive après son
   * montage (polices, markdown, graphiques des widgets), et un `scrollTop`
   * posé trop tôt atterrit au milieu. On répète donc le collage jusqu'à ce que
   * la hauteur cesse de bouger — trois trames identiques — avec un plafond de
   * trames pour ne jamais boucler indéfiniment. Le fil peut ne pas être encore
   * rendu au premier appel : on réessaie plutôt que d'abandonner.
   */
  const stickToBottom = useCallback(() => {
    let previous = -1
    let stable = 0
    let frames = 0
    // Un premier collage tout de suite, sans attendre de trame : une page cachée
    // ne rend pas de trames, et on veut être en bas *avant* d'être regardé.
    if (view.current) view.current.scrollTop = view.current.scrollHeight
    const step = () => {
      const node = view.current
      if (node) {
        node.scrollTop = node.scrollHeight
        stable = node.scrollHeight === previous ? stable + 1 : 0
        previous = node.scrollHeight
      }
      frames += 1
      if ((!node || stable < 3) && frames < 40) requestAnimationFrame(step)
    }
    requestAnimationFrame(step)
  }, [])

  /**
   * Revenir dans l'application, c'est reprendre au dernier message. Trois
   * événements pour un seul geste : `visibilitychange` couvre le retour
   * d'arrière-plan (PWA, changement d'onglet), `focus` le retour de fenêtre, et
   * `pageshow` la restauration depuis le cache de navigation d'iOS, qui ne
   * rejoue aucun des deux autres.
   */
  useEffect(() => {
    const back = () => {
      if (document.visibilityState === 'visible') stickToBottom()
    }
    document.addEventListener('visibilitychange', back)
    window.addEventListener('focus', back)
    window.addEventListener('pageshow', back)
    return () => {
      document.removeEventListener('visibilitychange', back)
      window.removeEventListener('focus', back)
      window.removeEventListener('pageshow', back)
    }
  }, [stickToBottom])

  const refreshState = useCallback(() => {
    api
      .thread()
      .then((thread) => setState(thread.state))
      .catch(() => undefined)
  }, [])

  useEffect(() => {
    api
      .thread()
      .then((thread) => {
        setItems(thread.items)
        setState(thread.state)
        setHasMore(thread.has_more)
        setOldestSeq(thread.oldest_seq)
        setOpenId(lastWidgetId(thread.items))
        stickToBottom()
        // Les polices d'affichage arrivent après le premier rendu : elles
        // décalent le fil, donc on recolle une fois qu'elles sont là.
        document.fonts?.ready.then(stickToBottom).catch(() => undefined)
        // Réarme le rappel à chaque ouverture : c'est le seul moment où on est sûr
        // que la page tourne.
        scheduleReminder(loadReminder(), () => !thread.state.checkin_done)
      })
      .catch((exception) =>
        setError(exception instanceof Error ? exception.message : 'Chargement impossible.'),
      )
      .finally(() => setLoading(false))
  }, [stickToBottom])

  /**
   * Fusionne les items renvoyés par le serveur, et retire les vues qu'il a
   * retirées. Le tri sur `seq` n'est pas cosmétique : la fusion passe par une
   * `Map`, dont l'ordre est celui de l'insertion — préfixer une page ancienne
   * sans retrier la placerait à la fin du fil.
   */
  /**
   * Prépare le mode crise à l'ouverture de l'application, et rejoue les épisodes
   * qui n'avaient pas pu partir.
   *
   * L'ordre compte : on purge d'abord, sinon le bilan mis en réserve ignorerait les
   * épisodes en attente et afficherait un compte faux. Et l'échec est silencieux au
   * démarrage : la réserve locale précédente suffit à faire fonctionner l'écran, et
   * une erreur affichée à l'ouverture pour une fonction qu'on n'utilise pas encore
   * serait du bruit.
   */
  useEffect(() => {
    let cancelled = false
    const local = loadContext()
    if (local) setPanic({ context: local.context, stale: local.ageHours })

    flushQueue()
      .then(() => api.panique())
      .then((context) => {
        if (cancelled) return
        cacheContext(context)
        setPanic({ context, stale: null })
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [])

  const merge = useCallback(
    (incoming: ThreadItem[], retired: string[] = []) => {
      setItems((current) => {
        const byId = new Map(current.map((item) => [item.id, item]))
        retired.forEach((id) => byId.delete(id))
        incoming.forEach((item) => byId.set(item.id, item))
        return [...byId.values()].sort((a, b) => a.seq - b.seq)
      })
      if (retired.length) setOpenId((current) => (current && retired.includes(current) ? null : current))
      const last = lastWidgetId(incoming)
      if (last) setOpenId(last)
      if (incoming.length) scroll('smooth')
    },
    [scroll],
  )

  /**
   * Remonter dans le fil. La hauteur ajoutée est compensée après le rendu, sinon
   * l'insertion en tête ferait sauter la lecture : le navigateur garde `scrollTop`,
   * donc tout ce qu'on regardait descend d'un bloc.
   */
  const loadMore = useCallback(async () => {
    if (oldestSeq === null || loadingMore) return
    setLoadingMore(true)
    const node = view.current
    const before = node ? node.scrollHeight - node.scrollTop : 0
    try {
      const page = await api.threadBefore(oldestSeq)
      if (page.items.length) {
        setItems((current) => {
          const byId = new Map(current.map((item) => [item.id, item]))
          page.items.forEach((item) => byId.set(item.id, item))
          return [...byId.values()].sort((a, b) => a.seq - b.seq)
        })
      }
      setHasMore(page.has_more)
      setOldestSeq(page.oldest_seq ?? oldestSeq)
      requestAnimationFrame(() => {
        if (view.current) view.current.scrollTop = view.current.scrollHeight - before
      })
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : 'Impossible de remonter le fil.')
    } finally {
      setLoadingMore(false)
    }
  }, [loadingMore, oldestSeq])

  /** Envoi d'un message : streamé, pour que la réponse s'écrive au fur et à mesure. */
  const send = useCallback(
    async (text: string) => {
      setBusy(true)
      setError(null)
      setStreaming('')
      abort.current?.abort()
      abort.current = new AbortController()
      try {
        await sendStream(
          text,
          {
            onItem: (item) => merge([item]),
            onToken: (token) => {
              setStreaming((current) => (current ?? '') + token)
              scroll('smooth')
            },
            onRetired: (ids) => merge([], ids),
            onItems: (incoming) => {
              setStreaming(null)
              merge(incoming)
              refreshState()
            },
            onError: setError,
          },
          abort.current.signal,
        )
      } catch (exception) {
        if ((exception as Error)?.name !== 'AbortError') {
          setError(exception instanceof Error ? exception.message : 'Envoi impossible.')
        }
      } finally {
        setStreaming(null)
        setBusy(false)
      }
    },
    [merge, refreshState, scroll],
  )

  const run = useCallback(
    async (action: () => Promise<{ items: ThreadItem[]; retired?: string[] }>) => {
      setBusy(true)
      setError(null)
      try {
        const result = await action()
        merge(result.items, result.retired ?? [])
        refreshState()
      } catch (exception) {
        setError(exception instanceof Error ? exception.message : 'Action impossible.')
      } finally {
        setBusy(false)
      }
    },
    [merge, refreshState],
  )

  const openWidget = useCallback(
    (type: LaunchType, label?: string) => run(() => api.openWidget(type, label)),
    [run],
  )
  const submit = useCallback(
    (itemId: string, values: Record<string, unknown>) => run(() => api.submitWidget(itemId, values)),
    [run],
  )
  const skip = useCallback((itemId: string) => run(() => api.skipWidget(itemId)), [run])

  if (loading) return <p className="spinner">Chargement du fil…</p>

  return (
    <div className="app">
      <header className="topbar">
        <div className="wordmark">Fuck&nbsp;Anxiety</div>
        {/* Le contrat du jour vit ici et pas dans le lanceur : l'état d'avancement
            était affiché à l'intérieur du menu « + », donc caché derrière un geste.
            Un objectif qu'il faut ouvrir un menu pour consulter n'en est pas un. */}
        <DayProgress state={state} busy={busy} onOpen={openWidget} />
        <AccountLink attention={accountAttention(user)} onOpen={() => setCompteOpen(true)} />
      </header>

      <div className="thread" ref={view}>
        {hasMore && (
          <button className="btn-sm thread-more" disabled={loadingMore} onClick={loadMore}>
            {loadingMore ? 'Chargement…' : 'Remonter dans le fil'}
          </button>
        )}

        {items.map((item, index) => {
          const key = dayKey(item)
          const separator =
            key && key !== (index > 0 ? dayKey(items[index - 1]) : '') ? (
              <div className="daysep" key={`sep-${key}`}>
                <span>{dayLabel(key)}</span>
              </div>
            ) : null

          return (
            <Fragment key={item.id}>
              {separator}
              {item.kind === 'widget' ? (
                <WidgetHost
                  item={item}
                  busy={busy}
                  onSubmit={(values) => submit(item.id, values)}
                  onSkip={() => skip(item.id)}
                  onOpen={openWidget}
                  open={openId === item.id}
                  onToggle={() => setOpenId((current) => (current === item.id ? null : item.id))}
                />
              ) : (
                <Message item={item} busy={busy} onChoose={send} />
              )}
            </Fragment>
          )
        })}

        {streaming !== null && (
          <div className="msg">
            {streaming ? <Markdown text={streaming} /> : <p className="dim">…</p>}
          </div>
        )}

        {error && <p className="error-text">{error}</p>}
        <div ref={bottom} />
      </div>

      <Composer
        busy={busy}
        state={state}
        onSend={send}
        onOpenWidget={openWidget}
        onPanic={() => setPanicOpen(true)}
      />

      {compteOpen && <Compte onClose={() => setCompteOpen(false)} />}

      {panicOpen && panic && (
        <QuickChill
          context={panic.context}
          stale={panic.stale}
          onClose={(recorded) => {
            setPanicOpen(false)
            // Un épisode enregistré a déposé son récapitulatif dans le fil côté
            // serveur : on recharge plutôt que de le reconstruire côté client, et on
            // rafraîchit le bilan pour la fois suivante.
            if (recorded) {
              api
                .thread()
                .then((thread) => {
                  setItems(thread.items)
                  setState(thread.state)
                  setHasMore(thread.has_more)
                  setOldestSeq(thread.oldest_seq)
                  stickToBottom()
                })
                .catch(() => undefined)
              api
                .panique()
                .then((context) => {
                  cacheContext(context)
                  setPanic({ context, stale: null })
                })
                .catch(() => undefined)
            }
          }}
        />
      )}
    </div>
  )
}
