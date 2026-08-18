import { useEffect, useRef, useState } from 'react'
import Slider from '../components/Slider'
import WhyBox from '../components/WhyBox'
import type { WidgetProps } from '../components/WidgetHost'

const CYCLE = 10 // secondes : 5 s d'inspiration, 5 s d'expiration → 6 cycles/min
const TOTAL = 5 * 60

export default function Breath({ busy, onSubmit, onSkip }: WidgetProps) {
  const [before, setBefore] = useState(5)
  const [after, setAfter] = useState(5)
  const [elapsed, setElapsed] = useState(0)
  const [running, setRunning] = useState(false)
  const timer = useRef<number | null>(null)

  useEffect(() => {
    if (!running) return
    timer.current = window.setInterval(() => {
      setElapsed((value) => {
        if (value + 1 >= TOTAL) {
          setRunning(false)
          return TOTAL
        }
        return value + 1
      })
    }, 1000)
    return () => {
      if (timer.current !== null) window.clearInterval(timer.current)
    }
  }, [running])

  const position = elapsed % CYCLE
  const inhaling = position < CYCLE / 2
  const remaining = inhaling ? CYCLE / 2 - position : CYCLE - position
  const progress = inhaling ? position / (CYCLE / 2) : (position - CYCLE / 2) / (CYCLE / 2)
  const scale = inhaling ? 1 + 0.5 * progress : 1.5 - 0.5 * progress
  const left = TOTAL - elapsed
  const cycles = Math.floor(elapsed / CYCLE)

  return (
    <>
      <div className="w-body">
        <Slider label="Anxiété avant" value={before} onChange={setBefore} />

        <div className="breath" style={{ marginTop: 'var(--g2)' }}>
          <div
            className={`sq${running && !inhaling ? ' sq-full' : ''}`}
            style={{ transform: `scale(${scale.toFixed(3)})` }}
          >
            {running ? Math.ceil(remaining) || 5 : '—'}
          </div>
        </div>
        <p className="phase">
          {running ? (inhaling ? 'Inspire par le nez' : 'Expire sans forcer') : elapsed >= TOTAL ? 'Terminé' : 'Prêt quand tu veux'}
        </p>
        <p className="bmeta">
          {String(Math.floor(left / 60)).padStart(2, '0')}:{String(left % 60).padStart(2, '0')} restant ·{' '}
          {cycles} cycle{cycles > 1 ? 's' : ''} · 6 cycles/min
        </p>
        <div className="btn-row" style={{ justifyContent: 'center' }}>
          <button className="btn-primary" onClick={() => setRunning((value) => !value)}>
            {running ? 'Pause' : elapsed > 0 ? 'Reprendre' : 'Commencer'}
          </button>
          <button
            onClick={() => {
              setRunning(false)
              setElapsed(0)
            }}
          >
            Remettre à zéro
          </button>
        </div>

        {elapsed > 30 && (
          <div style={{ marginTop: 'var(--g3)' }}>
            <Slider label="Anxiété après" value={after} onChange={setAfter} />
          </div>
        )}

        <WhyBox
          mechanism="À ~6 cycles par minute (0,1 Hz), la respiration entre en résonance avec la boucle du baroréflexe : l'amplitude des variations du rythme cardiaque augmente et les indices d'activité vagale (RMSSD) montent. L'expiration est la phase active — c'est là que l'influence parasympathique sur le cœur est maximale."
          evidenceLevel="A"
          sources={[
            {
              label:
                'Laborde et al., Neuroscience & Biobehavioral Reviews 2022 — méta-analyse : respiration lente et variabilité de la fréquence cardiaque',
              url: 'https://www.sciencedirect.com/science/article/abs/pii/S0149763422002007',
            },
            {
              label: "Laborde et al. 2021 — dose-réponse d'une séance à 6 cycles/min sur l'activité vagale",
              url: 'https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8656666/',
            },
          ]}
          contraindications="À pratiquer à froid, en entraînement quotidien. Si tu fais des attaques de panique, ne l'utilise pas comme bouée de sauvetage en pleine crise : ça deviendrait un comportement de sécurité et ça bloquerait l'apprentissage — que les sensations redescendent seules."
        />
      </div>

      <div className="w-foot">
        <button
          className="btn-primary"
          disabled={busy}
          onClick={() =>
            onSubmit({
              anxiety_before: before,
              anxiety_after: elapsed > 30 ? after : null,
              duration_min: Math.round(elapsed / 60),
              status: elapsed >= TOTAL * 0.8 ? 'fait' : 'partiel',
            })
          }
        >
          Terminer
        </button>
        <button className="btn-sm" disabled={busy} onClick={onSkip}>
          Pas maintenant
        </button>
      </div>
    </>
  )
}
