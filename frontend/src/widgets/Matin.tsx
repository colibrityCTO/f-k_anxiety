import { useState } from 'react'
import Slider from '../components/Slider'
import Stepper from '../components/Stepper'
import WhyBox from '../components/WhyBox'
import type { WidgetProps } from '../components/WidgetHost'

const NOTE = 'Déduit de ta phrase — vérifie.'

/**
 * Le matin : la nuit, l'instant, et l'intention. Trente secondes.
 *
 * Pourquoi le sommeil est ici et pas le soir : le rappel se dégrade dès que
 * l'agenda de sommeil n'est pas rempli au réveil, et l'estimation rétrospective
 * porte un biais qui n'est pas constant — les nuits courtes sont surestimées, les
 * longues sous-estimées. Demander « t'as dormi combien ? » douze heures après le
 * réveil récolte une valeur fausse, qui contamine ensuite la corrélation
 * sommeil → anxiété du lendemain.
 *
 * Et trois items seulement : la compliance baisse avec le nombre de questions, pas
 * avec le nombre de moments. Deux écrans courts tenus tous les jours valent mieux
 * qu'un formulaire complet rempli deux fois par semaine.
 */
export default function Matin({ item, busy, onSubmit, onSkip }: WidgetProps) {
  const prefill = (item.payload?.prefill ?? {}) as Record<string, number | string | string[]>
  const check = new Set(item.payload?.a_verifier ?? [])
  const derived = new Set((prefill._derive as string[] | undefined) ?? [])
  const numberOf = (key: string, fallback: number) =>
    prefill[key] === undefined || prefill[key] === null ? fallback : Number(prefill[key])

  const [sleep, setSleep] = useState(numberOf('sleep_hours', 7))
  const [quality, setQuality] = useState(numberOf('sleep_quality_0_10', 5))
  const [anxiety, setAnxiety] = useState(numberOf('anxiety_0_10', 4))
  const [fear, setFear] = useState(String(prefill.main_trigger ?? ''))
  const [intention, setIntention] = useState('')

  // Le sommeil vient d'un bracelet : on l'affiche, on ne le redemande pas — mais on
  // laisse corriger. Un capteur se trompe (sieste comptée comme nuit, bracelet
  // retiré), et une donnée de santé fausse est pire qu'une donnée absente.
  const fromSensor = derived.has('sleep_hours')
  const [correcting, setCorrecting] = useState(false)

  return (
    <>
      <div className="w-body">
        {fromSensor && !correcting ? (
          <div className="field">
            <label style={{ marginBottom: 0 }}>
              Sommeil<span className="hint">Lu sur ton bracelet — pas besoin de le saisir</span>
            </label>
            <p className="readout">
              {sleep.toFixed(1)} h
              <button className="btn-sm" onClick={() => setCorrecting(true)}>
                Corriger
              </button>
            </p>
          </div>
        ) : (
          <div className="pair">
            <Stepper
              label="Sommeil (h)"
              value={sleep}
              onChange={setSleep}
              max={24}
              step={0.5}
              note={check.has('sleep_hours') ? NOTE : undefined}
            />
          </div>
        )}

        <Slider
          label="Qualité de la nuit"
          value={quality}
          onChange={setQuality}
          lowLabel="très mauvaise"
          highLabel="excellente"
          note={check.has('sleep_quality_0_10') ? NOTE : undefined}
        />

        <Slider
          label="Comment tu te sens là"
          value={anxiety}
          onChange={setAnxiety}
          lowLabel="calme"
          highLabel="au maximum"
          note={check.has('anxiety_0_10') ? NOTE : undefined}
        />

        {/* Les deux trous d'une seule phrase. Le second est le plus utile : il
            engage une action *malgré* l'anxiété, au lieu d'attendre qu'elle passe. */}
        <div className="field">
          <label htmlFor="matin-peur">
            Aujourd'hui j'ai peur de…<span className="hint">Une ligne suffit</span>
          </label>
          <input
            id="matin-peur"
            value={fear}
            placeholder="la réunion de 15 h, prendre le métro, appeler la banque…"
            onChange={(event) => setFear(event.target.value)}
          />
        </div>

        <div className="field" style={{ marginBottom: 0 }}>
          <label htmlFor="matin-intention">
            …et je vais quand même faire<span className="hint">Facultatif, mais c'est le plus utile</span>
          </label>
          <input
            id="matin-intention"
            value={intention}
            placeholder="y aller sans préparer mes phrases, prendre la ligne 4…"
            onChange={(event) => setIntention(event.target.value)}
          />
        </div>

        <WhyBox
          mechanism="Le sommeil se note au réveil parce que le rappel se dégrade vite : dès que l'agenda n'est pas rempli le matin, l'estimation devient approximative, et son biais n'est pas constant — les nuits courtes sont surestimées, les longues sous-estimées. Une valeur fausse ici fausse toute la corrélation sommeil → anxiété du lendemain. La seconde phrase relève d'une autre logique : nommer une action à faire malgré l'anxiété, plutôt qu'attendre sa disparition."
          evidenceLevel="B"
          sources={[
            {
              label:
                'Consensus Sleep Diary — étude par entretiens cognitifs : difficultés de rappel quand l’agenda n’est pas rempli directement au réveil',
              url: 'https://pmc.ncbi.nlm.nih.gov/articles/PMC10879077/',
            },
            {
              label:
                'Scientific Reports 2024 — biais non constant des estimations rétrospectives de durée de sommeil',
              url: 'https://www.nature.com/articles/s41598-024-53174-1',
            },
          ]}
          data={[
            { label: 'Écran', value: 'matin — la nuit et l’instant' },
            { label: 'Le reste', value: 'demandé le soir, quand la journée est finie' },
          ]}
        />
      </div>

      <div className="w-foot">
        <button
          className="btn-primary"
          disabled={busy}
          onClick={() =>
            onSubmit({
              sleep_hours: sleep,
              sleep_quality_0_10: quality,
              // `corrige` dit quelque chose du capteur, pas seulement de la valeur :
              // c'est ce qui permettra plus tard de savoir s'il est fiable.
              sleep_source: fromSensor ? (correcting ? 'corrige' : 'capteur') : 'declare',
              anxiety_0_10: anxiety,
              main_trigger: fear || null,
              intention: intention || null,
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
