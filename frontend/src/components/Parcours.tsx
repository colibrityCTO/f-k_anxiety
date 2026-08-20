import { useState } from 'react'
import Icon from './Icon'
import ProgrammeDuJour, { ChiffresDuJour, useProgramDay } from './ProgrammeDuJour'
import type { LaunchType } from '../lib/types'

/**
 * Le bandeau du jour, sous le titre, toujours là.
 *
 * Ce qu'il montre en permanence : la date et **les cinq chiffres**. C'est la donnée
 * qu'on garde sous les yeux — le socle du jour, ce qui a été fait en plus, les jours
 * d'affilée, les jours réellement pratiqués et l'assiduité. Elle était sous la ligne
 * de flottaison, dans un panneau qu'il fallait déplier : la seule information qui
 * mérite d'être permanente était la seule qu'il fallait aller chercher.
 *
 * Ce qu'il cache jusqu'au clic : le texte. Le module de la semaine, les notices, la
 * liste des activités et leurs justifications. C'est long, ça se lit une fois, et ça
 * peut défiler.
 *
 * D'où la séparation stricte des deux zones dans la mise en page : les chiffres sont
 * hors du conteneur défilant. On peut parcourir toute la liste des activités sans
 * jamais perdre de vue où on en est — c'est tout l'intérêt de les avoir remontés.
 *
 * Pourquoi ce n'est plus un widget du fil : un programme est l'état du jour, pas un
 * événement. Déposé dans un fil chronologique, il défilait avec le reste, et
 * l'information la plus consultée devenait la plus difficile à retrouver.
 */
function dateDuJour(): string {
  const d = new Date()
  const texte = d.toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long' })
  return texte.charAt(0).toUpperCase() + texte.slice(1)
}

export default function Parcours({
  busy,
  onOpen,
}: {
  busy: boolean
  onOpen: (type: LaunchType, label?: string) => void
}) {
  const [open, setOpen] = useState(false)
  const { day, error } = useProgramDay()

  // Rien tant que le programme n'est pas là : une carcasse vide sous le titre, en
  // attente, coûte plus qu'elle n'apporte. En cas d'échec on le dit, sans bloquer
  // le fil qui, lui, fonctionne.
  if (error) {
    return (
      <section className="parcours">
        <p className="tiny dim" style={{ margin: 0 }}>
          Programme du jour indisponible.
        </p>
      </section>
    )
  }
  if (!day) return null

  return (
    <section className="parcours">
      <button
        type="button"
        className="parcours-head"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <span className="parcours-title">Mon parcours</span>
        <span className="parcours-date">{dateDuJour()}</span>
        <span className="parcours-chev">
          <Icon name={open ? 'minus' : 'plus'} size={14} />
        </span>
      </button>

      {/* Hors du conteneur défilant, volontairement. */}
      <ChiffresDuJour day={day} />

      {open && (
        <div className="parcours-body">
          <ProgrammeDuJour day={day} busy={busy} onOpen={onOpen} />
        </div>
      )}
    </section>
  )
}
