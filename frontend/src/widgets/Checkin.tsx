import { useState } from 'react'
import Slider from '../components/Slider'
import Stepper from '../components/Stepper'
import WhyBox from '../components/WhyBox'
import type { WidgetProps } from '../components/WidgetHost'

const NOTE = 'Déduit de ta phrase — vérifie.'

export default function Checkin({ item, busy, onSubmit, onSkip }: WidgetProps) {
  const prefill = (item.payload?.prefill ?? {}) as Record<string, number | string>
  const check = new Set(item.payload?.a_verifier ?? [])
  const numberOf = (key: string, fallback: number) =>
    prefill[key] === undefined || prefill[key] === null ? fallback : Number(prefill[key])

  const [anxiety, setAnxiety] = useState(numberOf('anxiety_0_10', 5))
  const [mood, setMood] = useState(numberOf('mood_0_10', 5))
  const [avoidance, setAvoidance] = useState(numberOf('avoidance_0_10', 4))
  const [sleep, setSleep] = useState(numberOf('sleep_hours', 7))
  const [caffeine, setCaffeine] = useState(numberOf('caffeine_units', 1))
  const [panic, setPanic] = useState(numberOf('panic_attacks', 0))
  const [trigger, setTrigger] = useState(String(prefill.main_trigger ?? ''))

  // Correction d'un jour antérieur. Bornée à 60 jours : au-delà, le souvenir est
  // trop reconstruit pour entrer dans une corrélation.
  const today = new Date().toISOString().slice(0, 10)
  const floor = new Date(Date.now() - 60 * 86_400_000).toISOString().slice(0, 10)
  const [date, setDate] = useState(String(prefill.entry_date ?? today))
  const [pickDate, setPickDate] = useState(date !== today)

  return (
    <>
      <div className="w-body">
        <Slider
          label="Anxiété"
          value={anxiety}
          onChange={setAnxiety}
          lowLabel="aucune"
          highLabel="maximale"
          note={check.has('anxiety_0_10') ? NOTE : undefined}
        />
        <Slider
          label="Humeur"
          value={mood}
          onChange={setMood}
          lowLabel="très basse"
          highLabel="très bonne"
          note={check.has('mood_0_10') ? NOTE : undefined}
        />
        <Slider
          label="Évitement"
          value={avoidance}
          onChange={setAvoidance}
          lowLabel="aucun"
          highLabel="total"
          note={check.has('avoidance_0_10') ? NOTE : undefined}
        />

        <div className="pair">
          <Stepper
            label="Sommeil (h)"
            value={sleep}
            onChange={setSleep}
            max={24}
            step={0.5}
            note={check.has('sleep_hours') ? NOTE : undefined}
          />
          <Stepper label="Cafés" value={caffeine} onChange={setCaffeine} max={30} />
          <Stepper
            label="Paniques"
            value={panic}
            onChange={setPanic}
            max={50}
            note={check.has('panic_attacks') ? NOTE : undefined}
          />
        </div>

        <div className="field" style={{ marginTop: 'var(--g3)' }}>
          {pickDate ? (
            <>
              <label htmlFor="checkin-date">
                Jour renseigné<span className="hint">60 jours en arrière au plus, jamais dans le futur</span>
              </label>
              <input
                id="checkin-date"
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
          <label htmlFor="trigger">
            Le déclencheur, en une phrase<span className="hint">Facultatif</span>
          </label>
          <input
            id="trigger"
            value={trigger}
            placeholder="Réunion à 15 h, message pas répondu, palpitations le matin…"
            onChange={(event) => setTrigger(event.target.value)}
          />
        </div>

        <WhyBox
          mechanism="Mesurer un comportement le modifie. Les données corrigent la mémoire biaisée par l'anxiété, qui ne retient que les pires moments. Et les régularités personnelles — sommeil → anxiété du lendemain, caféine → pics — ne sont visibles que sur ta propre série : aucune moyenne de population ne peut te les dire."
          evidenceLevel="A"
          sources={[
            {
              label:
                "Linardon et al., World Psychiatry 2024 — méta-analyse de 176 essais randomisés d'applications de santé mentale",
              url: 'https://onlinelibrary.wiley.com/doi/full/10.1002/wps.21183',
            },
            {
              label: "NICE CG113 — l'éducation et le suivi actif constituent l'étape 1 pour l'anxiété généralisée",
              url: 'https://www.nice.org.uk/guidance/cg113/chapter/Recommendations',
            },
          ]}
          contraindications="Ne mesure pas ton pouls et ne note pas chaque sensation dans la journée : un auto-monitoring excessif devient de l'hypervigilance corporelle, et ça entretient l'anxiété. Une à deux saisies par jour suffisent."
        />
      </div>

      <div className="w-foot">
        <button
          className="btn-primary"
          disabled={busy}
          onClick={() =>
            onSubmit({
              entry_date: date,
              anxiety_0_10: anxiety,
              mood_0_10: mood,
              avoidance_0_10: avoidance,
              sleep_hours: sleep,
              caffeine_units: caffeine,
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
