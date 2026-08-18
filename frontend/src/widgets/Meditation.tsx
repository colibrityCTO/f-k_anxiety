import { useEffect, useRef, useState } from 'react'
import Slider from '../components/Slider'
import WhyBox from '../components/WhyBox'
import type { WidgetProps } from '../components/WidgetHost'

type Practice = {
  slug: string
  name: string
  minutes: number
  steps: string[]
  mechanism: string
  level: string
  sources: { label: string; url?: string }[]
  caution?: string
}

const PRACTICES: Practice[] = [
  {
    slug: 'meditation-souffle',
    name: 'Conscience du souffle',
    minutes: 10,
    steps: [
      "Assis, yeux fermés ou regard bas. L'attention sur la sensation du souffle aux narines.",
      "Quand l'esprit part — il partira, c'est normal — note « pensée » et reviens au souffle.",
      'Ne modifie pas ta respiration : tu ne fais que l\'observer.',
    ],
    mechanism:
      "Entraîne la décentration : voir une pensée anxieuse comme un événement mental passager plutôt que comme une information sur le réel. Réduit aussi le temps passé en rumination tournée vers le futur.",
    level: 'A',
    sources: [
      {
        label: 'Hoge et al., JAMA Psychiatry 2023 — MBSR non inférieur à l\'escitalopram chez l\'adulte avec trouble anxieux',
        url: 'https://jamanetwork.com/journals/jamapsychiatry/fullarticle/2798510',
      },
    ],
  },
  {
    slug: 'scan-corporel',
    name: 'Scan corporel',
    minutes: 20,
    steps: [
      'Allongé ou assis, parcours le corps des pieds à la tête, zone par zone.',
      'Sur chaque zone : quelles sensations exactement ? température, pression, picotement, rien ?',
      'Sur une zone tendue ou désagréable : reste 3 respirations sans chercher à la relâcher.',
      'Termine par la sensation du corps entier.',
    ],
    mechanism:
      "Réduit l'évitement expérientiel : rester avec une sensation désagréable sans fuir désactive progressivement le réflexe d'évitement. C'est aussi la préparation directe à l'exposition intéroceptive.",
    level: 'A',
    sources: [
      {
        label: 'Hoge et al., JAMA Psychiatry 2023 — essai TAME',
        url: 'https://jamanetwork.com/journals/jamapsychiatry/fullarticle/2798510',
      },
    ],
    caution:
      "Peut faire monter l'anxiété au début en cas de forte anxiété somatique : c'est fréquent et transitoire. Raccourcis la séance plutôt que d'arrêter. En cas d'antécédent de traumatisme, préfère un ancrage externe (sons, contact des pieds au sol).",
  },
  {
    slug: 'conscience-emotionnelle',
    name: 'Conscience émotionnelle',
    minutes: 12,
    steps: [
      "3 minutes d'ancrage sur le souffle et le contact du corps.",
      "Repère l'émotion présente. Nomme-la en un mot.",
      'Balaye : quelles pensées ? quelles sensations, et où exactement ? quelle envie d\'agir ?',
      'À chaque jugement ou projection dans le futur, note « jugement » / « futur » et reviens au corps.',
    ],
    mechanism:
      "Module 3 du Protocole Unifié. Cible les deux dérives qui entretiennent l'anxiété : juger l'émotion (ce qui ajoute de la honte à la peur) et la projeter dans le futur. C'est le prérequis des expositions : on ne s'expose pas à ce qu'on ne sait pas observer.",
    level: 'B',
    sources: [
      {
        label: 'Barlow & Farchione, World Psychiatry 2020 — Protocole Unifié, module 3',
        url: 'https://onlinelibrary.wiley.com/doi/10.1002/wps.20748',
      },
    ],
  },
  {
    slug: 'relaxation-musculaire',
    name: 'Relaxation musculaire',
    minutes: 15,
    steps: [
      'Contracte un groupe musculaire 5 secondes (mains, avant-bras, épaules, visage, ventre, jambes, pieds).',
      'Relâche brutalement et observe la différence pendant 15 secondes.',
      'Enchaîne les groupes du bas vers le haut.',
    ],
    mechanism:
      "Réduit la tension musculaire — composante somatique majeure de l'anxiété généralisée — et développe une compétence de discrimination : percevoir la montée de tension assez tôt pour intervenir.",
    level: 'A',
    sources: [
      {
        label: "NICE CG113 — la relaxation appliquée est recommandée à égalité avec la TCC pour l'anxiété généralisée",
        url: 'https://www.nice.org.uk/guidance/cg113/chapter/Recommendations',
      },
    ],
    caution: 'Ne contracte pas une zone blessée ou douloureuse : passe-la.',
  },
]

