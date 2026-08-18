import { useEffect, useMemo, useState } from 'react'
import Stepper from '../components/Stepper'
import WhyBox from '../components/WhyBox'
import type { WidgetProps } from '../components/WidgetHost'
import { api } from '../lib/api'
import type { Instrument } from '../lib/types'

/**
 * Le questionnaire initial. Une fois, trois minutes, huit écrans.
 *
 * ## Ce qu'il répare
 *
 * `program.py` lit `profile["difficultes"]` depuis le début pour proposer une
 * expérience sociale. Personne n'écrivait jamais cette clé : la règle ne levait pas
 * d'erreur, elle ne se déclenchait simplement jamais. Deux autres règles s'y
 * ajoutent maintenant — panique et inquiétude.
 *
 * ## Trois décisions de contenu
 *
 * **Le GAD-7 et le PHQ-2 sont récupérés de l'API**, pas recopiés ici. Le libellé
 * exact d'un item d'échelle validée n'est pas du texte d'interface : le reformuler
 * invaliderait la mesure, et en garder deux copies garantit qu'elles divergeront.
 *
 * **La sensibilité anxieuse est mesurée par trois items maison, et c'est écrit à
 * l'écran.** L'ASI-3 est publié par IDS Publishing et réservé aux professionnels
 * qualifiés : l'embarquer serait une infraction, et faire passer trois questions
 * maison pour l'ASI-3 serait un mensonge. Elles servent à orienter le programme, pas
 * à produire un score.
 *
 * **La question du médecin est posée, pas supposée.** Le programme 12 semaines pose
 * l'exclusion d'une cause organique comme préalable (« le médecin a déjà
 * confirmé »). Si la réponse est non, l'application le dit — des symptômes physiques
 * méritent d'être vus une fois avant d'être traités comme de l'anxiété.
 */

const DIFFICULTIES: { key: string; label: string }[] = [
  { key: 'panique', label: 'Crises de panique, peur des sensations physiques' },
  { key: 'inquietude', label: 'Inquiétude qui tourne en boucle' },
  { key: 'social', label: 'Situations sociales, regard des autres' },
  { key: 'agoraphobie', label: 'Transports, foule, lieux dont on ne sort pas vite' },
  { key: 'sante', label: 'Ma santé, mon corps' },
  { key: 'travail', label: 'Le travail, la performance' },
  { key: 'sommeil', label: 'Le sommeil' },
]

const SENSATIONS = [
  'cœur qui s’accélère',
  'oppression dans la poitrine',
  'manque d’air',
  'vertige, tête légère',
  'nausée, ventre noué',
  'picotements, engourdissements',
  'irréalité, détachement',
  'transpiration, chaleur',
]

/** Trois items maison sur la peur des sensations. Non validés, et dit comme tel. */
const SENSITIVITY_ITEMS = [
  'Quand je sens mon cœur battre plus vite, je me dis que quelque chose va mal.',
  'Les sensations dans mon corps m’inquiètent plus que les autres gens.',
  'Quand je me sens étourdi, j’ai peur de m’évanouir ou de perdre le contrôle.',
]
const SENSITIVITY_OPTIONS = ['pas du tout', 'un peu', 'moyennement', 'beaucoup', 'énormément']

const AGES = [
  { key: 'moins-1-an', label: 'moins d’un an' },
  { key: '1-5-ans', label: '1 à 5 ans' },
  { key: '5-15-ans', label: '5 à 15 ans' },
  { key: 'plus-15-ans', label: 'plus de 15 ans' },
]

type Step = { key: string; title: string }

const STEPS: Step[] = [
  { key: 'objectif', title: 'Ce que ça t’empêche de faire' },
  { key: 'difficultes', title: 'Ce qui est le plus dur' },
  { key: 'anciennete', title: 'Depuis quand' },
  { key: 'gad7', title: 'GAD-7' },
  { key: 'phq2', title: 'PHQ-2' },
  { key: 'sensations', title: 'Les sensations' },
  { key: 'habitudes', title: 'Tes habitudes' },
  { key: 'securite', title: 'Sécurité' },
]

