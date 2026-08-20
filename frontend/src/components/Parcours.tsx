import { useState } from 'react'
import Icon from './Icon'
import ProgrammeDuJour from './ProgrammeDuJour'
import type { DayState, LaunchType } from '../lib/types'

/**
 * Le bandeau du jour, sous le titre, toujours là.
 *
 * Il porte deux choses et rien d'autre : **la date**, et **le contrat du jour** —
 * noter, respirer, écrire. Déplié, il montre le programme entier : le module de la
 * semaine, ce que les données ont déclenché, et la justification chiffrée de chaque
 * item.
 *
 * Pourquoi il n'est plus un widget du fil. Un programme n'est pas un événement,
 * c'est l'état du jour : le déposer dans un fil chronologique le faisait défiler
 * avec le reste, et deux minutes plus tard il fallait le rouvrir depuis un menu.
 * L'information la plus consultée était la plus difficile à retrouver.
 *
 * Pourquoi seul le socle est compté dans l'en-tête. Le programme propose cinq à huit
 * items ; un seul ensemble est réellement attendu. Afficher « 1/7 » à quelqu'un qui a
 * fait exactement ce qu'on lui demandait, c'est annoncer un échec là où le contrat
 * annonce une réussite. Le reste est visible en dépliant, jamais compté comme un dû.
 */

/** Ce que chaque ligne du socle ouvre. La saisie passe par `noter`, résolue par le serveur. */
const OPENS: Record<string, LaunchType> = {
  'checkin-quotidien': 'noter',
  'respiration-lente-10': 'breath',
  'journal-libre': 'journal',
}

function dateDuJour(): string {
  const d = new Date()
  const texte = d.toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long' })
  return texte.charAt(0).toUpperCase() + texte.slice(1)
}

export default function Parcours({
  state,
  busy,
  onOpen,
}: {
  state: DayState | null
  busy: boolean
  onOpen: (type: LaunchType, label?: string) => void
}) {
  const [open, setOpen] = useState(false)
  if (!state?.socle) return null
  const { items, fait, total } = state.socle
  const complet = fait >= total

  return (
    <section className={`parcours${open ? ' is-open' : ''}`}>
      <button
        type="button"
        className="parcours-head"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <span className="parcours-title">Mon parcours</span>
        <span className="parcours-date">{dateDuJour()}</span>
        <span className="parcours-count">
          {/* Pas de félicitation quand c'est plein : tenir le socle est la normale,
              pas une performance. Ce qui est dit à la place est utile. */}
          {complet ? 'fait · le reste est libre' : `${fait}/${total}`}
        </span>
        <span className="parcours-chev">
          <Icon name={open ? 'minus' : 'plus'} size={14} />
        </span>
      </button>

      {/* Les trois cases restent visibles repliées : c'est l'information qu'on vient
          chercher vingt fois par jour, et la déplier pour la lire annulerait tout le
          bénéfice de l'avoir remontée ici. */}
      <div className="parcours-cells">
        {items.map((item) => (
          <button
            key={item.slug}
            type="button"
            className={`dayprog-cell${item.fait ? ' is-done' : ''}`}
            disabled={busy}
            title={item.fait ? `${item.label} — fait` : `${item.label} — à faire`}
            onClick={() => onOpen(OPENS[item.slug] ?? 'noter', item.label)}
          >
            {item.label}
          </button>
        ))}
      </div>

      {open && (
        <div className="parcours-body">
          <ProgrammeDuJour busy={busy} onOpen={onOpen} />
        </div>
      )}
    </section>
  )
}
