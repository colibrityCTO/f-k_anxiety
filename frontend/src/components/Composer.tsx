import { useState } from 'react'
import Icon from './Icon'
import type { DayState, WidgetType } from '../lib/types'

/** Les quatorze widgets. Le fil est le seul écran : tout part d'ici. */
const TILES: { type: WidgetType; name: string; icon: string }[] = [
  { type: 'checkin', name: 'Check-in', icon: 'checkin' },
  { type: 'breath', name: 'Respirer', icon: 'breath' },
  { type: 'journal', name: 'Journal', icon: 'journal' },
  { type: 'exposition', name: 'Exposition', icon: 'expo' },
  { type: 'interoceptif', name: 'Sensations', icon: 'sensations' },
  { type: 'meditation', name: 'Méditation', icon: 'meditation' },
  { type: 'echelles', name: 'Échelles', icon: 'scale' },
  { type: 'stats', name: 'Mes chiffres', icon: 'stats' },
  { type: 'analysis', name: 'Analyse', icon: 'analysis' },
  { type: 'memoire', name: 'Mémoire', icon: 'memory' },
  { type: 'rapport', name: 'Rapport', icon: 'report' },
  { type: 'sources', name: 'Sources', icon: 'sources' },
  { type: 'account', name: 'Compte', icon: 'account' },
  { type: 'logout', name: 'Sortir', icon: 'logout' },
]

export default function Composer({
  busy,
  state,
  onSend,
  onOpenWidget,
}: {
  busy: boolean
  state: DayState | null
  onSend: (text: string) => void
  onOpenWidget: (type: WidgetType, label?: string) => void
}) {
  const [text, setText] = useState('')
  const [open, setOpen] = useState(false)

  function send() {
    const value = text.trim()
    if (!value || busy) return
    setText('')
    setOpen(false)
    onSend(value)
  }

  return (
    <div className="composer">
      <div className="inputrow">
        <button
          className="iconbtn"
          aria-expanded={open}
          aria-label="Ouvrir les widgets"
          onClick={() => setOpen((value) => !value)}
        >
          <Icon name={open ? 'close' : 'plus'} />
        </button>
        <input
          value={text}
          placeholder="Écrire… ou lancer un widget avec +"
          autoComplete="off"
          onChange={(event) => setText(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') send()
          }}
        />
        <button className="sendbtn" onClick={send} disabled={busy || !text.trim()}>
          OK
        </button>
      </div>

      {open && (
        <div className="launcher">
          <div className="tiles">
            {TILES.map((tile) => (
              <button
                key={tile.type}
                className="tile"
                disabled={busy}
                onClick={() => {
                  setOpen(false)
                  onOpenWidget(tile.type, tile.name)
                }}
              >
                <Icon name={tile.icon} />
                <span className="nm">{tile.name}</span>
              </button>
            ))}
          </div>
          {state && (
            <p className="tiny dim" style={{ marginTop: 'var(--g2)', marginBottom: 0 }}>
              Semaine {state.week} · module {state.module} — {state.module_title}
              {state.streak > 0 ? ` · ${state.streak} jour(s) d'affilée` : ''}
              {state.gad7_last !== null ? ` · GAD-7 ${state.gad7_last}` : ''}
            </p>
          )}
        </div>
      )}
    </div>
  )
}
