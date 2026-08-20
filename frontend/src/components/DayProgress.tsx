import type { DayState, LaunchType } from '../lib/types'

/**
 * Le contrat du jour, en haut, tout le temps.
 *
 * Ce qui a été tranché ici, et qui explique pourquoi la barre est si courte : elle
 * ne compte **que le socle** — noter, respirer, écrire. Le programme calcule chaque
 * jour cinq à huit items, mais un seul de ces ensembles est réellement attendu.
 * « Mon parcours » affichait `fait / total` sur l'ensemble tout en écrivant deux
 * écrans plus bas qu'un seul item était attendu : quelqu'un qui avait fait
 * exactement ce qu'on lui demandait lisait « 1/7 ». La barre annonçait un échec
 * pendant que le contrat annonçait une réussite.
 *
 * Trois cases, donc, et pas de série à préserver — `ROADMAP.md` écarte
 * explicitement toute mécanique de suite ininterrompue, parce qu'un compteur qui se
 * remet à zéro punit exactement le jour où c'était le plus dur. Ce qu'on affiche est
 * l'état d'aujourd'hui, et rien de ce qu'il faudrait « ne pas casser ».
 *
 * Chaque case est cliquable : une barre de progression qui ne mène pas à ce qu'elle
 * mesure n'est qu'un reproche.
 */

/** Ce que chaque ligne du socle ouvre. La saisie passe par `noter`, résolue par le serveur. */
const OPENS: Record<string, LaunchType> = {
  'checkin-quotidien': 'noter',
  'respiration-lente-10': 'breath',
  'journal-libre': 'journal',
}

export default function DayProgress({
  state,
  busy,
  onOpen,
}: {
  state: DayState | null
  busy: boolean
  onOpen: (type: LaunchType, label?: string) => void
}) {
  if (!state?.socle) return null
  const { items, fait, total } = state.socle
  const complet = fait >= total

  return (
    <div className="dayprog" aria-label={`Aujourd'hui : ${fait} sur ${total}`}>
      <div className="dayprog-cells">
        {items.map((item) => (
          <button
            key={item.slug}
            type="button"
            className={`dayprog-cell${item.fait ? ' is-done' : ''}`}
            disabled={busy}
            title={item.fait ? `${item.label} — fait` : `${item.label} — à faire`}
            onClick={() => onOpen(OPENS[item.slug] ?? 'jour', item.label)}
          >
            {item.label}
          </button>
        ))}
      </div>
      <span className="dayprog-count">
        {complet ? (
          /* Pas de félicitation : le socle tenu est la normale, pas une performance.
             Ce qui est dit à la place est utile — le reste existe et reste ouvert. */
          <>fait · le reste est libre</>
        ) : (
          <>
            {fait}/{total}
          </>
        )}
      </span>
    </div>
  )
}
