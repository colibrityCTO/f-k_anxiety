import { useEffect, useRef, useState } from 'react'
import Slider from '../components/Slider'
import Steps from '../components/Steps'
import WhyBox from '../components/WhyBox'
import type { WidgetProps } from '../components/WidgetHost'
import { api } from '../lib/api'
import type { InteroceptivePayload } from '../lib/types'

/**
 * Exposition intéroceptive : provoquer volontairement les sensations redoutées.
 *
 * Deux garde-fous dans l'interface, pas seulement dans le texte : la porte de
 * contre-indications bloque l'accès jusqu'à validation explicite, et le champ
 * « prédiction » se remplit avant l'exercice — c'est l'écart avec le résultat qui
 * produit l'apprentissage, pas la baisse d'anxiété pendant.
 *
 * Quatre étapes, une seule à l'écran. Tout tenait sur une même page : le choix de
 * l'exercice, la prédiction, le minuteur et le bilan, soit huit champs et un
 * compte à rebours empilés. Le découpage n'est pas cosmétique ici — il rend
 * structurellement impossible d'écrire sa prédiction *après* avoir vu ce qui s'est
 * passé, alors que c'est l'écart entre les deux qui produit tout l'apprentissage.
 * L'ordre était déjà celui-là dans la page ; il n'était pas contraint.
 */
