import { useState } from 'react'
import Slider from '../components/Slider'
import WhyBox from '../components/WhyBox'
import type { WidgetProps } from '../components/WidgetHost'

/** Où / avec qui / en train de quoi. Un 8 seul n'apprend rien ; un 8 « transports,
 *  seul » se recoupe avec les autres. Liste courte et fermée : du texte libre ne
 *  serait jamais comparable d'un jour sur l'autre. */
const CONTEXTS = [
  'travail',
  'maison',
  'transports',
  'dehors',
  'seul',
  'avec du monde',
  'avant un truc',
  'après un truc',
]

/**
 * « Comment je me sens là. » Un curseur, à volonté, jamais demandé.
 *
 * Un item unique 0-10 est défendable pour l'instant présent : il corrèle autour de
 * 0,70 avec la sous-échelle anxiété du HADS. La réserve est dite dans le panneau
 * plutôt que masquée — sur un item unique, aucune cohérence interne n'est
 * calculable : c'est un signal, pas un score.
 *
 * Deux choix de conception qui comptent autant que la mesure :
 *
 * - **Rien n'est demandé en retour.** Pas d'analyse, pas de commentaire, pas de
 *   félicitation. Chez certains, consulter sans arrêt ses propres notes devient le
 *   symptôme ; répondre à chaque mesure par une interprétation entraînerait ça.
 * - **L'application ne propose jamais cet écran d'elle-même.** Il vit dans le
 *   lanceur, à l'initiative de l'utilisateur. Trois invites par jour est un
 *   plafond, et le matin et le soir l'occupent déjà.
 */
export default function Maintenant({ item, busy, onSubmit }: WidgetProps) {
  const prefill = (item.payload?.prefill ?? {}) as Record<string, number | string>
  const [anxiety, setAnxiety] = useState(
    prefill.anxiety_0_10 === undefined ? 5 : Number(prefill.anxiety_0_10),
  )
  const [contexts, setContexts] = useState<string[]>([])
  const [note, setNote] = useState('')

  const toggle = (label: string) =>
    setContexts((current) =>
      current.includes(label) ? current.filter((c) => c !== label) : [...current, label],
    )

  return (
    <>
      <div className="w-body">
        <Slider
          label="Là, maintenant"
          value={anxiety}
          onChange={setAnxiety}
          lowLabel="calme"
          highLabel="au maximum"
        />

        <div className="field">
          <label style={{ marginBottom: 'var(--g1)' }}>
            Où t'en es<span className="hint">Facultatif — c'est ce qui rend le chiffre exploitable</span>
          </label>
          <div className="chips">
            {CONTEXTS.map((label) => (
              <button
                key={label}
                className={`chip${contexts.includes(label) ? ' on' : ''}`}
                onClick={() => toggle(label)}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        <div className="field" style={{ marginBottom: 0 }}>
          <label htmlFor="now-note">
            Un mot, si tu veux<span className="hint">Facultatif</span>
          </label>
          <input
            id="now-note"
            value={note}
            placeholder="ça monte depuis le message de ma mère…"
            onChange={(event) => setNote(event.target.value)}
          />
        </div>

        <WhyBox
          mechanism="Une seule question, posée sur l'instant plutôt que sur la journée. C'est ce qui donne la résolution intra-journée : avec un point par jour, « ça monte toujours en fin d'après-midi » est invisible. Et le soir, le pic et la moyenne se calculent sur ces mesures au lieu d'être reconstruits — sous anxiété, la mémoire ne retient que les pires moments."
          evidenceLevel="B"
          sources={[
            {
              label:
                'Évaluation psychométrique d’une échelle visuelle analogique d’anxiété — corrélation ≈ 0,70 avec la sous-échelle anxiété du HADS',
              url: 'https://pubmed.ncbi.nlm.nih.gov/20529361/',
            },
            {
              label:
                'JMIR 2024 — expérience factorielle nationale sur les bonnes pratiques de l’évaluation écologique momentanée',
              url: 'https://www.jmir.org/2024/1/e50275',
            },
          ]}
          data={[
            { label: 'Un seul item', value: 'signal exploitable, pas un score validé' },
            { label: 'Fiabilité interne', value: 'non calculable sur une question unique' },
          ]}
          contraindications="Si tu te surprends à noter toutes les dix minutes ou à surveiller ta courbe, arrête et reviens au matin et au soir : la surveillance continue de ses propres sensations est de l'hypervigilance, et elle entretient l'anxiété au lieu de la réduire."
        />
      </div>

      <div className="w-foot">
        <button
          className="btn-primary"
          disabled={busy}
          onClick={() =>
            onSubmit({ anxiety_0_10: anxiety, contexts, note: note || null })
          }
        >
          Noter
        </button>
      </div>
    </>
  )
}
