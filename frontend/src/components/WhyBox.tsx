import type { SourceRef } from '../lib/types'

const EVIDENCE = {
  A: 'Niveau A — essais randomisés ou recommandation officielle',
  B: 'Niveau B — preuve prometteuse mais partielle',
  C: 'Niveau C — consensus clinique',
} as const

/**
 * Le panneau qui tient la promesse « je comprends d'où ça sort ». Quatre choses,
 * dans cet ordre : le mécanisme, le niveau de preuve, les références
 * vérifiables, et les données personnelles qui ont déclenché la proposition.
 */
export default function WhyBox({
  mechanism,
  evidenceLevel,
  sources = [],
  contraindications,
  data,
  label = "D'où ça sort",
}: {
  mechanism?: string | null
  evidenceLevel?: string | null
  sources?: SourceRef[]
  contraindications?: string | null
  data?: { label: string; value: string }[]
  label?: string
}) {
  return (
    <details className="why">
      <summary>{label}</summary>
      <div className="why-body">
        {mechanism && (
          <div className="why-section">
            <h4>Par quel mécanisme ça agit</h4>
            <p>{mechanism}</p>
          </div>
        )}
        {evidenceLevel && (
          <div className="why-section">
            <h4>Niveau de preuve</h4>
            <p>{EVIDENCE[evidenceLevel as keyof typeof EVIDENCE] ?? evidenceLevel}</p>
          </div>
        )}
        {data && data.length > 0 && (
          <div className="why-section">
            <h4>Tes données qui ont déclenché ça</h4>
            <table>
              <tbody>
                {data.map((row) => (
                  <tr key={row.label}>
                    <th scope="row">{row.label}</th>
                    <td className="mono">{row.value}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {sources.length > 0 && (
          <div className="why-section">
            <h4>Références</h4>
            <ul className="source-list">
              {sources.map((source, index) => (
                <li key={index}>
                  {source.url ? (
                    <a href={source.url} target="_blank" rel="noreferrer noopener">
                      {source.label}
                    </a>
                  ) : (
                    source.label
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}
        {contraindications && (
          <div className="why-section">
            <h4>Précautions</h4>
            <p>{contraindications}</p>
          </div>
        )}
      </div>
    </details>
  )
}
