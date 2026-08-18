import { useEffect, useState } from 'react'
import WhyBox from '../components/WhyBox'
import type { WidgetProps } from '../components/WidgetHost'
import { api } from '../lib/api'
import type { Instrument } from '../lib/types'

/**
 * Les trois échelles, un seul widget. Le GAD-7 mesure l'inquiétude et la tension,
 * le PHQ-2 dépiste la dépression associée, l'échelle d'évitement suit le
 * mécanisme que le GAD-7 ne capte pas.
 */
export default function Echelles({ item, busy, onSubmit, onSkip }: WidgetProps) {
  const forced = item.widget_type === 'gad7' ? 'gad7' : null
  const [instruments, setInstruments] = useState<Instrument[]>([])
  const [active, setActive] = useState<string>(forced ?? 'gad7')
  const [answers, setAnswers] = useState<Record<number, number>>({})

  useEffect(() => {
    api
      .instruments()
      .then((data) => setInstruments(data.instruments))
      .catch(() => undefined)
  }, [])

  const instrument = instruments.find((row) => row.instrument === active) ?? null

  if (!instrument) {
    return (
      <div className="w-body">
        <p className="small dim">Chargement des échelles…</p>
      </div>
    )
  }

  const answered = Object.keys(answers).length
  const complete = answered === instrument.items.length

  return (
    <>
      <div className="w-body">
        {!forced && instruments.length > 1 && (
          <div className="chips" style={{ marginBottom: 'var(--g3)' }}>
            {instruments.map((row) => (
              <button
                key={row.instrument}
                className="chip"
                aria-pressed={active === row.instrument}
                onClick={() => {
                  setActive(row.instrument)
                  setAnswers({})
                }}
              >
                {row.title}
              </button>
            ))}
          </div>
        )}

        <p className="small dim">{instrument.prompt}</p>
        {instrument.items.map((question, index) => (
          <div className="q" key={`${instrument.instrument}-${index}`}>
            <div className="txt">
              {index + 1}. {question}
            </div>
            <div className="opts">
              {instrument.options.map((option) => (
                <button
                  key={option.value}
                  className="opt"
                  aria-pressed={answers[index] === option.value}
                  onClick={() => setAnswers((current) => ({ ...current, [index]: option.value }))}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>
        ))}

        <WhyBox
          mechanism={instrument.explanation}
          evidenceLevel={instrument.instrument === 'avoidance' ? 'C' : 'A'}
          sources={instrument.sources}
          contraindications={instrument.limits}
        />
      </div>

      <div className="w-foot">
        <button
          className="btn-primary"
          disabled={busy || !complete}
          onClick={() =>
            onSubmit({
              instrument: instrument.instrument,
              items: instrument.items.map((_, index) => answers[index] ?? 0),
            })
          }
        >
          Valider
        </button>
        <button className="btn-sm" disabled={busy} onClick={onSkip}>
          Pas maintenant
        </button>
        <span className="tiny dim">
          {answered} / {instrument.items.length} répondu
        </span>
      </div>
    </>
  )
}