const ETAPES = ['L’exercice', 'Ta prédiction', 'Le faire', 'Ce qui s’est passé']
export default function Interoceptif({ busy, onSubmit, onSkip }: WidgetProps) {
  const [data, setData] = useState<InteroceptivePayload | null>(null)
  const [confirmed, setConfirmed] = useState(false)
  const [slug, setSlug] = useState<string | null>(null)
  const [prediction, setPrediction] = useState('')
  const [probability, setProbability] = useState(60)
  const [outcome, setOutcome] = useState('')
  const [learning, setLearning] = useState('')
  const [anxietyMax, setAnxietyMax] = useState(6)
  const [anxietyAfter, setAnxietyAfter] = useState(3)
  // La ressemblance aux crises réelles. Défaut à 5 et non 0 : un défaut à zéro
  // serait validé tel quel par quelqu'un qui passe vite, et un zéro faux ferait
  // écarter un exercice utile.
  const [similarity, setSimilarity] = useState(5)
  const [remaining, setRemaining] = useState(0)
  const [running, setRunning] = useState(false)
  const [finished, setFinished] = useState(false)
  const [etape, setEtape] = useState(0)
  const timer = useRef<number | null>(null)

  useEffect(() => {
    api.interoceptive().then(setData).catch(() => undefined)
  }, [])

  useEffect(() => {
    if (!running) return
    timer.current = window.setInterval(() => {
      setRemaining((value) => {
        if (value <= 1) {
          setRunning(false)
          setFinished(true)
          // On enchaîne seul sur le bilan : réclamer un clic « Suivant » à quelqu'un
          // qui vient de provoquer volontairement ses sensations redoutées est une
          // friction placée exactement au mauvais endroit.
          setEtape(3)
          return 0
        }
        return value - 1
      })
    }, 1000)
    return () => {
      if (timer.current !== null) window.clearInterval(timer.current)
    }
  }, [running])

  if (!data) {
    return (
      <div className="w-body">
        <p className="small dim">Chargement des exercices…</p>
      </div>
    )
  }

  const gateOpen = Boolean(data.valide_le) || confirmed
  const exercise = data.exercices.find((row) => row.slug === slug) ?? null
  const repetitions = exercise
    ? (data.compte_par_exercice[`Exposition intéroceptive — ${exercise.name}`] ?? 0)
    : 0

  // --- Porte de contre-indications -----------------------------------------
  if (!gateOpen) {
    return (
      <>
        <div className="w-body">
          <h3 style={{ marginBottom: 'var(--g2)' }}>À vérifier une seule fois</h3>
          <p className="small">
            Ces exercices ne créent aucun danger chez une personne en bonne santé physique. Mais si
            l'une de ces situations te concerne, demande l'avis d'un médecin avant de commencer :
          </p>
          <ul className="source-list">
            {data.contre_indications.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
          <p className="small">
            Cette vérification n'est pas un formalisme : c'est aussi ce qui rend l'exercice crédible
            pour toi. Tu ne peux pas apprendre que des sensations sont sans danger si tu n'es pas sûr
            qu'elles le sont.
          </p>
          <WhyBox mechanism={data.mecanisme} evidenceLevel="A" sources={data.sources} />
        </div>
        <div className="w-foot">
          <button className="btn-primary" onClick={() => setConfirmed(true)}>
            Aucune ne me concerne, ou mon médecin est d'accord
          </button>
          <button className="btn-sm" disabled={busy} onClick={onSkip}>
            Pas maintenant
          </button>
        </div>
      </>
    )
  }

  const dernier = etape === ETAPES.length - 1
  // Ce qui bloque le passage à l'étape suivante, et pourquoi. Un bouton grisé sans
  // raison affichée se lit comme une panne ; chaque blocage porte donc sa phrase.
  const blocage =
    etape === 0 && !exercise
      ? 'Choisis un exercice.'
      : etape === 1 && !prediction.trim()
        ? "Écris ta prédiction d'abord — sans elle, l'exercice n'apprend rien."
        : etape === 2 && !finished && remaining === (exercise?.seconds ?? 0)
          ? "Lance le minuteur. Tu peux passer à la suite une fois l'exercice commencé."
          : null

  return (
    <>
      <div className="w-body">
        <Steps index={etape} titles={ETAPES} onGo={setEtape} />

        {/* --- 1. Quel exercice ------------------------------------------- */}
        {etape === 0 && (
          <div className="field">
            <label>Quel exercice ?</label>
            <div className="chips">
              {data.exercices.map((row) => {
                const count =
                  data.compte_par_exercice[`Exposition intéroceptive — ${row.name}`] ?? 0
                return (
                  <button
                    key={row.slug}
                    className="chip"
                    aria-pressed={slug === row.slug}
                    onClick={() => {
                      setSlug(row.slug)
                      setRemaining(row.seconds)
                      setRunning(false)
                      setFinished(false)
                    }}
                  >
                    {row.name} · {row.seconds} s{count > 0 ? ` · ${count}×` : ''}
                  </button>
                )
              })}
            </div>
            {exercise && (
              <>
                <p className="small">
                  <strong>{exercise.how}</strong> Sensations visées :{' '}
                  {exercise.sensations.join(', ')}.
                </p>
                {exercise.note && <p className="tiny dim">{exercise.note}</p>}
              </>
            )}
          </div>
        )}

        {/* --- 2. La prédiction, écrite avant ------------------------------ */}
        {etape === 1 && exercise && (
          <>
            <p className="small">
              <strong>{exercise.how}</strong> Sensations visées : {exercise.sensations.join(', ')}.
            </p>
            <div className="field">
              <label htmlFor="io-pred">
                Ta prédiction, écrite <strong>avant</strong>
              </label>
              <textarea
                id="io-pred"
                value={prediction}
                placeholder="« Je vais m'évanouir », « mon cœur va s'emballer et ne plus s'arrêter »…"
                onChange={(event) => setPrediction(event.target.value)}
              />
            </div>
            <Slider
              label="Probabilité que tu donnes"
              value={probability}
              onChange={setProbability}
              max={100}
              lowLabel="impossible"
              highLabel="certain"
              suffix=" %"
            />
          </>
        )}

        {/* --- 3. Le minuteur, seul à l'écran ------------------------------ */}
        {etape === 2 && exercise && (
          <div style={{ textAlign: 'center' }}>
            <p className="small">
              <strong>{exercise.how}</strong>
            </p>
            <div
              style={{
                fontFamily: 'var(--display)',
                fontSize: '4rem',
                lineHeight: 1,
                fontVariantNumeric: 'tabular-nums',
              }}
            >
              {remaining}
              <span style={{ fontSize: '1.25rem' }}> s</span>
            </div>
            <div className="btn-row" style={{ justifyContent: 'center' }}>
              <button
                className="btn-primary"
                disabled={remaining === 0}
                onClick={() => setRunning((value) => !value)}
              >
                {running ? 'Pause' : remaining < exercise.seconds ? 'Reprendre' : 'Lancer'}
              </button>
              <button
                onClick={() => {
                  setRunning(false)
                  setFinished(false)
                  setRemaining(exercise.seconds)
                }}
              >
                Remettre à zéro
              </button>
            </div>
          </div>
        )}

        {/* --- 4. Ce qui s'est réellement passé ---------------------------- */}
        {etape === 3 && exercise && (
          <>
            {finished && (
              <p className="small">
                Reste encore <strong>une minute</strong> avec les sensations, sans respiration de
                secours et sans t'asseoir précipitamment. Puis note ce qui s'est passé.
              </p>
            )}
            {/* La prédiction est rappelée, en lecture seule : c'est l'écart avec elle
                qui produit l'apprentissage, et de mémoire on la réécrit toujours plus
                proche du résultat qu'elle ne l'était. */}
            {prediction.trim() && (
              <p className="frame-note">
                Tu avais écrit, à {probability} % : « {prediction.trim()} »
              </p>
            )}
            <Slider label="Anxiété maximale pendant" value={anxietyMax} onChange={setAnxietyMax} />
            <div className="field">
              <label htmlFor="io-out">Ce qui s'est réellement passé</label>
              <textarea
                id="io-out"
                value={outcome}
                onChange={(event) => setOutcome(event.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="io-learn">
                Qu'est-ce que t'as appris ?<span className="hint">Une phrase</span>
              </label>
              <input
                id="io-learn"
                value={learning}
                onChange={(event) => setLearning(event.target.value)}
              />
            </div>
            <Slider label="Anxiété maintenant" value={anxietyAfter} onChange={setAnxietyAfter} />
            {/* La question qui décide quel exercice compte pour cette personne.
                Elle vient de l'évaluation intéroceptive de Schmidt & Trakowski,
                déjà citée dans le catalogue — et elle manquait. */}
            <Slider
              label="Ressemblance à tes crises réelles"
              value={similarity}
              onChange={setSimilarity}
              lowLabel="rien à voir"
              highLabel="exactement ça"
            />
          </>
        )}

        <WhyBox
          mechanism={data.mecanisme}
          evidenceLevel={exercise?.evidence ?? 'A'}
          sources={data.sources}
          contraindications={
            data.valide_le
              ? `Contre-indications validées le ${data.valide_le}. Si ta situation médicale change, reprends l'avis d'un médecin.`
              : undefined
          }
          data={
            exercise && repetitions > 0
              ? [{ label: 'Répétitions déjà faites', value: String(repetitions) }]
              : undefined
          }
        />
      </div>

      <div className="w-foot">
        {etape > 0 && (
          <button className="btn-sm" disabled={busy} onClick={() => setEtape(etape - 1)}>
            Retour
          </button>
        )}
        {!dernier ? (
          <button
            className="btn-primary"
            disabled={Boolean(blocage)}
            onClick={() => setEtape(etape + 1)}
          >
            Suivant
          </button>
        ) : (
          <button
            className="btn-primary"
            disabled={busy || !exercise || (!prediction.trim() && !outcome.trim())}
            onClick={() =>
              onSubmit({
                confirm_contraindications: !data.valide_le ? true : undefined,
                slug: exercise?.slug,
                prediction,
                prediction_probability: probability,
                actual_outcome: outcome,
                learning,
                anxiety_max: anxietyMax,
                anxiety_after: anxietyAfter,
                similarity_0_10: similarity,
                repetition: repetitions + 1,
              })
            }
          >
            Enregistrer
          </button>
        )}
        <button className="btn-sm" disabled={busy} onClick={onSkip}>
          Pas maintenant
        </button>
        {blocage && <span className="tiny dim">{blocage}</span>}
      </div>
    </>
  )
}
