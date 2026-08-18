import Icon from './Icon'
import type { ThreadItem, WidgetType } from '../lib/types'
import Account from '../widgets/Account'
import Analysis from '../widgets/Analysis'
import Breath from '../widgets/Breath'
import Checkin from '../widgets/Checkin'
import Echelles from '../widgets/Echelles'
import Exposition from '../widgets/Exposition'
import Interoceptif from '../widgets/Interoceptif'
import Journal from '../widgets/Journal'
import Logout from '../widgets/Logout'
import Meditation from '../widgets/Meditation'
import Memoire from '../widgets/Memoire'
import Rapport from '../widgets/Rapport'
import Sources from '../widgets/Sources'
import Stats from '../widgets/Stats'

export type WidgetProps = {
  item: ThreadItem
  busy: boolean
  onSubmit: (values: Record<string, unknown>) => Promise<void> | void
  onSkip: () => Promise<void> | void
}

const META: Record<WidgetType, { title: string; tag: string }> = {
  checkin: { title: 'Check-in du jour', tag: 'Saisie · 2 min' },
  breath: { title: 'Respiration lente', tag: '5 min · ~6 cycles/min' },
  journal: { title: 'Journal', tag: 'Saisie' },
  gad7: { title: 'GAD-7', tag: 'Mesure · hebdomadaire' },
  echelles: { title: 'Échelles', tag: 'Mesure' },
  exposition: { title: 'Exposition', tag: 'Module 7' },
  interoceptif: { title: 'Sensations', tag: 'Module 6 · intéroceptif' },
  meditation: { title: 'Méditation', tag: 'Pratique guidée' },
  memoire: { title: 'Mémoire', tag: 'Historique complet' },
  rapport: { title: 'Rapport', tag: 'Pour un professionnel' },
  stats: { title: 'Mes chiffres', tag: 'Données' },
  analysis: { title: 'Analyse', tag: 'Période' },
  sources: { title: 'Sources', tag: 'Corpus' },
  account: { title: 'Compte', tag: 'Système' },
  logout: { title: 'Sortir', tag: 'Système' },
}

const BODIES: Record<WidgetType, (props: WidgetProps) => JSX.Element> = {
  checkin: Checkin,
  breath: Breath,
  journal: Journal,
  gad7: Echelles,
  echelles: Echelles,
  exposition: Exposition,
  interoceptif: Interoceptif,
  meditation: Meditation,
  memoire: Memoire,
  rapport: Rapport,
  stats: Stats,
  analysis: Analysis,
  sources: Sources,
  account: Account,
  logout: Logout,
}

/** Récapitulatifs des widgets figés : un widget validé n'affiche plus de contrôles. */
function summarise(item: ThreadItem): { label: string; value: string }[] {
  const saved = item.saved_values ?? {}
  const num = (key: string) => (saved[key] === null || saved[key] === undefined ? null : String(saved[key]))

  switch (item.widget_type) {
    case 'checkin':
      return [
        ['Anxiété', num('anxiety_0_10')],
        ['Humeur', num('mood_0_10')],
        ['Évitement', num('avoidance_0_10')],
        ['Sommeil', num('sleep_hours') ? `${Number(saved.sleep_hours).toFixed(1)} h` : null],
        ['Cafés', num('caffeine_units')],
        ['Paniques', num('panic_attacks')],
      ]
        .filter(([, value]) => value !== null)
        .map(([label, value]) => ({ label: String(label), value: String(value) }))
    case 'gad7':
    case 'echelles':
      return [
        { label: String(saved.instrument ?? 'Score').toUpperCase(), value: String(saved.total ?? '—') },
        { label: 'Sévérité', value: String(saved.severity ?? '—') },
      ]
    case 'exposition':
      // En mode « ajout » il n'y a pas encore de tentative : on n'affiche pas
      // une case vide, on l'omet.
      return [
        { label: 'Item', value: String(saved.label ?? '—') },
        ...(saved.attempts !== undefined && saved.attempts !== null
          ? [{ label: 'Tentatives', value: String(saved.attempts) }]
          : []),
        ...(saved.mastered ? [{ label: 'État', value: 'maîtrisé' }] : []),
      ]
    case 'interoceptif':
      return [
        ...(num('anxiety_before') ? [{ label: 'Anxiété max', value: num('anxiety_before') as string }] : []),
        ...(num('anxiety_after') ? [{ label: 'Après', value: num('anxiety_after') as string }] : []),
      ]
    case 'meditation':
      return [
        { label: 'Durée', value: `${saved.duration_min ?? '—'} min` },
        ...(num('anxiety_before') ? [{ label: 'Avant', value: num('anxiety_before') as string }] : []),
        ...(num('anxiety_after') ? [{ label: 'Après', value: num('anxiety_after') as string }] : []),
      ]
    case 'breath':
      return [
        { label: 'Avant', value: num('anxiety_before') ?? '—' },
        { label: 'Après', value: num('anxiety_after') ?? '—' },
      ]
    case 'journal':
      return [
        { label: 'Format', value: String(saved.kind ?? 'libre') },
        { label: 'Date', value: String(saved.entry_date ?? '') },
      ]
    case 'analysis':
      return [{ label: 'Portée', value: String(saved.scope ?? '—') }]
    default:
      return []
  }
}

