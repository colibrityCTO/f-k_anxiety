import { useState } from 'react'
import Slider from '../components/Slider'
import WhyBox from '../components/WhyBox'
import type { WidgetProps } from '../components/WidgetHost'
import { api } from '../lib/api'
import type { JournalEntry } from '../lib/types'

const EMOTIONS = ['peur', 'angoisse', 'honte', 'colère', 'tristesse', 'culpabilité']

const WHY = {
  libre: {
    mechanism:
      "Mettre en mots découpe l'émotion en trois composantes manipulables — pensées, sensations, comportements — au lieu d'un bloc massif ingérable. C'est le module 2 du Protocole Unifié.",
    level: 'A',
    sources: [
      {
        label: 'Barlow & Farchione, World Psychiatry 2020 — Protocole Unifié transdiagnostique',
        url: 'https://onlinelibrary.wiley.com/doi/10.1002/wps.20748',
      },
    ],
  },
  pensee: {
    mechanism:
      "Le Protocole Unifié réduit les distorsions cognitives à deux pièges : surestimer la probabilité, et catastrophiser. Il ne s'agit pas de penser positif — ça ne marche pas — mais d'élargir l'éventail des interprétations, puis de tester la nouvelle hypothèse dans le réel. La question « et si c'était vrai, comment je fais face ? » est la plus utile, et la plus négligée.",
    level: 'A',
    sources: [
      {
        label: "NICE CG113 — la TCC est recommandée en première ligne pour l'anxiété généralisée",
        url: 'https://www.nice.org.uk/guidance/cg113/chapter/Recommendations',
      },
      {
        label: 'Méta-analyse de la TCC de faible intensité pour le TAG (2024)',
        url: 'https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10763350/',
      },
    ],
  },
} as const

