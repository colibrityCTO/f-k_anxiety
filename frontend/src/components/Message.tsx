import { useState } from 'react'
import Markdown from './Markdown'
import type { ThreadItem } from '../lib/types'

/**
 * Un message est une fenêtre. Celle de l'assistant est un cadre ouvert, celle de
 * l'utilisateur un bloc plein inversé : vide contre plein, sans une seule couleur.
 *
 * Les réponses pré-choisies sont attachées au message de l'assistant, jamais dans
 * une barre permanente. Elles disparaissent dès qu'un choix est fait, puisque le
 * choix devient un message dans le fil.
 */
export default function Message({
  item,
  busy,
  onChoose,
}: {
  item: ThreadItem
  busy: boolean
  onChoose: (text: string) => void
}) {
  const mine = item.role === 'user'
  const [used, setUsed] = useState(false)
  const suggestions = mine || used ? [] : item.suggestions

  return (
    <div className={`msg${mine ? ' msg-me' : ''}`}>
      {mine ? <p>{item.content}</p> : <Markdown text={item.content ?? ''} />}

      {item.citations.length > 0 && !mine && <Citations item={item} />}

      {suggestions.length > 0 && (
        <div className="msg-actions">
          {suggestions.map((label) => (
            <button
              key={label}
              className="btn-sm"
              disabled={busy}
              onClick={() => {
                setUsed(true)
                onChoose(label)
              }}
            >
              {label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function Citations({ item }: { item: ThreadItem }) {
  return (
    <details className="why">
      <summary>Sources de cette réponse</summary>
      <div className="why-body">
        {item.citations.map((citation, index) => (
          <div className="why-section" key={citation.doc_id}>
            <h4>
              [{index + 1}] {citation.titre}
              {citation.niveau_de_preuve ? ` · preuve ${citation.niveau_de_preuve}` : ''}
            </h4>
            <ul className="source-list">
              {citation.sources.slice(0, 3).map((source, i) => (
                <li key={i}>
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
        ))}
        {item.engine && <p className="tiny dim">Rédigé par {item.engine}.</p>}
      </div>
    </details>
  )
}