export default function WidgetHost({
  item,
  busy,
  onSubmit,
  onSkip,
  onOpen,
  open,
  onToggle,
}: WidgetProps & {
  onOpen: (type: WidgetType, label?: string) => void
  open: boolean
  onToggle: () => void
}) {
  const type = (item.widget_type ?? 'checkin') as WidgetType
  const meta = META[type]
  const frozen =
    item.status === 'valide' || item.status === 'reporte' || item.status === 'remplace'
  const tag = !frozen
    ? meta.tag
    : item.status === 'valide'
      ? 'Enregistré'
      : item.status === 'reporte'
        ? 'Reporté'
        : 'Remplacé'

  /**
   * L'en-tête est l'interrupteur du widget : replié, il ne reste que le titre et
   * son étiquette. Un seul widget est ouvert à la fois — les précédents se
   * referment d'eux-mêmes, et au lancement c'est le dernier du fil qui est ouvert.
   */
  const head = (
    <button type="button" className="w-head w-toggle" aria-expanded={open} onClick={onToggle}>
      <div className="w-title">{meta.title}</div>
      <div className="w-tag">{tag}</div>
      <span className="w-chev">
        <Icon name={open ? 'minus' : 'plus'} size={14} />
      </span>
    </button>
  )

  if (frozen) {
    const cells = item.status === 'valide' ? summarise(item) : []
    return (
      <div className={`w${open ? '' : ' w-shut'}`}>
        {head}
        {open && (
          <>
            {cells.length > 0 && (
              <div className="w-body">
                <div className="sum">
                  {cells.map((cell) => (
                    <div key={cell.label}>
                      <span>{cell.label}</span>
                      <b>{cell.value}</b>
                    </div>
                  ))}
                </div>
              </div>
            )}
            <div className="w-foot">
              <button className="btn-sm" disabled={busy} onClick={() => onOpen(type, meta.title)}>
                {item.status === 'valide' ? 'Corriger' : 'Le faire maintenant'}
              </button>
              <span className="tiny dim">
                {item.status === 'valide'
                  ? 'Figé : « Corriger » en ouvre un neuf, sans réécrire le passé.'
                  : item.status === 'reporte'
                    ? 'Reporté — ce n’est pas un échec, c’est une donnée.'
                    : 'Remplacé par une saisie plus récente.'}
              </span>
            </div>
          </>
        )}
      </div>
    )
  }

  const Body = BODIES[type]
  return (
    <div className={`w${open ? '' : ' w-shut'}`}>
      {head}
      {open && <Body item={item} busy={busy} onSubmit={onSubmit} onSkip={onSkip} />}
    </div>
  )
}