export default function Journal({ item, busy, onSubmit, onSkip }: WidgetProps) {
  const prefill = (item.payload?.prefill ?? {}) as Record<string, string>
  const [kind, setKind] = useState<'libre' | 'pensee'>('libre')
  const [text, setText] = useState(String(prefill.free_text ?? ''))
  const [situation, setSituation] = useState(String(prefill.situation ?? ''))
  const [thought, setThought] = useState(String(prefill.automatic_thought ?? ''))
  const [trap, setTrap] = useState('')
  const [against, setAgainst] = useState('')
  const [coping, setCoping] = useState('')
  const [alternative, setAlternative] = useState('')
  const [before, setBefore] = useState(7)
  const [after, setAfter] = useState(5)
  const [emotions, setEmotions] = useState<string[]>([])
  const [editing, setEditing] = useState<string | null>(null)
  const [past, setPast] = useState<JournalEntry[] | null>(null)

  const why = WHY[kind]

  /** Charge une entrée passée dans le formulaire. La date d'origine est conservée. */
  function loadEntry(entry: JournalEntry) {
    setEditing(entry.id ?? null)
    setKind(entry.kind === 'pensee' ? 'pensee' : 'libre')
    setText(entry.free_text ?? '')
    setSituation(entry.situation ?? '')
    setThought(entry.automatic_thought ?? '')
    setTrap(entry.thinking_trap ?? '')
    setAgainst(entry.evidence_against ?? '')
    setCoping(entry.coping_plan ?? '')
    setAlternative(entry.alternative_thought ?? '')
    setBefore(entry.intensity_before ?? 7)
    setAfter(entry.intensity_after ?? 5)
    setEmotions(entry.emotions ?? [])
    setPast(null)
  }

  return (
    <>
      <div className="w-body">
        <div className="chips" style={{ marginBottom: 'var(--g3)' }}>
          <button className="chip" aria-pressed={kind === 'libre'} onClick={() => setKind('libre')}>
            Entrée libre
          </button>
          <button className="chip" aria-pressed={kind === 'pensee'} onClick={() => setKind('pensee')}>
            Journal de pensées
          </button>
          <button
            className="chip"
            aria-pressed={past !== null}
            onClick={async () => {
              if (past !== null) return setPast(null)
              setPast(await api.journal(undefined, 90).catch(() => []))
            }}
          >
            Corriger une entrée
          </button>
        </div>

        {past !== null && (
          <div className="field">
            <label>Tes 90 derniers jours</label>
            {past.length === 0 && <p className="small dim">Aucune entrée à corriger.</p>}
            <ul className="list-reset">
              {past.slice(0, 15).map((entry) => (
                <li key={entry.id} style={{ borderBottom: '1px solid rgba(255,255,255,.35)', padding: '8px 0' }}>
                  <button
                    className="btn-sm"
                    style={{ border: 0, padding: 0, textAlign: 'left', textTransform: 'none', letterSpacing: 0, fontSize: '0.875rem', fontWeight: 400 }}
                    onClick={() => loadEntry(entry)}
                  >
                    <strong>{entry.entry_date}</strong> · {entry.kind} —{' '}
                    {(entry.free_text ?? entry.situation ?? entry.automatic_thought ?? '').slice(0, 70) || '(vide)'}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        {editing && (
          <p className="tiny dim">
            Tu corriges une entrée existante. Sa date d'origine est conservée — corriger un texte ne
            le déplace pas à aujourd'hui.{' '}
            <button
              className="btn-sm"
              style={{ border: 0, padding: 0, textTransform: 'none', letterSpacing: 0 }}
              onClick={() => setEditing(null)}
            >
              (annuler la correction)
            </button>
          </p>
        )}

        {kind === 'libre' ? (
          <>
            <div className="field">
              <label htmlFor="free">Qu'est-ce qui s'est passé ?</label>
              <textarea
                id="free"
                value={text}
                placeholder="Les faits d'abord. Puis ce que t'as ressenti dans le corps. Puis ce que t'as fait, ou évité de faire."
                onChange={(event) => setText(event.target.value)}
              />
            </div>
            <div className="field" style={{ marginBottom: 0 }}>
              <label>Émotions</label>
              <div className="chips">
                {EMOTIONS.map((emotion) => (
                  <button
                    key={emotion}
                    className="chip"
                    aria-pressed={emotions.includes(emotion)}
                    onClick={() =>
                      setEmotions((current) =>
                        current.includes(emotion)
                          ? current.filter((value) => value !== emotion)
                          : [...current, emotion],
                      )
                    }
                  >
                    {emotion}
                  </button>
                ))}
              </div>
            </div>
          </>
        ) : (
          <>
            <div className="field">
              <label htmlFor="situation">La situation, en une phrase factuelle</label>
              <input id="situation" value={situation} onChange={(event) => setSituation(event.target.value)} />
            </div>
            <Slider label="Intensité sur le moment" value={before} onChange={setBefore} />
            <div className="field">
              <label htmlFor="thought">La pensée automatique — la phrase exacte</label>
              <textarea id="thought" value={thought} onChange={(event) => setThought(event.target.value)} />
            </div>
            <div className="field">
              <label>Quel piège ?</label>
              <div className="chips">
                {[
                  ['surestimation', 'Surestimation de la probabilité'],
                  ['catastrophisation', 'Catastrophisation'],
                  ['les_deux', 'Les deux'],
                ].map(([value, label]) => (
                  <button key={value} className="chip" aria-pressed={trap === value} onClick={() => setTrap(value)}>
                    {label}
                  </button>
                ))}
              </div>
            </div>
            <div className="field">
              <label htmlFor="against">Preuves contre cette pensée</label>
              <textarea id="against" value={against} onChange={(event) => setAgainst(event.target.value)} />
            </div>
            <div className="field">
              <label htmlFor="coping">
                Et si c'était vrai — comment tu fais face ?<span className="hint">Souvent la question la plus utile</span>
              </label>
              <textarea id="coping" value={coping} onChange={(event) => setCoping(event.target.value)} />
            </div>
            <div className="field">
              <label htmlFor="alt">Une pensée alternative crédible (pas « positive »)</label>
              <textarea id="alt" value={alternative} onChange={(event) => setAlternative(event.target.value)} />
            </div>
            <Slider label="Intensité maintenant" value={after} onChange={setAfter} />
          </>
        )}

        <WhyBox mechanism={why.mechanism} evidenceLevel={why.level} sources={[...why.sources]} />
      </div>

      <div className="w-foot">
        <button
          className="btn-primary"
          disabled={busy || (kind === 'libre' ? !text.trim() : !thought.trim())}
          onClick={() =>
            onSubmit(
              kind === 'libre'
                ? { kind, free_text: text, emotions, edit_id: editing }
                : {
                    kind,
                    edit_id: editing,
                    situation,
                    automatic_thought: thought,
                    thinking_trap: trap || null,
                    evidence_against: against,
                    coping_plan: coping,
                    alternative_thought: alternative,
                    intensity_before: before,
                    intensity_after: after,
                  },
            )
          }
        >
          {editing ? 'Corriger' : 'Enregistrer'}
        </button>
        <button className="btn-sm" disabled={busy} onClick={onSkip}>
          Pas maintenant
        </button>
      </div>
    </>
  )
}
