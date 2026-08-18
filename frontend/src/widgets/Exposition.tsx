import { useEffect, useState } from 'react'
import Slider from '../components/Slider'
import WhyBox from '../components/WhyBox'
import type { WidgetProps } from '../components/WidgetHost'
import { api } from '../lib/api'
import type { ExposureItem } from '../lib/types'

const KINDS: [ExposureItem['kind'], string][] = [
  ['in_vivo', 'Situation réelle'],
  ['interoceptif', 'Sensation physique'],
  ['imaginaire', 'Scénario imaginé'],
]

const WHY = {
  mechanism:
    "Ce n'est pas la baisse d'anxiété pendant l'exposition qui prédit le bénéfice, mais la violation d'attente : l'écart entre ce que tu prédisais et ce qui est arrivé. On ne désapprend pas la peur, on construit en parallèle un apprentissage concurrent — « je peux gérer ça » — qu'il faut ensuite rendre récupérable dans un maximum de contextes. D'où la répétition du même item en variant lieu, heure et personnes.",
  sources: [
    {
      label: 'Craske et al., Behaviour Research and Therapy 2014 — Maximizing exposure therapy: an inhibitory learning approach',
      url: 'https://pubmed.ncbi.nlm.nih.gov/24864005/',
    },
    {
      label: 'Craske et al., 2022 — OptEx Nexus, approche par récupération inhibitrice',
      url: 'https://pubmed.ncbi.nlm.nih.gov/35325683/',
    },
  ],
  contraindications:
    "Ce n'est pas une épreuve de force. Si tu quittes la situation en panique en concluant « je n'y arriverai jamais », l'item était trop haut : redescends. En cas de trouble sévère, d'antécédent traumatique ou d'idées suicidaires, l'exposition se fait accompagnée par un professionnel.",
}

