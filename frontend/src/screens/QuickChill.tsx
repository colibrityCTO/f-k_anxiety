import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Icon from '../components/Icon'
import Steps from '../components/Steps'
import Slider from '../components/Slider'
import WhyBox from '../components/WhyBox'
import { sendOrQueue } from '../lib/panic'
import type { PanicContext, PanicTool } from '../lib/types'

/**
 * QUICK CHILL — l'écran du pic d'anxiété.
 *
 * Quatre décisions, chacune pour une raison précise :
 *
 * **Plein écran, hors du fil.** C'est la seule exception assumée à « tout est dans
 * le fil ». Un fil qui défile est coûteux cognitivement, et en crise on n'a pas ça
 * à donner. Le récapitulatif, lui, est déposé dans le fil **après** : la trace reste
 * là où elle doit être.
 *
 * **Aucun appel réseau au lancement.** Le contenu est dans le bundle, l'état
 * personnel en réserve locale. Une crise dans le métro est une crise sans réseau.
 *
 * **Remarquer → nommer → respirer.** Dans cet ordre, et pas l'inverse. Nommer une
 * sensation réduit la réactivité par inhibition préfrontale, sans effort de contrôle.
 * Surtout : nommer d'abord **réinterprète** la sensation, respirer d'abord la
 * **supprime** — et la suppression répétée fabrique un comportement de sécurité.
 *
 * **On ne promet rien.** « Quelque chose à faire pendant que ça passe », pas
 * « respire et ça s'arrête ». La seconde formulation promet un contrôle qui n'existe
 * pas, et c'est elle qui crée la dépendance.
 */

type Step = 'remarquer' | 'nommer' | 'outil' | 'bilan' | 'fini'

/**
 * Les quatre temps de la séquence, pour la barre de progression. `fini` en est
 * exclu : ce n'est pas une étape mais l'après, et compter l'écran de sortie
 * ferait afficher « 4 sur 5 » à quelqu'un qui a tout terminé.
 *
 * Voir la fin est ce qui compte le plus ici, plus encore qu'ailleurs : en pleine
 * crise, une séquence dont on ne sait pas où elle s'arrête est une raison de ne
 * pas la commencer.
 */
const ETAPES: { step: Step; title: string }[] = [
  { step: 'remarquer', title: 'Remarquer' },
  { step: 'nommer', title: 'Nommer' },
  { step: 'outil', title: 'Un outil' },
  { step: 'bilan', title: 'Noter' },
]

const ORDER: PanicTool['step'][] = ['respirer', 'ancrer', 'froid', 'jeu']

const GROUNDING = [
  'Cinq choses que tu vois',
  'Quatre choses que tu entends',
  'Trois choses que tu touches',
  'Deux choses que tu sens',
  'Une chose que tu goûtes',
]

