import { useCallback, useEffect, useRef, useState } from 'react'
import Composer from '../components/Composer'
import Markdown from '../components/Markdown'
import Message from '../components/Message'
import WidgetHost from '../components/WidgetHost'
import { api, sendStream } from '../lib/api'
import { loadReminder, scheduleReminder } from '../lib/reminder'
import type { DayState, ThreadItem, WidgetType } from '../lib/types'

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

export default function Chat() {
  const [items, setItems] = useState<ThreadItem[]>([])
  const [state, setState] = useState<DayState | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [streaming, setStreaming] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  // Un seul widget ouvert à la fois : celui dont l'identifiant est ici.
  const [openId, setOpenId] = useState<string | null>(null)
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

  const merge = useCallback(
    (incoming: ThreadItem[]) => {
      setItems((current) => {
        const byId = new Map(current.map((item) => [item.id, item]))
        incoming.forEach((item) => byId.set(item.id, item))
        return [...byId.values()]
      })
      const last = lastWidgetId(incoming)
      if (last) setOpenId(last)
      scroll('smooth')
    },
    [scroll],
  )

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
    async (action: () => Promise<{ items: ThreadItem[] }>) => {
      setBusy(true)
      setError(null)
      try {
        merge((await action()).items)
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
    (type: WidgetType, label?: string) => run(() => api.openWidget(type, label)),
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
      </header>

      <div className="thread" ref={view}>
        {items.map((item) =>
          item.kind === 'widget' ? (
            <WidgetHost
              key={item.id}
              item={item}
              busy={busy}
              onSubmit={(values) => submit(item.id, values)}
              onSkip={() => skip(item.id)}
              onOpen={openWidget}
              open={openId === item.id}
              onToggle={() => setOpenId((current) => (current === item.id ? null : item.id))}
            />
          ) : (
            <Message key={item.id} item={item} busy={busy} onChoose={send} />
          ),
        )}

        {streaming !== null && (
          <div className="msg">
            {streaming ? <Markdown text={streaming} /> : <p className="dim">…</p>}
          </div>
        )}

        {error && <p className="error-text">{error}</p>}
        <div ref={bottom} />
      </div>

      <Composer busy={busy} state={state} onSend={send} onOpenWidget={openWidget} />
    </div>
  )
}
