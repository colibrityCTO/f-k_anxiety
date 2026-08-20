import ProgrammeDuJour, { ChiffresDuJour, useProgramDay } from '../components/ProgrammeDuJour'
import type { WidgetProps } from '../components/WidgetHost'

/**
 * Le parcours du jour, en tant que widget du fil. **Plus rien n'en crée.**
 *
 * Il vit désormais sous le titre, en permanence, dans un bandeau qu'on déplie —
 * parce qu'un programme n'est pas un événement mais l'état du jour. Le chercher
 * dans un menu, puis le voir défiler avec le reste du fil, le rendait introuvable
 * deux minutes après l'avoir ouvert.
 *
 * Ce fichier reste pour une seule raison : des items de type `jour` dorment encore
 * dans les fils existants, et le passé ne se réécrit pas. Il rend exactement le
 * même contenu que le bandeau — un seul composant pour les deux, sans quoi les deux
 * finiraient par diverger.
 */
export default function Jour({ busy, onOpen }: WidgetProps) {
  const { day, error } = useProgramDay()
  return (
    <div className="w-body">
      {error && <p className="error-text">{error}</p>}
      {!day && !error && <p className="dim">Chargement…</p>}
      {day && (
        <>
          <ChiffresDuJour day={day} />
          <ProgrammeDuJour day={day} busy={busy} onOpen={onOpen ?? (() => undefined)} />
        </>
      )}
    </div>
  )
}
