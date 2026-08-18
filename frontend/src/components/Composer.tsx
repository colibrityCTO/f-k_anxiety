import { useState } from 'react'
import Icon from './Icon'
import type { DayState, WidgetType } from '../lib/types'

/**
 * Le lanceur. Le fil est le seul écran : tout part d'ici.
 *
 * `matin`, `soir` et `maintenant` remplacent le check-in unique. Les trois sont
 * dans la grille, et pas seulement proposés : « Là, maintenant » n'est *jamais*
 * poussé par l'application — c'est sa seule porte d'entrée, et c'est voulu.
 */
const TILES: { type: WidgetType; name: string; icon: string }[] = [
  { type: 'maintenant', name: 'Là, maintenant', icon: 'checkin' },
  { type: 'matin', name: 'Ce matin', icon: 'checkin' },
  { type: 'soir', name: 'Ce soir', icon: 'checkin' },
  { type: 'breath', name: 'Respirer', icon: 'breath' },
  { type: 'journal', name: 'Journal', icon: 'journal' },
  { type: 'exposition', name: 'Exposition', icon: 'expo' },
  { type: 'interoceptif', name: 'Sensations', icon: 'sensations' },
  { type: 'meditation', name: 'Méditation', icon: 'meditation' },
  { type: 'echelles', name: 'Échelles', icon: 'scale' },
  { type: 'prevision', name: 'Demain', icon: 'analysis' },
  { type: 'stats', name: 'Mes chiffres', icon: 'stats' },
  { type: 'analysis', name: 'Analyse', icon: 'analysis' },
  { type: 'memoire', name: 'Mémoire', icon: 'memory' },
  { type: 'rapport', name: 'Rapport', icon: 'report' },
  { type: 'sources', name: 'Sources', icon: 'sources' },
  // `account` et `logout` ont quitté la grille : ils vivent dans la page Compte,
  // atteignable en haut à droite. Leurs types restent acceptés côté serveur et
  // dans `WidgetType`, parce que des items de ces types sont déjà dans les fils.
]

export default function Composer({
  busy,
  state,
  onSend,
  onOpenWidget,
  onPanic,
}: {
  busy: boolean
  state: DayState | null
  onSend: (text: string) => void
  onOpenWidget: (type: WidgetType, label?: string) => void
  /** Ouvre le mode crise. Hors de la grille : en crise, un geste suffit. */
  onPanic: () => void
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
        {/* Jamais désactivé, même pendant un envoi : une crise n'attend pas la fin
            d'une requête. Et hors de la grille des widgets, parce qu'ouvrir un menu
            puis choisir une tuile fait trois gestes de trop. */}
        <button className="panicbtn" onClick={onPanic} aria-label="Mode crise — quick chill">
          CHILL
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
              {state.mesures_instantanees > 0
                ? ` · ${state.mesures_instantanees} mesure(s) aujourd'hui`
                : ''}
            </p>
          )}
        </div>
      )}
    </div>
  )
}
