import { useEffect, useState } from 'react'
import WhyBox from '../components/WhyBox'
import type { WidgetProps } from '../components/WidgetHost'
import { api } from '../lib/api'
import type { EngineStatus } from '../lib/types'

/**
 * L'analyse n'est pas une saisie : valider signifie « lance-la ». Le résultat
 * arrive dans le fil comme un message, avec ses sources — pas enfermé ici.
 */
export default function Analysis({ busy, onSubmit, onSkip }: WidgetProps) {
  const [engine, setEngine] = useState<EngineStatus | null>(null)
  const [scope, setScope] = useState<'quotidien' | 'hebdomadaire'>('quotidien')

  useEffect(() => {
    api.engineStatus().then(setEngine).catch(() => undefined)
  }, [])

  return (
    <>
      <div className="w-body">
        <div className="chips" style={{ marginBottom: 'var(--g2)' }}>
          <button className="chip" aria-pressed={scope === 'quotidien'} onClick={() => setScope('quotidien')}>
            14 derniers jours
          </button>
          <button
            className="chip"
            aria-pressed={scope === 'hebdomadaire'}
            onClick={() => setScope('hebdomadaire')}
          >
            4 dernières semaines
          </button>
        </div>

        <p className="small">
          Je calcule d'abord tes chiffres, puis je les interprète en citant les fiches. Ce que tu
          n'as <strong>pas</strong> fait compte autant que le reste : c'est ce qui indique quoi
          ajuster.
        </p>

        {engine && (
          <p className="tiny dim">
            Mode : {engine.mode_effectif === 'llm' ? `rédaction par ${engine.moteur_principal}` : 'analyse locale déterministe'}
            {' · '}recherche vectorielle :{' '}
            {engine.recherche_vectorielle ? engine.modele_embeddings : 'désactivée (mode lexical)'}
          </p>
        )}

        <WhyBox
          label="Comment cette analyse est produite"
          mechanism="Deux étages. Tous les chiffres sont calculés en Python sur l'historique entier : moyennes, corrélations de Pearson décalées d'un jour, taux de réalisation, écart GAD-7 comparé au seuil de signification clinique. Le modèle ne calcule rien — il interprète et rédige, uniquement à partir de ces chiffres et des extraits de fiches, et doit citer ses sources."
          evidenceLevel="A"
          sources={[
            {
              label: "J Affect Disord 2023 — l'amélioration du sommeil médie l'amélioration de l'anxiété (analyse de médiation sur deux grands essais randomisés)",
              url: 'https://www.sciencedirect.com/science/article/pii/S0165032723008194',
            },
            {
              label: 'Toussaint et al., J Affect Disord 2020 — différence minimale cliniquement importante du GAD-7',
              url: 'https://pubmed.ncbi.nlm.nih.gov/32090765/',
            },
          ]}
          contraindications="Une analyse sur moins de 14 jours renseignés dit peu de choses : les corrélations demandent au minimum 6 paires de jours par signal."
        />
      </div>

      <div className="w-foot">
        <button className="btn-primary" disabled={busy} onClick={() => onSubmit({ scope })}>
          Lancer l'analyse
        </button>
        <button className="btn-sm" disabled={busy} onClick={onSkip}>
          Pas maintenant
        </button>
      </div>
    </>
  )
}
