import { useEffect, useRef, useState } from 'react'
import Slider from '../components/Slider'
import WhyBox from '../components/WhyBox'
import type { WidgetProps } from '../components/WidgetHost'

/**
 * Trois protocoles nommés, avec leur niveau de preuve. Les deux derniers viennent du
 * programme 12 semaines : quelqu'un qui l'a suivi cherche ces noms-là.
 *
 * L'ordre n'est pas neutre. La respiration de résonance à ~6 cycles/min est en tête
 * parce que c'est celle que la méta-analyse soutient. Le box breathing est en dernier
 * parce que l'essai randomisé de référence l'a trouvé **moins efficace** que le soupir
 * cyclique sur l'humeur — le proposer sans le dire aurait été trompeur.
 */
const PATTERNS = [
  {
    key: 'resonance',
    name: 'Résonance ~6 c/min',
    inhale: 5,
    hold: 0,
    exhale: 5,
    holdAfter: 0,
    evidence: 'B',
    note:
      'Cinq secondes à l’inspiration, cinq à l’expiration. C’est le rythme que la ' +
      'méta-analyse de Laborde soutient pour l’effet sur le tonus vagal — un effet ' +
      'd’entraînement, qui se construit sur des semaines.',
  },
  {
    key: 'diaphragmatique',
    name: 'Diaphragmatique 4-4-6',
    inhale: 4,
    hold: 4,
    exhale: 6,
    holdAfter: 0,
    evidence: 'C',
    note:
      'Le protocole des semaines 1-2 du programme 12 semaines. L’expiration plus longue ' +
      'que l’inspiration est ce qui compte ; l’apnée de quatre secondes, elle, n’est pas ' +
      'soutenue par un essai propre.',
  },
  {
    key: 'box',
    name: 'Box breathing 4-4-4-4',
    inhale: 4,
    hold: 4,
    exhale: 4,
    holdAfter: 4,
    evidence: 'C',
    note:
      'Quatre temps égaux. À savoir avant de le choisir : dans l’essai randomisé de ' +
      'Balban (2023), le soupir cyclique — à expiration allongée — a fait **mieux** que ' +
      'le box breathing sur l’humeur et la fréquence respiratoire.',
  },
] as const

const TOTAL = 5 * 60

export default function Breath({ busy, onSubmit, onSkip }: WidgetProps) {
  const [before, setBefore] = useState(5)
  const [after, setAfter] = useState(5)
  // Le type doit être l'union des trois, pas le premier : `as const` fige sinon
  // l'état sur la résonance et refuse les deux autres.
  const [pattern, setPattern] = useState<(typeof PATTERNS)[number]>(PATTERNS[0])
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

  /**
   * Quatre phases possibles, dont deux peuvent durer zéro seconde. Le calcul est
   * générique plutôt que codé pour un rythme unique : c'est ce qui permet de proposer
   * trois protocoles sans trois implémentations.
   */
  const CYCLE = pattern.inhale + pattern.hold + pattern.exhale + pattern.holdAfter
  const position = elapsed % CYCLE
  const phase =
    position < pattern.inhale
      ? 'inspire'
      : position < pattern.inhale + pattern.hold
        ? 'retiens'
        : position < pattern.inhale + pattern.hold + pattern.exhale
          ? 'expire'
          : 'poumons vides'
  const remaining =
    phase === 'inspire'
      ? pattern.inhale - position
      : phase === 'retiens'
        ? pattern.inhale + pattern.hold - position
        : phase === 'expire'
          ? pattern.inhale + pattern.hold + pattern.exhale - position
          : CYCLE - position
  const inhaling = phase === 'inspire'
  // L'orbe reste grande pendant l'apnée haute et petite pendant l'apnée basse : elle
  // représente le volume pulmonaire, pas la phase.
  const scale =
    phase === 'inspire'
      ? 1 + 0.5 * (position / pattern.inhale)
      : phase === 'retiens'
        ? 1.5
        : phase === 'expire'
          ? 1.5 - 0.5 * ((position - pattern.inhale - pattern.hold) / pattern.exhale)
          : 1
  const left = TOTAL - elapsed
  const cycles = Math.floor(elapsed / CYCLE)

  return (
    <>
      <div className="w-body">
        <Slider label="Anxiété avant" value={before} onChange={setBefore} />

        {/* Le choix du protocole, avec son niveau de preuve visible sur la puce. Le
            changer en cours de séance remet le compteur à zéro — un cycle à moitié
            fait dans un rythme et terminé dans un autre ne veut rien dire. */}
        <div className="field" style={{ marginTop: 'var(--g2)' }}>
          <label style={{ marginBottom: 'var(--g1)' }}>
            Le rythme<span className="hint">Le premier est celui que la preuve soutient</span>
          </label>
          <div className="chips">
            {PATTERNS.map((item) => (
              <button
                key={item.key}
                className={`chip${pattern.key === item.key ? ' on' : ''}`}
                onClick={() => {
                  setPattern(item)
                  setElapsed(0)
                  setRunning(false)
                }}
              >
                {item.name} · {item.evidence}
              </button>
            ))}
          </div>
          <p className="tiny dim">{pattern.note}</p>
        </div>

        <div className="breath" style={{ marginTop: 'var(--g2)' }}>
          <div
            className={`sq${running && !inhaling ? ' sq-full' : ''}`}
            style={{ transform: `scale(${scale.toFixed(3)})` }}
          >
            {running ? Math.ceil(remaining) || pattern.inhale : '—'}
          </div>
        </div>
        <p className="phase">
          {running
            ? {
                inspire: 'Inspire par le nez',
                retiens: 'Retiens, poumons pleins',
                expire: 'Expire sans forcer',
                'poumons vides': 'Retiens, poumons vides',
              }[phase]
            : elapsed >= TOTAL
              ? 'Terminé'
              : 'Prêt quand tu veux'}
        </p>
        <p className="bmeta">
          {String(Math.floor(left / 60)).padStart(2, '0')}:{String(left % 60).padStart(2, '0')} restant ·{' '}
          {cycles} cycle{cycles > 1 ? 's' : ''} · {Math.round(600 / CYCLE) / 10} cycles/min
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
