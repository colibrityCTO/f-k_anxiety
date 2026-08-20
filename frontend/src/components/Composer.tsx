import { useState } from 'react'
import Icon from './Icon'
import type { DayState, LaunchType } from '../lib/types'

/**
 * Le lanceur, à deux niveaux.
 *
 * Il en avait seize à plat, et la grille contredisait le serveur sur deux points.
 * « Ce matin », « Ce soir » et « Là, maintenant » y étaient côte à côte, ce qui
 * laissait ouvrir le formulaire du soir à dix heures — alors que le serveur
 * l'interdit, et pour une raison qui tient : à midi la journée n'est pas finie, la
 * faire résumer produit un chiffre faux, et corriger ce chiffre ensuite apprend que
 * les saisies ne comptent pas. Rien n'empêchait non plus de redemander une nuit
 * déjà notée. **Noter** remplace les trois : le serveur résout la demande en matin,
 * soir ou mesure instantanée selon l'heure et selon ce qui manque encore.
 *
 * « Mon parcours » n'y est plus non plus : il est sous le titre, déplié d'un geste,
 * parce que c'est l'état du jour et pas un événement à déposer dans un fil.
 *
 * Le reste se range en deux groupes. **Pratiquer** est ce qui se fait — le second
 * niveau est la porte d'entrée manuelle vers les exercices ; le programme du jour,
 * lui, en propose déjà un dans le fil avec sa justification chiffrée. **Mes
 * données** est ce qui se lit, jamais urgent, et qui occupait la moitié de l'écran
 * de lancement.
 */
type Tile = { type: LaunchType; name: string; icon: string }
type Group = { key: 'pratiquer' | 'donnees'; name: string; icon: string; note: string; tiles: Tile[] }

// « Mon parcours » a quitté la grille : il vit sous le titre, en permanence. Un
// programme n'est pas quelque chose qu'on lance, c'est l'état du jour.
const DIRECT: Tile[] = [
  // `noter` n'est pas un type de widget : c'est une demande, résolue côté serveur.
  { type: 'noter', name: 'Noter', icon: 'noter' },
]

const GROUPS: Group[] = [
  {
    key: 'pratiquer',
    name: 'Pratiquer',
    icon: 'pratique',
    note: 'Les exercices, à lancer quand tu veux. Le programme t’en propose déjà un par jour, avec sa raison.',
    tiles: [
      { type: 'breath', name: 'Respirer', icon: 'breath' },
      { type: 'meditation', name: 'Méditation', icon: 'meditation' },
      { type: 'interoceptif', name: 'Sensations', icon: 'sensations' },
      { type: 'exposition', name: 'Exposition', icon: 'expo' },
      { type: 'journal', name: 'Journal', icon: 'journal' },
      { type: 'echelles', name: 'Échelles', icon: 'scale' },
    ],
  },
  {
    key: 'donnees',
    name: 'Mes données',
    icon: 'stats',
    note: 'Rien à remplir ici : ça se lit. Aucune de ces vues ne laisse de trace dans le fil.',
    tiles: [
      { type: 'stats', name: 'Mes chiffres', icon: 'stats' },
      { type: 'analysis', name: 'Analyse', icon: 'analysis' },
      { type: 'prevision', name: 'Demain', icon: 'analysis' },
      { type: 'memoire', name: 'Mémoire', icon: 'memory' },
      { type: 'rapport', name: 'Rapport', icon: 'report' },
      { type: 'sources', name: 'Sources', icon: 'sources' },
    ],
  },
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
  onOpenWidget: (type: LaunchType, label?: string) => void
  /** Ouvre le mode crise. Hors de la grille : en crise, un geste suffit. */
  onPanic: () => void
}) {
  const [text, setText] = useState('')
  const [open, setOpen] = useState(false)
  const [group, setGroup] = useState<Group | null>(null)

  function close() {
    setOpen(false)
    setGroup(null)
  }

  function send() {
    const value = text.trim()
    if (!value || busy) return
    setText('')
    close()
    onSend(value)
  }

  function launch(tile: Tile) {
    close()
    onOpenWidget(tile.type, tile.name)
  }

  /**
   * Ce que « Noter » va ouvrir, en clair sous la tuile. Le serveur tranche seul,
   * mais annoncer sa décision évite le seul reproche qu'on puisse faire à une
   * entrée unique : ne pas savoir ce qu'on va obtenir en appuyant.
   */
  const noterHint = !state
    ? null
    : !state.matin_done
      ? 'ta nuit'
      : !state.soir_done && new Date().getHours() >= 17
        ? 'ta journée'
        : 'ton niveau, là'

  return (
    <div className="composer">
      <div className="inputrow">
        <button
          className="iconbtn"
          aria-expanded={open}
          aria-label="Ouvrir les widgets"
          onClick={() => (open ? close() : setOpen(true))}
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
          {group ? (
            <>
              <button className="btn-sm launcher-back" onClick={() => setGroup(null)}>
                <Icon name="back" size={14} /> {group.name}
              </button>
              <p className="tiny dim">{group.note}</p>
              <div className="tiles">
                {group.tiles.map((tile) => (
                  <button
                    key={tile.type}
                    className="tile"
                    disabled={busy}
                    onClick={() => launch(tile)}
                  >
                    <Icon name={tile.icon} />
                    <span className="nm">{tile.name}</span>
                  </button>
                ))}
              </div>
            </>
          ) : (
            <div className="tiles">
              {DIRECT.map((tile) => (
                <button
                  key={tile.type}
                  className="tile"
                  disabled={busy}
                  onClick={() => launch(tile)}
                >
                  <Icon name={tile.icon} />
                  <span className="nm">{tile.name}</span>
                  {tile.type === 'noter' && noterHint && (
                    <span className="tile-hint">{noterHint}</span>
                  )}
                </button>
              ))}
              {GROUPS.map((entry) => (
                <button
                  key={entry.key}
                  className="tile tile-group"
                  disabled={busy}
                  onClick={() => setGroup(entry)}
                >
                  <Icon name={entry.icon} />
                  <span className="nm">{entry.name}</span>
                  <span className="tile-hint">{entry.tiles.length} ›</span>
                </button>
              ))}
            </div>
          )}

          {state && !group && (
            <p className="tiny dim" style={{ marginTop: 'var(--g2)', marginBottom: 0 }}>
              Semaine {state.week} · module {state.module} — {state.module_title}
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
