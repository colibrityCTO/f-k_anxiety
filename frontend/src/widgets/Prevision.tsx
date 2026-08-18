import { useEffect, useState } from 'react'
import WhyBox from '../components/WhyBox'
import type { WidgetProps } from '../components/WidgetHost'
import { api } from '../lib/api'
import type { ForecastPayload } from '../lib/types'

/**
 * La charge du jour et la fourchette de demain.
 *
 * Trois règles d'affichage, chacune contre un piège précis :
 *
 * **Deux chiffres séparés, jamais fusionnés.** L'anxiété déclarée est la vérité de
 * référence ; la charge est un cumul de facteurs. Un score composite unique étiqueté
 * « ton anxiété » se met à être surveillé pour lui-même — et un score qui monte est
 * anxiogène par construction.
 *
 * **Une fourchette, pas un point.** « Entre 4 et 7 » est une prévision. « 5,4 » est
 * une promesse, et une promesse ratée coûte la confiance dans tout le reste.
 *
 * **La fiabilité réelle est affichée, échecs compris.** Les prévisions sont figées en
 * base, donc on peut comparer ce qui avait été annoncé à ce qui est arrivé. Un modèle
 * dont on ne montre pas les erreurs est une décoration.
 */
export default function Prevision(_: WidgetProps) {
  const [data, setData] = useState<ForecastPayload | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .prevision()
      .then(setData)
      .catch((exception) =>
        setError(exception instanceof Error ? exception.message : 'Calcul impossible.'),
      )
  }, [])

  if (error) return <div className="w-body"><p className="error-text">{error}</p></div>
  if (!data) return <div className="w-body"><p className="dim">Calcul…</p></div>

  const { charge, prevision, historique } = data
  const beats = prevision?.validation.gagnant === 'regression'

  return (
    <div className="w-body">
      <div className="sum">
        <div>
          <span>Anxiété déclarée</span>
          <b>{data.anxiete_declaree ?? '—'}</b>
        </div>
        <div>
          <span>Charge du jour</span>
          <b>{charge.valeur ?? '—'}</b>
        </div>
      </div>
      <p className="tiny dim">
        Deux chiffres distincts. Le second n'est pas ton anxiété : c'est ce que la journée
        cumule comme facteurs de risque, pondérés par ce qui compte <b>chez toi</b>.
      </p>

      {charge.valeur === null && charge.raison && (
        <p className="frame-note">{charge.raison}</p>
      )}

      {charge.composantes.length > 0 && (
        <table className="tbl">
          <thead>
            <tr>
              <th>Facteur</th>
              <th>Poids chez toi</th>
              <th>Aujourd'hui</th>
            </tr>
          </thead>
          <tbody>
            {charge.composantes.map((component) => (
              <tr key={component.facteur}>
                <td>{component.facteur}</td>
                <td>{component.poids > 0 ? component.poids : '—'}</td>
                <td>
                  {component.actif === null
                    ? (component.note ?? '—')
                    : component.actif
                      ? 'oui'
                      : 'non'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {prevision && (
        <>
          <h4 className="sec">Demain</h4>
          <div className="range">
            <span>{prevision.interval_low}</span>
            <div className="range-bar">
              <div
                className="range-fill"
                style={{
                  left: `${prevision.interval_low * 10}%`,
                  width: `${(prevision.interval_high - prevision.interval_low) * 10}%`,
                }}
              />
            </div>
            <span>{prevision.interval_high}</span>
          </div>
          <p className="tiny dim">
            Modèle retenu : <b>{prevision.model}</b>.{' '}
            {beats
              ? 'Il fait mieux que de reporter la valeur du jour — vérifié en avance glissante.'
              : "Aucun calcul ne fait mieux que de reporter la valeur du jour chez toi, donc on ne fait pas semblant."}
          </p>
        </>
      )}

      {historique.n > 0 && (
        <>
          <h4 className="sec">Ce que les prévisions passées ont donné</h4>
          <div className="sum">
            <div>
              <span>Erreur moyenne</span>
              <b>{historique.mae}</b>
            </div>
            {historique.mae_persistance !== null && (
              <div>
                <span>Persistance</span>
                <b>{historique.mae_persistance}</b>
              </div>
            )}
            {historique.couverture !== null && (
              <div>
                <span>Dans la fourchette</span>
                <b>{Math.round(historique.couverture * 100)} %</b>
              </div>
            )}
            <div>
              <span>Prévisions notées</span>
              <b>{historique.n}</b>
            </div>
          </div>
          {historique.couverture !== null && historique.couverture < 0.8 && (
            <p className="frame-note">
              La fourchette est annoncée à 95 % et n'en couvre que{' '}
              {Math.round(historique.couverture * 100)} % : elle est mal calibrée, donc trop
              étroite. C'est affiché plutôt que corrigé en silence.
            </p>
          )}
        </>
      )}

      <WhyBox
        mechanism="La référence à battre n'est pas le hasard mais la persistance — « demain = aujourd'hui » — parce que l'essentiel de la variance d'un jour sur l'autre vient de l'autocorrélation. Le modèle personnel est validé en avance glissante : à chaque jour testé il n'est ajusté que sur les jours antérieurs, jamais sur le jour testé. S'il ne fait pas mieux que la persistance, il n'est pas utilisé. La fourchette est calibrée sur tes propres variations quotidiennes, pas sur un écart-type théorique."
        evidenceLevel="B"
        sources={[
          {
            label:
              'Digital Biomarkers of Anxiety Disorder Symptom Changes — R² robuste ≈ 0,75 au niveau du groupe, ≈ 0,39 au niveau individuel',
            url: 'https://pmc.ncbi.nlm.nih.gov/articles/PMC8858490/',
          },
        ]}
        data={[
          { label: 'Prédicteurs utilisés', value: prevision?.validation.prédicteurs.join(', ') ?? '—' },
          {
            label: 'Jours de test',
            value: String(prevision?.validation.n_test ?? 0),
          },
          {
            label: 'Erreur en validation',
            value:
              prevision?.validation.mae_regression === null ||
              prevision?.validation.mae_regression === undefined
                ? 'pas encore testable'
                : `modèle ${prevision.validation.mae_regression} · persistance ${prevision.validation.mae_persistance}`,
          },
        ]}
        contraindications="Ce n'est pas une annonce. Une prévision d'anxiété élevée n'est pas un événement décidé, et surveiller la courbe est exactement ce qu'il ne faut pas faire : la vigilance portée sur ses propres états les entretient. Aucune crise de panique n'est jamais prédite ici — ça n'aurait aucune fiabilité, et une prédiction anxiogène est auto-réalisatrice."
      />
    </div>
  )
}
