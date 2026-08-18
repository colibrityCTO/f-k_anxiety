import { useState } from 'react'
import Slider from '../components/Slider'
import Stepper from '../components/Stepper'
import WhyBox from '../components/WhyBox'
import type { WidgetProps } from '../components/WidgetHost'

const NOTE = 'Déduit de ta phrase — vérifie.'
const COMPUTED = 'Calculé sur tes mesures du jour — corrige si c’est faux.'

/**
 * Le soir : la journée écoulée, une fois qu'elle est finie.
 *
 * Deux chiffres d'anxiété et non un seul. Sous anxiété, la mémoire ne retient que
 * les pires moments — le programme du code le dit déjà noir sur blanc. Demander
 * « ton anxiété moyenne aujourd'hui » récolte donc en réalité un pic mal étiqueté,
 * qu'on traite ensuite comme une moyenne. Autant demander les deux et savoir lequel
 * est lequel. Et quand des mesures instantanées existent, les deux arrivent
 * **calculés** : plus rien à reconstruire de mémoire.
 *
 * Le compteur de paniques passe en lecture seule dès qu'un épisode a été déclaré :
 * une crise se note au moment où elle arrive, pas douze heures plus tard.
 */
export default function Soir({ item, busy, onSubmit, onSkip }: WidgetProps) {
  const prefill = (item.payload?.prefill ?? {}) as Record<string, number | string | string[]>
  const check = new Set(item.payload?.a_verifier ?? [])
  const derived = new Set((prefill._derive as string[] | undefined) ?? [])
  const numberOf = (key: string, fallback: number) =>
    prefill[key] === undefined || prefill[key] === null ? fallback : Number(prefill[key])

  const [mean, setMean] = useState(numberOf('anxiety_0_10', 5))
  const [peak, setPeak] = useState(numberOf('anxiety_peak_0_10', 6))
  const [mood, setMood] = useState(numberOf('mood_0_10', 5))
  const [avoidance, setAvoidance] = useState(numberOf('avoidance_0_10', 4))
  const [caffeine, setCaffeine] = useState(numberOf('caffeine_units', 1))
  const [alcohol, setAlcohol] = useState(numberOf('alcohol_units', 0))
  const [exercise, setExercise] = useState(numberOf('exercise_min', 0))
  const [panic, setPanic] = useState(numberOf('panic_attacks', 0))
  const [trigger, setTrigger] = useState(String(prefill.main_trigger ?? ''))

  // Paniques déclarées au moment de la crise : on affiche, on ne redemande pas.
  const panicDerived = derived.has('panic_attacks')

  const today = new Date().toISOString().slice(0, 10)
  const floor = new Date(Date.now() - 60 * 86_400_000).toISOString().slice(0, 10)
  const [date, setDate] = useState(String(prefill.entry_date ?? today))
  const [pickDate, setPickDate] = useState(date !== today)

  const noteFor = (key: string) =>
    derived.has(key) ? COMPUTED : check.has(key) ? NOTE : undefined

  return (
    <>
      <div className="w-body">
        <Slider
          label="Le pic de la journée"
          value={peak}
          onChange={setPeak}
          lowLabel="jamais monté"
          highLabel="au maximum"
          note={noteFor('anxiety_peak_0_10')}
        />
        <Slider
          label="En moyenne sur la journée"
          value={mean}
          onChange={setMean}
          lowLabel="calme"
          highLabel="au maximum"
          note={noteFor('anxiety_0_10')}
        />
        <Slider
          label="Humeur"
          value={mood}
          onChange={setMood}
          lowLabel="très basse"
          highLabel="très bonne"
          note={noteFor('mood_0_10')}
        />
        <Slider
          label="Évitement"
          value={avoidance}
          onChange={setAvoidance}
          lowLabel="aucun"
          highLabel="total"
          note={noteFor('avoidance_0_10')}
        />

        <div className="pair">
          <Stepper label="Cafés" value={caffeine} onChange={setCaffeine} max={30} />
          <Stepper label="Verres" value={alcohol} onChange={setAlcohol} max={40} />
          <Stepper label="Sport (min)" value={exercise} onChange={setExercise} max={600} step={5} />
        </div>

        {panicDerived ? (
          <div className="field">
            <label style={{ marginBottom: 0 }}>
              Paniques<span className="hint">Compté sur ce que t’as déclaré sur le moment</span>
            </label>
            <p className="readout">{panic}</p>
          </div>
        ) : (
          <div className="pair">
            <Stepper
              label="Paniques"
              value={panic}
              onChange={setPanic}
              max={50}
              note={check.has('panic_attacks') ? NOTE : undefined}
            />
          </div>
        )}

        <div className="field" style={{ marginTop: 'var(--g3)' }}>
          {pickDate ? (
            <>
              <label htmlFor="soir-date">
                Jour renseigné
                <span className="hint">60 jours en arrière au plus, jamais dans le futur</span>
              </label>
              <input
                id="soir-date"
                type="date"
                value={date}
                min={floor}
                max={today}
                onChange={(event) => setDate(event.target.value)}
              />
            </>
          ) : (
            <button className="btn-sm" onClick={() => setPickDate(true)}>
              Renseigner un autre jour
            </button>
          )}
        </div>

        <div className="field" style={{ marginBottom: 0 }}>
          <label htmlFor="soir-trigger">
            Le déclencheur, en une phrase<span className="hint">Facultatif</span>
          </label>
          <input
            id="soir-trigger"
            value={trigger}
            placeholder="Réunion à 15 h, message pas répondu, palpitations le matin…"
            onChange={(event) => setTrigger(event.target.value)}
          />
        </div>

        <WhyBox
          mechanism="Deux chiffres et non un seul : sous anxiété, la mémoire retient les pires moments, donc une « moyenne » demandée de tête est en réalité un pic. Les séparer permet de savoir lequel bouge — un pic qui baisse et une moyenne stable ne veulent pas dire la même chose. Les régularités personnelles (sommeil → anxiété du lendemain, caféine → pics) ne sont visibles que sur ta propre série : aucune moyenne de population ne peut te les dire."
          evidenceLevel="A"
          sources={[
            {
              label:
                'Linardon et al., World Psychiatry 2024 — méta-analyse de 176 essais randomisés d’applications de santé mentale',
              url: 'https://onlinelibrary.wiley.com/doi/full/10.1002/wps.21183',
            },
            {
              label:
                'NICE CG113 — l’éducation et le suivi actif constituent l’étape 1 pour l’anxiété généralisée',
              url: 'https://www.nice.org.uk/guidance/cg113/chapter/Recommendations',
            },
          ]}
          data={
            derived.size
              ? [{ label: 'Pré-rempli', value: 'calculé sur tes mesures instantanées du jour' }]
              : undefined
          }
          contraindications="Ne mesure pas ton pouls et ne note pas chaque sensation dans la journée : un auto-monitoring excessif devient de l'hypervigilance corporelle, et ça entretient l'anxiété."
        />
      </div>

      <div className="w-foot">
        <button
          className="btn-primary"
          disabled={busy}
          onClick={() =>
            onSubmit({
              entry_date: date,
              anxiety_0_10: mean,
              anxiety_peak_0_10: peak,
              mood_0_10: mood,
              avoidance_0_10: avoidance,
              caffeine_units: caffeine,
              alcohol_units: alcohol,
              exercise_min: exercise,
              // Ignoré côté serveur si des épisodes ont été déclarés : c'est le
              // compte réel qui gagne, pas ce qu'on se rappelle le soir.
              panic_attacks: panic,
              main_trigger: trigger || null,
            })
          }
        >
          Valider
        </button>
        <button className="btn-sm" disabled={busy} onClick={onSkip}>
          Pas maintenant
        </button>
      </div>
    </>
  )
}