export default function Exposition({ item, busy, onSubmit, onSkip }: WidgetProps) {
  const [items, setItems] = useState<ExposureItem[]>([])
  const [mode, setMode] = useState<'attempt' | 'add'>('attempt')
  const [selected, setSelected] = useState<string | null>(null)

  // Ajout d'un item
  const [label, setLabel] = useState('')
  const [kind, setKind] = useState<ExposureItem['kind']>('in_vivo')
  const [anticipated, setAnticipated] = useState(5)
  const [safety, setSafety] = useState('')

  // Tentative
  const [prediction, setPrediction] = useState('')
  const [probability, setProbability] = useState(70)
  const [outcome, setOutcome] = useState('')
  const [learning, setLearning] = useState('')
  const [anxietyMax, setAnxietyMax] = useState(7)
  const [anxietyAfter, setAnxietyAfter] = useState(4)
  const [dropped, setDropped] = useState('')
  const [mastered, setMastered] = useState(false)

  useEffect(() => {
    api
      .exposures()
      .then((rows) => {
        setItems(rows)
        const open = rows.filter((row) => !row.mastered)
        if (open.length === 0) setMode('add')
        else {
          // Suggestion : le plus bas item entre 4 et 6, sinon le plus bas ouvert.
          const zone = open.filter((row) => (row.anticipated_anxiety ?? 0) >= 4 && (row.anticipated_anxiety ?? 0) <= 6)
          setSelected((zone[0] ?? open[0]).id)
        }
      })
      .catch(() => setMode('add'))
  }, [])

  const open = items.filter((row) => !row.mastered)
  const current = open.find((row) => row.id === selected) ?? null
  const prefillLabel = String((item.payload?.prefill as Record<string, unknown>)?.situation ?? '')

  return (
    <>
      <div className="w-body">
        <div className="chips" style={{ marginBottom: 'var(--g3)' }}>
          <button
            className="chip"
            aria-pressed={mode === 'attempt'}
            disabled={open.length === 0}
            onClick={() => setMode('attempt')}
          >
            J'ai tenté
          </button>
          <button className="chip" aria-pressed={mode === 'add'} onClick={() => setMode('add')}>
            Ajouter un item
          </button>
        </div>

        {mode === 'add' ? (
          <>
            <div className="field">
              <label htmlFor="expo-label">Ce que tu évites</label>
              <input
                id="expo-label"
                value={label || prefillLabel}
                placeholder="Prendre le métro à l'heure de pointe, téléphoner à un inconnu, boire un café serré…"
                onChange={(event) => setLabel(event.target.value)}
              />
            </div>
            <div className="field">
              <label>Type</label>
              <div className="chips">
                {KINDS.map(([value, text]) => (
                  <button key={value} className="chip" aria-pressed={kind === value} onClick={() => setKind(value)}>
                    {text}
                  </button>
                ))}
              </div>
            </div>
            <Slider
              label="Anxiété anticipée"
              value={anticipated}
              onChange={setAnticipated}
              lowLabel="rien"
              highLabel="insoutenable"
              note="On commence entre 4 et 6 : plus bas n'apprend rien, plus haut fait fuir."
            />
            <div className="field" style={{ marginBottom: 0 }}>
              <label htmlFor="expo-safety">
                Comportements de sécurité associés<span className="hint">Séparés par des virgules</span>
              </label>
              <input
                id="expo-safety"
                value={safety}
                placeholder="être accompagné, rester près de la sortie, garder mon téléphone en main"
                onChange={(event) => setSafety(event.target.value)}
              />
            </div>
          </>
        ) : (
          <>
            <div className="field">
              <label>Quel item ?</label>
              <div className="chips">
                {open.map((row) => (
                  <button
                    key={row.id}
                    className="chip"
                    aria-pressed={selected === row.id}
                    onClick={() => setSelected(row.id)}
                  >
                    {row.label} · {row.anticipated_anxiety ?? '—'}/10
                    {row.attempts > 0 ? ` · ${row.attempts}×` : ''}
                  </button>
                ))}
              </div>
              {current && current.safety_behaviors.length > 0 && (
                <p className="tiny dim" style={{ marginTop: 6 }}>
                  À retirer cette fois : {current.safety_behaviors.join(', ')}
                </p>
              )}
            </div>

            <div className="field">
              <label htmlFor="expo-pred">
                Ta prédiction, écrite <strong>avant</strong>
              </label>
              <textarea
                id="expo-pred"
                value={prediction}
                placeholder="« Je vais faire une crise et devoir sortir à la station suivante. »"
                onChange={(event) => setPrediction(event.target.value)}
              />
            </div>
            <Slider
              label="Probabilité que tu donnais"
              value={probability}
              onChange={setProbability}
              max={100}
              lowLabel="impossible"
              highLabel="certain"
              suffix=" %"
            />
            <Slider label="Anxiété maximale pendant" value={anxietyMax} onChange={setAnxietyMax} />
            <div className="field">
              <label htmlFor="expo-out">Ce qui s'est réellement passé</label>
              <textarea
                id="expo-out"
                value={outcome}
                onChange={(event) => setOutcome(event.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="expo-learn">
                Qu'est-ce que t'as appris que tu ne savais pas ?<span className="hint">Une phrase</span>
              </label>
              <input
                id="expo-learn"
                value={learning}
                placeholder="L'anxiété est montée à 8 puis redescendue seule en 12 minutes."
                onChange={(event) => setLearning(event.target.value)}
              />
            </div>
            <Slider label="Anxiété à la fin" value={anxietyAfter} onChange={setAnxietyAfter} />
            <div className="field">
              <label htmlFor="expo-dropped">
                Comportements de sécurité retirés<span className="hint">Séparés par des virgules</span>
              </label>
              <input
                id="expo-dropped"
                value={dropped}
                onChange={(event) => setDropped(event.target.value)}
              />
            </div>
            <label
              style={{ display: 'flex', gap: 12, alignItems: 'center', textTransform: 'none', letterSpacing: 0, fontSize: '0.875rem', fontWeight: 400 }}
            >
              <input type="checkbox" checked={mastered} onChange={(event) => setMastered(event.target.checked)} />
              <span>Marquer cet item comme maîtrisé</span>
            </label>
          </>
        )}

        <WhyBox
          mechanism={WHY.mechanism}
          evidenceLevel="A"
          sources={WHY.sources}
          contraindications={WHY.contraindications}
        />
      </div>

      <div className="w-foot">
        {mode === 'add' ? (
          <button
            className="btn-primary"
            disabled={busy || !(label || prefillLabel).trim()}
            onClick={() =>
              onSubmit({
                mode: 'add',
                label: label || prefillLabel,
                kind,
                anticipated_anxiety: anticipated,
                safety_behaviors: safety
                  .split(',')
                  .map((value) => value.trim())
                  .filter(Boolean),
              })
            }
          >
            Ajouter à mon échelle
          </button>
        ) : (
          <button
            className="btn-primary"
            disabled={busy || !current || (!prediction.trim() && !outcome.trim())}
            onClick={() =>
              onSubmit({
                mode: 'attempt',
                item_id: current?.id,
                prediction,
                prediction_probability: probability,
                actual_outcome: outcome,
                learning,
                anxiety_max: anxietyMax,
                anxiety_after: anxietyAfter,
                mastered,
                safety_behaviors_dropped: dropped
                  .split(',')
                  .map((value) => value.trim())
                  .filter(Boolean),
              })
            }
          >
            Enregistrer la tentative
          </button>
        )}
        <button className="btn-sm" disabled={busy} onClick={onSkip}>
          Pas maintenant
        </button>
      </div>
    </>
  )
}