export default function QuickChill({
  context,
  stale,
  onClose,
}: {
  context: PanicContext
  /** Réserve locale vieille de plus d'un jour : on le dit au lieu de le masquer. */
  stale: number | null
  onClose: (recorded: boolean) => void
}) {
  const [step, setStep] = useState<Step>('remarquer')
  const [areas, setAreas] = useState<string[]>([])
  const [thought, setThought] = useState<{ label: string; reframe: string } | null>(null)
  const [toolIndex, setToolIndex] = useState(0)
  const [used, setUsed] = useState<{ slug: string; seconds: number }[]>([])
  const [coldConfirmed, setColdConfirmed] = useState(Boolean(context.froid_valide_le))
  const [after, setAfter] = useState(5)
  const [minutes, setMinutes] = useState(10)
  const [feared, setFeared] = useState<boolean | null>(null)
  const [happened, setHappened] = useState('')
  const [preceded, setPreceded] = useState('')
  const [saving, setSaving] = useState(false)
  const [queued, setQueued] = useState(false)

  const startedAt = useRef(Date.now())

  const tools = useMemo(
    () =>
      ORDER.map((s) => context.outils.find((t) => t.step === s)).filter(
        (t): t is PanicTool => Boolean(t),
      ),
    [context.outils],
  )
  const tool = tools[toolIndex]

  // Échap ferme, comme n'importe quel plein écran. En crise, on doit pouvoir sortir
  // sans chercher le bouton.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const nextTool = useCallback(() => {
    if (toolIndex + 1 < tools.length) setToolIndex(toolIndex + 1)
    else setStep('bilan')
  }, [toolIndex, tools.length])

  const noteUse = useCallback(
    (slug: string, seconds: number) =>
      setUsed((current) =>
        current.some((u) => u.slug === slug) ? current : [...current, { slug, seconds }],
      ),
    [],
  )

  async function save() {
    setSaving(true)
    const ok = await sendOrQueue({
      what_preceded: preceded || null,
      body_symptoms: areas,
      thought_in_moment: thought?.label ?? null,
      tools_used: used,
      anxiety_peak: 10,
      anxiety_after: after,
      time_to_relief_min: Math.max(
        1,
        minutes || Math.round((Date.now() - startedAt.current) / 60_000),
      ),
      what_actually_happened: happened || null,
      feared_outcome_happened: feared,
      confirm_cold_contraindications:
        coldConfirmed && !context.froid_valide_le && used.some((u) => u.slug === 'froid'),
    })
    setSaving(false)
    setQueued(!ok)
    setStep('fini')
  }

  return (
    <div className="qc" role="dialog" aria-modal="true" aria-label="Mode crise">
      <div className="qc-top">
        <span className="qc-eyebrow">Quick chill</span>
        <button className="iconbtn" aria-label="Fermer" onClick={() => onClose(false)}>
          <Icon name="close" />
        </button>
      </div>

      <div className="qc-body">
        {step !== 'fini' && (
          <Steps
            index={Math.max(0, ETAPES.findIndex((e) => e.step === step))}
            titles={ETAPES.map((e) => e.title)}
          />
        )}

        {step === 'remarquer' && (
          <>
            <p className="qc-framing">{context.cadrage}</p>
            <h2 className="qc-h">Où tu le sens ?</h2>
            <div className="chips">
              {context.zones.map((zone) => (
                <button
                  key={zone}
                  className={`chip${areas.includes(zone) ? ' on' : ''}`}
                  onClick={() =>
                    setAreas((current) =>
                      current.includes(zone)
                        ? current.filter((z) => z !== zone)
                        : [...current, zone],
                    )
                  }
                >
                  {zone}
                </button>
              ))}
            </div>
            <div className="qc-foot">
              <button className="btn-primary" onClick={() => setStep('nommer')}>
                Continuer
              </button>
              <button className="btn-sm" onClick={() => setStep('outil')}>
                Passer, je veux juste respirer
              </button>
            </div>
          </>
        )}

        {step === 'nommer' && (
          <>
            <h2 className="qc-h">C'est quoi, la pensée ?</h2>
            {!thought ? (
              <div className="qc-cards">
                {context.pensees.map((item) => (
                  <button key={item.label} className="qc-card" onClick={() => setThought(item)}>
                    {item.label}
                  </button>
                ))}
              </div>
            ) : (
              <>
                <p className="qc-named">« {thought.label} »</p>
                <p className="qc-reframe">{thought.reframe}</p>
              </>
            )}
            <div className="qc-foot">
              <button className="btn-primary" onClick={() => setStep('outil')}>
                {thought ? 'Maintenant on respire' : 'Aucune des quatre'}
              </button>
              {thought && (
                <button className="btn-sm" onClick={() => setThought(null)}>
                  Changer
                </button>
              )}
            </div>
          </>
        )}

        {step === 'outil' && tool && (
          <ToolStep
            tool={tool}
            coldConfirmed={coldConfirmed}
            onConfirmCold={() => setColdConfirmed(true)}
            onUsed={(seconds) => noteUse(tool.slug, seconds)}
            onBetter={() => {
              setStep('bilan')
            }}
            onNext={nextTool}
            isLast={toolIndex + 1 >= tools.length}
          />
        )}

        {step === 'bilan' && (
          <>
            <h2 className="qc-h">C'est passé.</h2>
            <Slider
              label="Où tu en es maintenant"
              value={after}
              onChange={setAfter}
              lowLabel="calme"
              highLabel="au maximum"
            />
            <div className="field">
              <label htmlFor="qc-min">
                Ça a duré combien de temps ?<span className="hint">En minutes, à peu près</span>
              </label>
              <input
                id="qc-min"
                type="number"
                min={1}
                max={600}
                value={minutes}
                onChange={(event) => setMinutes(Number(event.target.value))}
              />
            </div>
            <div className="field">
              <label htmlFor="qc-before">
                Qu'est-ce qui a précédé ?<span className="hint">Facultatif</span>
              </label>
              <input
                id="qc-before"
                value={preceded}
                placeholder="métro bondé, trois cafés, mauvaise nuit…"
                onChange={(event) => setPreceded(event.target.value)}
              />
            </div>

            {/* La question qui rend le log utilisable comme preuve. La réponse vient
                de l'utilisateur : l'application ne peut pas juger d'un texte libre si
                la catastrophe a eu lieu, et prétendre le faire serait une invention. */}
            <div className="field">
              <label style={{ marginBottom: 'var(--g1)' }}>
                Ce que tu redoutais, c'est arrivé ?
              </label>
              <div className="chips">
                <button
                  className={`chip${feared === false ? ' on' : ''}`}
                  onClick={() => setFeared(false)}
                >
                  Non
                </button>
                <button
                  className={`chip${feared === true ? ' on' : ''}`}
                  onClick={() => setFeared(true)}
                >
                  Oui
                </button>
              </div>
            </div>
            <div className="field">
              <label htmlFor="qc-real">
                Ce qui s'est réellement passé<span className="hint">Facultatif</span>
              </label>
              <input
                id="qc-real"
                value={happened}
                placeholder="rien, je suis descendu à la station suivante…"
                onChange={(event) => setHappened(event.target.value)}
              />
            </div>

            {context.bilan.phrase && (
              <p className="qc-proof">
                Jusqu'ici : {context.bilan.phrase.replace(/\*\*/g, '')}
              </p>
            )}

            {/* Le garde-fou anti-comportement de sécurité. Il était calculé par le
                serveur — deux conditions simultanées, usage élevé **et** GAD-7 qui ne
                bouge pas au-delà de sa DMCI — envoyé dans le contexte, et affiché
                nulle part. Un écran d'urgence qui devient ce qui rassure travaille
                contre le traitement, et c'est exactement ce que cette phrase dit.

                Placé **après** l'épisode, jamais avant : pendant la crise, ce serait
                un reproche au pire moment. Ici, la crise est passée. */}
            {context.alerte_usage && (
              <p className="qc-alert">{context.alerte_usage.replace(/\*\*/g, '')}</p>
            )}

            <div className="qc-foot">
              <button className="btn-primary" disabled={saving} onClick={save}>
                {saving ? 'Enregistrement…' : 'Enregistrer'}
              </button>
              <button className="btn-sm" disabled={saving} onClick={() => onClose(false)}>
                Ne rien enregistrer
              </button>
            </div>
          </>
        )}

        {step === 'fini' && (
          <>
            <h2 className="qc-h">{queued ? 'Gardé.' : 'Noté.'}</h2>
            <p className="qc-reframe">
              {queued
                ? "Pas de réseau — l'épisode est gardé sur l'appareil et partira à la prochaine ouverture. Rien n'est perdu."
                : "C'est dans ton historique. Au bout de quelques épisodes, ce sont ces lignes qui montrent que ça passe toujours."}
            </p>
            <div className="qc-foot">
              <button className="btn-primary" onClick={() => onClose(true)}>
                Revenir
              </button>
            </div>
          </>
        )}

        {stale !== null && stale > 24 && step === 'remarquer' && (
          <p className="tiny dim qc-stale">
            Données personnelles en réserve depuis {Math.round(stale / 24)} jour(s) — le bilan
            affiché peut être en retard. Le contenu, lui, est à jour.
          </p>
        )}
      </div>
    </div>
  )
}