export default function Onboarding({ busy, onSubmit }: WidgetProps) {
  const [instruments, setInstruments] = useState<Instrument[] | null>(null)
  const [step, setStep] = useState(0)

  const [objectif, setObjectif] = useState('')
  const [difficultes, setDifficultes] = useState<string[]>([])
  const [anciennete, setAnciennete] = useState<string | null>(null)
  const [gad7, setGad7] = useState<number[]>(Array(7).fill(0))
  const [phq2, setPhq2] = useState<number[]>(Array(2).fill(0))
  const [sensibilite, setSensibilite] = useState<number[]>(Array(3).fill(0))
  const [paniques, setPaniques] = useState(0)
  const [sensations, setSensations] = useState<string[]>([])
  const [cafeine, setCafeine] = useState(2)
  const [alcool, setAlcool] = useState(2)
  const [sport, setSport] = useState(2)
  const [heure, setHeure] = useState('21:00')
  const [medecin, setMedecin] = useState<boolean | null>(null)
  const [contreIndications, setContreIndications] = useState(false)

  useEffect(() => {
    api
      .instruments()
      .then((data) => setInstruments(data.instruments))
      .catch(() => setInstruments([]))
  }, [])

  const gad = useMemo(
    () => instruments?.find((i) => i.instrument === 'gad7') ?? null,
    [instruments],
  )
  const phq = useMemo(
    () => instruments?.find((i) => i.instrument === 'phq2') ?? null,
    [instruments],
  )

  const toggle = (list: string[], value: string) =>
    list.includes(value) ? list.filter((v) => v !== value) : [...list, value]

  const current = STEPS[step]
  const last = step === STEPS.length - 1

  function scaleGrid(
    meta: Instrument | null,
    values: number[],
    setValues: (next: number[]) => void,
  ) {
    if (!meta) return <p className="dim">Chargement de l'échelle…</p>
    return (
      <>
        <p className="tiny dim">{meta.prompt}</p>
        {meta.items.map((item, index) => (
          <div className="field" key={item}>
            <label style={{ marginBottom: 'var(--g1)' }}>{item}</label>
            <div className="chips">
              {meta.options.map((option) => (
                <button
                  key={option.value}
                  className={`chip${values[index] === option.value ? ' on' : ''}`}
                  onClick={() =>
                    setValues(values.map((v, i) => (i === index ? option.value : v)))
                  }
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>
        ))}
        <p className="tiny dim">{meta.limits}</p>
      </>
    )
  }

  return (
    <>
      <div className="w-body">
        <p className="tiny dim">
          Étape {step + 1} sur {STEPS.length} — {current.title}
        </p>

        {current.key === 'objectif' && (
          <div className="field">
            <label htmlFor="ob-objectif">
              Qu'est-ce que l'anxiété t'empêche de faire ?
              <span className="hint">
                Une ou deux phrases. C'est la seule question dont la réponse compte plus que
                les chiffres.
              </span>
            </label>
            <textarea
              id="ob-objectif"
              value={objectif}
              placeholder="prendre le métro sans y penser la veille, dire non en réunion, dormir sans vérifier mon pouls…"
              onChange={(event) => setObjectif(event.target.value)}
            />
          </div>
        )}

        {current.key === 'difficultes' && (
          <>
            <p className="tiny dim">
              Coche ce qui te concerne. C'est ça qui décide de l'ordre du programme — pas
              une moyenne de population.
            </p>
            <div className="chips">
              {DIFFICULTIES.map((item) => (
                <button
                  key={item.key}
                  className={`chip${difficultes.includes(item.key) ? ' on' : ''}`}
                  onClick={() => setDifficultes(toggle(difficultes, item.key))}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </>
        )}

        {current.key === 'anciennete' && (
          <>
            <p className="tiny dim">
              Depuis combien de temps ? Ça change ce qu'on peut raisonnablement attendre en
              trois mois — une habitude de quinze ans ne se réécrit pas linéairement, et le
              savoir évite de prendre un plateau pour un échec.
            </p>
            <div className="chips">
              {AGES.map((item) => (
                <button
                  key={item.key}
                  className={`chip${anciennete === item.key ? ' on' : ''}`}
                  onClick={() => setAnciennete(item.key)}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </>
        )}

        {current.key === 'gad7' && scaleGrid(gad, gad7, setGad7)}
        {current.key === 'phq2' && scaleGrid(phq, phq2, setPhq2)}

        {current.key === 'sensations' && (
          <>
            <div className="pair">
              <Stepper
                label="Crises le mois dernier"
                value={paniques}
                onChange={setPaniques}
                max={60}
              />
            </div>
            <div className="field">
              <label style={{ marginBottom: 'var(--g1)' }}>
                Quelles sensations te font peur ?
                <span className="hint">
                  Elles décideront des exercices proposés : provoquer un vertige n'apprend
                  rien à quelqu'un dont les crises sont digestives.
                </span>
              </label>
              <div className="chips">
                {SENSATIONS.map((item) => (
                  <button
                    key={item}
                    className={`chip${sensations.includes(item) ? ' on' : ''}`}
                    onClick={() => setSensations(toggle(sensations, item))}
                  >
                    {item}
                  </button>
                ))}
              </div>
            </div>
            <p className="tiny dim">
              Trois dernières questions, <b>non validées</b> : elles orientent le programme,
              elles ne produisent pas un score. L'échelle de référence sur ce point n'est
              pas libre de droits.
            </p>
            {SENSITIVITY_ITEMS.map((item, index) => (
              <div className="field" key={item}>
                <label style={{ marginBottom: 'var(--g1)' }}>{item}</label>
                <div className="chips">
                  {SENSITIVITY_OPTIONS.map((label, value) => (
                    <button
                      key={label}
                      className={`chip${sensibilite[index] === value ? ' on' : ''}`}
                      onClick={() =>
                        setSensibilite(sensibilite.map((v, i) => (i === index ? value : v)))
                      }
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </>
        )}

        {current.key === 'habitudes' && (
          <>
            <p className="tiny dim">
              Des ordres de grandeur suffisent. Ils serviront de valeurs par défaut au
              check-in, pour que tu n'aies pas à tout ressaisir chaque soir.
            </p>
            <div className="pair">
              <Stepper label="Cafés / jour" value={cafeine} onChange={setCafeine} max={20} />
              <Stepper label="Verres / semaine" value={alcool} onChange={setAlcool} max={60} />
              <Stepper label="Séances / semaine" value={sport} onChange={setSport} max={20} />
            </div>
            <div className="field" style={{ marginBottom: 0 }}>
              <label htmlFor="ob-heure">
                Heure du rappel du soir<span className="hint">Modifiable à tout moment</span>
              </label>
              <input
                id="ob-heure"
                type="time"
                value={heure}
                style={{ width: 150 }}
                onChange={(event) => setHeure(event.target.value)}
              />
            </div>
          </>
        )}

        {current.key === 'securite' && (
          <>
            <div className="field">
              <label style={{ marginBottom: 'var(--g1)' }}>
                Un médecin a-t-il déjà écarté une cause physique à tes symptômes ?
                <span className="hint">
                  C'est le préalable de tout le reste, pas une formalité.
                </span>
              </label>
              <div className="chips">
                <button
                  className={`chip${medecin === true ? ' on' : ''}`}
                  onClick={() => setMedecin(true)}
                >
                  Oui
                </button>
                <button
                  className={`chip${medecin === false ? ' on' : ''}`}
                  onClick={() => setMedecin(false)}
                >
                  Non, pas encore
                </button>
              </div>
            </div>

            <label className="check">
              <input
                type="checkbox"
                checked={contreIndications}
                onChange={(event) => setContreIndications(event.target.checked)}
              />
              <span>
                Je n'ai <b>aucune</b> de ces situations, ou mon médecin m'a donné son
                accord : maladie cardiaque, maladie respiratoire dont l'asthme, épilepsie,
                hypertension non contrôlée, glaucome, antécédent d'AVC, grossesse, blessure
                au cou ou au dos, trouble de l'oreille interne, diabète mal équilibré.
                <br />
                <span className="tiny dim">
                  Cocher maintenant évite de te retrouver bloqué devant un bouton inactif
                  dans huit semaines. Tu peux le laisser décoché — les exercices concernés
                  seront simplement indisponibles jusqu'à ce que tu le fasses.
                </span>
              </span>
            </label>

            <p className="frame-note">
              Si tu as des idées suicidaires ou de te faire du mal, cette application n'est
              pas l'outil : <b>3114</b> (France, gratuit, 24 h/24), ou <b>15</b> / <b>112</b>.
            </p>
          </>
        )}

        <WhyBox
          mechanism="Deux usages, et ils sont distincts. Les réponses sur tes difficultés décident de l'ordre du programme : le Protocole Unifié est un tronc commun validé contre les protocoles spécifiques, et c'est la couche adaptative qui traite les particularités. Les échelles, elles, posent une ligne de base chiffrée — sans elle, aucune évolution n'est interprétable, parce que la mémoire sous anxiété ne retient que les pires moments."
          evidenceLevel="A"
          sources={[
            {
              label:
                'Barlow et al., World Psychiatry 2020 — Protocole Unifié ; essai d’équivalence contre les protocoles spécifiques (JAMA Psychiatry 2017)',
              url: 'https://onlinelibrary.wiley.com/doi/10.1002/wps.20748',
            },
            {
              label:
                'NICE CG113 — éducation et suivi actif : l’étape 1 pour l’anxiété généralisée',
              url: 'https://www.nice.org.uk/guidance/cg113/chapter/Recommendations',
            },
            {
              label:
                'GAD-7 et PHQ : libres de droits depuis 2010, aucune autorisation requise',
              url: 'https://www.pfizer.com/news/press-release/press-release-detail/pfizer_to_offer_free_public_access_to_mental_health_assessment_tools_to_improve_diagnosis_and_patient_care',
            },
          ]}
          data={[
            { label: 'Écrit une fois', value: 'refaisable depuis la page Compte, sans écraser' },
            { label: 'Sensibilité aux sensations', value: '3 items maison, non validés' },
          ]}
          contraindications="Aucune de ces réponses n'est un diagnostic. Le GAD-7 est un outil de dépistage et de suivi ; un score élevé indique qu'un accompagnement humain est la suite recommandée, pas que l'application suffira."
        />
      </div>

      <div className="w-foot">
        {step > 0 && (
          <button className="btn-sm" disabled={busy} onClick={() => setStep(step - 1)}>
            Retour
          </button>
        )}
        {!last ? (
          <button className="btn-primary" onClick={() => setStep(step + 1)}>
            Suivant
          </button>
        ) : (
          <button
            className="btn-primary"
            disabled={busy}
            onClick={() =>
              onSubmit({
                objectif,
                difficultes,
                anciennete,
                gad7,
                phq2,
                sensibilite,
                paniques_mois: paniques,
                sensations,
                habitudes: { cafeine_jour: cafeine, alcool_semaine: alcool, sport_semaine: sport },
                rappel_heure: heure,
                medecin_ecarte: medecin,
                contre_indications_ok: contreIndications,
              })
            }
          >
            Terminer
          </button>
        )}
      </div>
    </>
  )
}
