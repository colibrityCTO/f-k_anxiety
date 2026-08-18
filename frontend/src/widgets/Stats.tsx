import { useEffect, useState } from 'react'
import { GAD7_THRESHOLDS, LineChart } from '../components/Charts'
import WhyBox from '../components/WhyBox'
import type { WidgetProps } from '../components/WidgetHost'
import { api } from '../lib/api'
import type { HistoryPayload } from '../lib/types'

const RANGES = [14, 30, 90]

export default function Stats(_props: WidgetProps) {
  const [days, setDays] = useState(30)
  const [history, setHistory] = useState<HistoryPayload | null>(null)

  useEffect(() => {
    api.history(days).then(setHistory).catch(() => undefined)
  }, [days])

  if (!history) {
    return (
      <div className="w-body">
        <p className="small dim">Chargement de tes chiffres…</p>
      </div>
    )
  }

  const daily = history.quotidien
  const num = (row: Record<string, unknown>, key: string): number | null => {
    const value = row[key]
    if (value === null || value === undefined) return null
    const parsed = Number(value)
    return Number.isNaN(parsed) ? null : parsed
  }

  const anxieties = daily.map((row) => num(row, 'anxiete')).filter((v): v is number => v !== null)
  const last7 = anxieties.slice(-7)
  const previous7 = anxieties.slice(-14, -7)
  const mean = (list: number[]) => (list.length ? list.reduce((a, b) => a + b, 0) / list.length : null)
  const meanRecent = mean(last7)
  const meanPrevious = mean(previous7)
  const delta = meanRecent !== null && meanPrevious !== null ? meanRecent - meanPrevious : null

  const adherence = history.assiduite.reduce(
    (acc, row) => ({ done: acc.done + row.faites, total: acc.total + row.total }),
    { done: 0, total: 0 },
  )

  return (
    <div className="w-body">
      <div className="chips" style={{ marginBottom: 'var(--g2)' }}>
        {RANGES.map((range) => (
          <button key={range} className="chip" aria-pressed={days === range} onClick={() => setDays(range)}>
            {range} jours
          </button>
        ))}
      </div>

      <div className="stats">
        <div className="stat">
          <b>{meanRecent !== null ? meanRecent.toFixed(1) : '—'}</b>
          <span>Anxiété moy. 7 j</span>
        </div>
        <div className="stat">
          <b>{delta !== null ? `${delta > 0 ? '+' : ''}${delta.toFixed(1)}` : '—'}</b>
          <span>vs 7 j précédents</span>
        </div>
        <div className="stat">
          <b>{adherence.total ? `${Math.round((adherence.done / adherence.total) * 100)}%` : '—'}</b>
          <span>Activités faites</span>
        </div>
      </div>

      <LineChart
        title="Anxiété et humeur"
        yLabel="échelle 0-10, un seul axe pour les deux séries"
        series={[
          {
            name: 'Anxiété',
            points: daily.map((row) => ({ label: String(row.entry_date), value: num(row, 'anxiete') })),
          },
          {
            name: 'Humeur',
            dashed: true,
            points: daily.map((row) => ({ label: String(row.entry_date), value: num(row, 'humeur') })),
          },
        ]}
      />

      <div style={{ marginTop: 'var(--g3)' }}>
        <LineChart
          title="Sommeil"
          yLabel="heures par nuit"
          yMin={0}
          yMax={12}
          unit=" h"
          series={[
            {
              name: 'Sommeil',
              points: daily.map((row) => ({ label: String(row.entry_date), value: num(row, 'sommeil_h') })),
            },
          ]}
        />
      </div>

      {history.gad7.length > 0 && (
        <div style={{ marginTop: 'var(--g3)' }}>
          <LineChart
            title="GAD-7"
            yLabel="score sur 21"
            yMin={0}
            yMax={21}
            thresholds={GAD7_THRESHOLDS}
            series={[
              { name: 'GAD-7', points: history.gad7.map((row) => ({ label: row.taken_on, value: row.total })) },
            ]}
          />
        </div>
      )}

      <WhyBox
        label="Comment lire ces courbes"
        mechanism="Aucune couleur : les deux séries se distinguent par le motif du trait (plein / tirets) et par l'étiquette du dernier point. Une seule échelle 0-10 pour les deux, jamais deux axes — c'est la première cause de graphique trompeur. Les seuils du GAD-7 sont tracés en filets, pas en zones colorées."
        evidenceLevel="A"
        sources={[
          {
            label: 'Toussaint et al., J Affect Disord 2020 — une variation de moins de 4 points au GAD-7 est du bruit de mesure',
            url: 'https://pubmed.ncbi.nlm.nih.gov/32090765/',
          },
        ]}
        contraindications="Regarder ses courbes tous les jours peut devenir une forme d'hypervigilance. Une fois par semaine suffit largement."
      />
    </div>
  )
}