/** Un outil : sa consigne, son minuteur, sa réserve de preuve, et sa porte. */
function ToolStep({
  tool,
  coldConfirmed,
  onConfirmCold,
  onUsed,
  onBetter,
  onNext,
  isLast,
}: {
  tool: PanicTool
  coldConfirmed: boolean
  onConfirmCold: () => void
  onUsed: (seconds: number) => void
  onBetter: () => void
  onNext: () => void
  isLast: boolean
}) {
  const [elapsed, setElapsed] = useState(0)
  const [running, setRunning] = useState(tool.step === 'respirer')
  const [checked, setChecked] = useState<number[]>([])

  useEffect(() => {
    setElapsed(0)
    setRunning(tool.step === 'respirer')
    setChecked([])
  }, [tool.slug, tool.step])

  useEffect(() => {
    if (!running) return
    const id = window.setInterval(() => setElapsed((value) => value + 1), 1000)
    return () => window.clearInterval(id)
  }, [running])

  useEffect(() => {
    if (elapsed > 0 && elapsed % 15 === 0) onUsed(elapsed)
  }, [elapsed, onUsed])

  // La porte du froid : la liste n'est pas un ornement. Tant qu'elle n'est pas
  // confirmée, l'outil ne démarre pas — et le serveur refuse de l'enregistrer.
  const gated = Boolean(tool.contraindications) && !coldConfirmed

  const cycle = tool.pattern ? tool.pattern.inhale + tool.pattern.hold + tool.pattern.exhale : 0
  const phase = (() => {
    if (!tool.pattern || !running) return null
    const t = elapsed % cycle
    if (t < tool.pattern.inhale) return 'Inspire'
    if (t < tool.pattern.inhale + tool.pattern.hold) return 'Retiens'
    return 'Expire'
  })()

  return (
    <>
      <h2 className="qc-h">{tool.name}</h2>
      <p className="qc-reframe">{tool.how}</p>

      {gated ? (
        <div className="qc-gate">
          <p>
            <b>Avant de faire ça</b> — le froid brutal ne convient pas à tout le monde. Confirme
            que tu n'as pas {tool.contraindications}, ou que ton médecin a donné son accord.
          </p>
          <button className="btn-primary" onClick={onConfirmCold}>
            Aucune de ces situations ne me concerne
          </button>
          <button className="btn-sm" onClick={onNext}>
            Je préfère éviter — passer
          </button>
        </div>
      ) : (
        <>
          {tool.pattern && (
            <div className="qc-breath">
              <div
                className="qc-orb"
                style={{
                  animationDuration: `${cycle}s`,
                  animationPlayState: running ? 'running' : 'paused',
                }}
              />
              <div className="qc-phase">{phase ?? 'Prêt'}</div>
              <div className="qc-timer">
                {String(Math.floor(elapsed / 60)).padStart(2, '0')}:
                {String(elapsed % 60).padStart(2, '0')} / {Math.round(tool.seconds / 60)} min
              </div>
            </div>
          )}

          {tool.step === 'ancrer' && (
            <div className="qc-list">
              {GROUNDING.map((line, index) => (
                <button
                  key={line}
                  className={`qc-item${checked.includes(index) ? ' done' : ''}`}
                  onClick={() => {
                    setChecked((current) =>
                      current.includes(index)
                        ? current.filter((i) => i !== index)
                        : [...current, index],
                    )
                    onUsed(0)
                  }}
                >
                  {line}
                </button>
              ))}
            </div>
          )}

          {tool.step === 'jeu' && <PatternGame onPlayed={() => onUsed(0)} />}

          {!tool.pattern && tool.step === 'froid' && (
            <div className="qc-timer" style={{ marginTop: 'var(--g3)' }}>
              {String(Math.floor(elapsed / 60)).padStart(2, '0')}:
              {String(elapsed % 60).padStart(2, '0')}
            </div>
          )}

          <div className="qc-foot">
            {tool.pattern && (
              <button className="btn-sm" onClick={() => setRunning((value) => !value)}>
                {running ? 'Pause' : 'Démarrer'}
              </button>
            )}
            {!tool.pattern && tool.step === 'froid' && !running && (
              <button className="btn-sm" onClick={() => setRunning(true)}>
                Démarrer le minuteur
              </button>
            )}
            <button className="btn-primary" onClick={onBetter}>
              Ça redescend
            </button>
            {!isLast && (
              <button className="btn-sm" onClick={onNext}>
                Toujours pareil — autre chose
              </button>
            )}
          </div>
        </>
      )}

      <WhyBox
        mechanism={tool.mechanism}
        evidenceLevel={tool.evidence}
        sources={tool.sources}
        contraindications={tool.caveat ?? tool.contraindications}
      />
    </>
  )
}

