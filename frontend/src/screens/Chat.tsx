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
  const abort = useRef<AbortController | null>(null)

  const scroll = useCallback((behavior: ScrollBehavior = 'auto') => {
    requestAnimationFrame(() => bottom.current?.scrollIntoView({ behavior, block: 'end' }))
  }, [])

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
        scroll()
        // Réarme le rappel à chaque ouverture : c'est le seul moment où on est sûr
        // que la page tourne.
        scheduleReminder(loadReminder(), () => !thread.state.checkin_done)
      })
      .catch((exception) =>
        setError(exception instanceof Error ? exception.message : 'Chargement impossible.'),
      )
      .finally(() => setLoading(false))
  }, [scroll])

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

      <div className="thread">
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
