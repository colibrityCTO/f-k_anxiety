import { useEffect, useState } from 'react'
import WhyBox from '../components/WhyBox'
import type { WidgetProps } from '../components/WidgetHost'
import { api } from '../lib/api'
import type { MemoryRow, MemoryStats } from '../lib/types'

const LABELS: Record<string, string> = {
  checkin: 'Check-in',
  journal: 'Journal',
  assessment: 'Échelle',
  activity: 'Activité',
  message: 'Conversation',
  insight: 'Analyse',
}

const SUGGESTIONS = [
  'crise dans le métro',
  'nuits courtes',
  "ce que j'ai appris",
  'réunion au travail',
]

/**
 * Recherche dans son propre historique. Exposé volontairement : tu dois pouvoir
 * vérifier ce qui est stocké à ton sujet, et ce qu'une requête y retrouve.
 */
export default function Memoire(_props: WidgetProps) {
  const [stats, setStats] = useState<MemoryStats | null>(null)
  const [rows, setRows] = useState<MemoryRow[] | null>(null)
  const [query, setQuery] = useState('')
  const [busy, setBusy] = useState(false)
  const [mode, setMode] = useState<string | null>(null)

  useEffect(() => {
    api
      .memory()
      .then((data) => {
        setStats(data.stats)
        setRows(data.recents ?? [])
      })
      .catch(() => undefined)
  }, [])

  async function search(text: string) {
    const value = text.trim()
    if (value.length < 2) return
    setBusy(true)
    try {
      const data = await api.memory(value)
      setStats(data.stats)
      setRows(data.resultats ?? [])
      setMode(data.resultats?.[0]?.mode ?? 'aucun résultat')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="w-body">
      <div className="field">
        <label htmlFor="mem-q">Chercher dans mon historique</label>
        <input
          id="mem-q"
          value={query}
          placeholder="crise dans le métro, nuits courtes, ce que j'ai appris…"
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') search(query)
          }}
        />
      </div>
      <div className="chips" style={{ marginBottom: 'var(--g2)' }}>
        {SUGGESTIONS.map((text) => (
          <button
            key={text}
            className="chip"
            disabled={busy}
            onClick={() => {
              setQuery(text)
              search(text)
            }}
          >
            {text}
          </button>
        ))}
      </div>

      {stats && (
        <p className="tiny dim">
          <strong>{stats.total}</strong> souvenir(s) conservé(s), dont{' '}
          <strong>{stats.vectorises}</strong> vectorisé(s) —{' '}
          {stats.par_source.map((row) => `${LABELS[row.source_kind] ?? row.source_kind} ${row.n}`).join(' · ')}
          {mode ? ` · recherche ${mode}` : ''}
        </p>
      )}

      <div className="divider" />

      {rows === null && <p className="small dim">Chargement…</p>}
      {rows !== null && rows.length === 0 && (
        <p className="small dim">Rien trouvé. Ton historique se remplira à mesure que tu l'utilises.</p>
      )}
      <ul className="list-reset">
        {(rows ?? []).map((row, index) => (
          <li key={index} style={{ borderBottom: '1px solid rgba(0,0,0,.35)', padding: '10px 0' }}>
            <p className="tiny dim" style={{ marginBottom: 2 }}>
              {LABELS[row.source_kind] ?? row.source_kind} · {row.entry_date ?? 'sans date'}
            </p>
            <p className="small" style={{ marginBottom: 0 }}>
              {row.content}
            </p>
          </li>
        ))}
      </ul>

      <WhyBox
        label="Comment cette mémoire fonctionne"
        mechanism="Chaque check-in, entrée de journal, échelle, activité, message et analyse est rendu en texte, embeddé et conservé définitivement — sans fenêtre glissante. La recherche est hybride : similarité vectorielle et plein texte, fusionnés par rangs réciproques. Les chiffres, eux, ne passent pas par ici : ils sont recalculés exactement sur l'historique entier, parce qu'une moyenne ne doit pas dépendre de ce qu'une recherche a bien voulu remonter."
        evidenceLevel="A"
        sources={[
          {
            label: "Linardon et al., World Psychiatry 2024 — le suivi longitudinal est associé aux effets les plus importants",
            url: 'https://onlinelibrary.wiley.com/doi/full/10.1002/wps.21183',
          },
        ]}
        contraindications="Relire ses pires journées en boucle peut nourrir la rumination. Cette recherche sert à retrouver ce que tu as appris, pas à ressasser ce que tu as subi."
      />
    </div>
  )
}