/**
 * Tâche à charge visuo-spatiale : reproduire un motif sur une grille.
 *
 * Pourquoi celle-ci et pas un jeu : ce que la preuve désigne est la **charge
 * visuo-spatiale**, pas le divertissement. Une reproduction de motif la sollicite
 * directement, et la difficulté monte d'une case à chaque réussite.
 *
 * Le niveau de preuve est affiché à côté, et il est bas : l'essai randomisé porte sur
 * les souvenirs intrusifs après un traumatisme, pas sur l'attaque de panique. Ici
 * c'est de l'extrapolation, et c'est dit.
 */
function PatternGame({ onPlayed }: { onPlayed: () => void }) {
  const SIZE = 16
  const [target, setTarget] = useState<number[]>([])
  const [picked, setPicked] = useState<number[]>([])
  const [showing, setShowing] = useState(false)
  const [level, setLevel] = useState(3)
  const [verdict, setVerdict] = useState<string | null>(null)

  const deal = useCallback(
    (count: number) => {
      const cells = new Set<number>()
      while (cells.size < count) cells.add(Math.floor(Math.random() * SIZE))
      setTarget([...cells])
      setPicked([])
      setVerdict(null)
      setShowing(true)
      window.setTimeout(() => setShowing(false), 900 + count * 250)
      onPlayed()
    },
    [onPlayed],
  )

  useEffect(() => {
    deal(3)
  }, [deal])

  function pick(index: number) {
    if (showing || verdict) return
    const next = picked.includes(index)
      ? picked.filter((i) => i !== index)
      : [...picked, index]
    setPicked(next)
    if (next.length === target.length) {
      const right = next.every((i) => target.includes(i))
      setVerdict(right ? 'Juste' : 'Raté')
      window.setTimeout(() => {
        const step = right ? Math.min(level + 1, 8) : Math.max(level - 1, 3)
        setLevel(step)
        deal(step)
      }, 700)
    }
  }

  return (
    <div className="qc-game">
      <div className="qc-grid">
        {Array.from({ length: SIZE }, (_, index) => (
          <button
            key={index}
            className={`qc-cell${
              showing && target.includes(index) ? ' lit' : picked.includes(index) ? ' on' : ''
            }`}
            onClick={() => pick(index)}
            aria-label={`case ${index + 1}`}
          />
        ))}
      </div>
      <p className="tiny dim">
        {showing ? 'Retiens le motif…' : verdict ? verdict : `Reproduis-le — ${level} cases`}
      </p>
    </div>
  )
}