export default function Meditation({ busy, onSubmit, onSkip }: WidgetProps) {
  const [practice, setPractice] = useState(PRACTICES[0])
  const [before, setBefore] = useState(5)
  const [after, setAfter] = useState(5)
  const [remaining, setRemaining] = useState(PRACTICES[0].minutes * 60)
  const [running, setRunning] = useState(false)
  const timer = useRef<number | null>(null)

  useEffect(() => {
    setRemaining(practice.minutes * 60)
    setRunning(false)
  }, [practice])

  useEffect(() => {
    if (!running) return
    timer.current = window.setInterval(() => {
      setRemaining((value) => {
        if (value <= 1) {
          setRunning(false)
          return 0
        }
        return value - 1
      })
    }, 1000)
    return () => {
      if (timer.current !== null) window.clearInterval(timer.current)
    }
  }, [running])

  const elapsed = practice.minutes * 60 - remaining

  return (
    <>
      <div className="w-body">
        <div className="chips" style={{ marginBottom: 'var(--g3)' }}>
          {PRACTICES.map((option) => (
            <button
              key={option.slug}
              className="chip"
              aria-pressed={practice.slug === option.slug}
              onClick={() => setPractice(option)}
            >
              {option.name} · {option.minutes} min
            </button>
          ))}
        </div>

        <Slider label="Anxiété avant" value={before} onChange={setBefore} />

        <div style={{ textAlign: 'center', marginTop: 'var(--g3)' }}>
          <div style={{ fontFamily: 'var(--display)', fontSize: '3.5rem', lineHeight: 1, fontVariantNumeric: 'tabular-nums' }}>
            {Math.floor(remaining / 60)}:{String(remaining % 60).padStart(2, '0')}
          </div>
          <div
            style={{ height: 4, background: 'transparent', border: '1px solid currentColor', margin: 'var(--g2) 0' }}
          >
            <div
              style={{
                height: '100%',
                width: `${Math.min(100, (elapsed / (practice.minutes * 60)) * 100)}%`,
                background: 'currentColor',
              }}
            />
          </div>
          <div className="btn-row" style={{ justifyContent: 'center' }}>
            <button className="btn-primary" onClick={() => setRunning((value) => !value)}>
              {running ? 'Pause' : elapsed > 0 ? 'Reprendre' : 'Commencer'}
            </button>
            <button
              onClick={() => {
                setRunning(false)
                setRemaining(practice.minutes * 60)
              }}
            >
              Remettre à zéro
            </button>
          </div>
        </div>

        <ol className="md" style={{ paddingLeft: '1.2rem', marginTop: 'var(--g3)' }}>
          {practice.steps.map((step, index) => (
            <li key={index} style={{ marginBottom: 6 }}>
              {step}
            </li>
          ))}
        </ol>

        {elapsed > 60 && <Slider label="Anxiété après" value={after} onChange={setAfter} />}

        <WhyBox
          mechanism={practice.mechanism}
          evidenceLevel={practice.level}
          sources={practice.sources}
          contraindications={practice.caution}
        />
      </div>

      <div className="w-foot">
        <button
          className="btn-primary"
          disabled={busy || elapsed < 30}
          onClick={() =>
            onSubmit({
              slug: practice.slug,
              duration_min: Math.round(elapsed / 60),
              anxiety_before: before,
              anxiety_after: elapsed > 60 ? after : null,
              status: elapsed >= practice.minutes * 60 * 0.8 ? 'fait' : 'partiel',
            })
          }
        >
          Terminer
        </button>
        <button className="btn-sm" disabled={busy} onClick={onSkip}>
          Pas maintenant
        </button>
        {elapsed < 30 && <span className="tiny dim">Lance la séance d'abord.</span>}
      </div>
    </>
  )
}
