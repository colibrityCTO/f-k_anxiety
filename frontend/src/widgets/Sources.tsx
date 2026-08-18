import { useEffect, useState } from 'react'
import Markdown from '../components/Markdown'
import type { WidgetProps } from '../components/WidgetHost'
import { api } from '../lib/api'
import type { KbDoc, KbDocDetail } from '../lib/types'

/** Le corpus, consultable. C'est exactement ce que l'assistant lit — rien d'autre. */
export default function Sources(_props: WidgetProps) {
  const [docs, setDocs] = useState<KbDoc[]>([])
  const [open, setOpen] = useState<KbDocDetail | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    api.knowledge().then(setDocs).catch(() => undefined)
  }, [])

  async function openDoc(docId: string) {
    setLoading(true)
    try {
      setOpen(await api.knowledgeDoc(docId))
    } finally {
      setLoading(false)
    }
  }

  if (open) {
    return (
      <div className="w-body">
        <button className="btn-sm" onClick={() => setOpen(null)}>
          ← Toutes les fiches
        </button>
        <h3 style={{ margin: 'var(--g2) 0 var(--g1)' }}>{open.title}</h3>
        <p className="tiny dim">
          {open.evidence_level ? `Preuve ${open.evidence_level}` : ''} {open.category ?? ''}
        </p>
        <ul className="source-list" style={{ marginBottom: 'var(--g2)' }}>
          {open.sources.map((source, index) => (
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
        <div className="divider" />
        <Markdown text={open.content} />
      </div>
    )
  }

  return (
    <div className="w-body">
      {docs.length === 0 && <p className="small dim">Corpus vide — lance l'ingestion côté serveur.</p>}
      <ul className="list-reset">
        {docs.map((doc) => (
          <li
            key={doc.doc_id}
            style={{ borderBottom: '1px solid rgba(255,255,255,.35)', padding: '10px 0' }}
          >
            <button
              className="btn-sm"
              style={{ border: 0, padding: 0, textAlign: 'left', letterSpacing: 0, textTransform: 'none', fontSize: '0.9375rem', fontWeight: 500 }}
              disabled={loading}
              onClick={() => openDoc(doc.doc_id)}
            >
              {doc.title}
            </button>{' '}
            {doc.evidence_level && <span className="badge">preuve {doc.evidence_level}</span>}
          </li>
        ))}
      </ul>
    </div>
  )
}
