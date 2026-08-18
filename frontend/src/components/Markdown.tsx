import type { ReactNode } from 'react'

/**
 * Rendu markdown minimal, volontairement sans dépendance : titres, listes,
 * tableaux, gras, italique, code, citations, séparateurs, et surtout les
 * références [1] du modèle, transformées en pastilles cliquables vers la liste
 * des citations.
 */
export default function Markdown({ text }: { text: string }) {
  return <div className="md">{renderBlocks(text)}</div>
}

function renderBlocks(text: string): ReactNode[] {
  const lines = text.replace(/\r\n/g, '\n').split('\n')
  const blocks: ReactNode[] = []
  let index = 0
  let key = 0

  while (index < lines.length) {
    const line = lines[index]

    if (!line.trim()) {
      index += 1
      continue
    }

    if (/^\s*(---|___|\*\*\*)\s*$/.test(line)) {
      blocks.push(<hr key={key++} />)
      index += 1
      continue
    }

    const heading = /^(#{1,4})\s+(.*)$/.exec(line)
    if (heading) {
      const level = heading[1].length
      const content = inline(heading[2])
      if (level <= 2) blocks.push(<h2 key={key++}>{content}</h2>)
      else if (level === 3) blocks.push(<h3 key={key++}>{content}</h3>)
      else blocks.push(<h4 key={key++}>{content}</h4>)
      index += 1
      continue
    }

    // Tableau : ligne d'en-tête suivie d'une ligne de séparation |---|
    if (line.includes('|') && index + 1 < lines.length && /^\s*\|?[\s:|-]+\|/.test(lines[index + 1])) {
      const header = splitRow(line)
      index += 2
      const rows: string[][] = []
      while (index < lines.length && lines[index].includes('|')) {
        rows.push(splitRow(lines[index]))
        index += 1
      }
      blocks.push(
        <table key={key++}>
          <thead>
            <tr>
              {header.map((cell, i) => (
                <th key={i}>{inline(cell)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i}>
                {row.map((cell, j) => (
                  <td key={j}>{inline(cell)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>,
      )
      continue
    }

    if (/^\s*>\s?/.test(line)) {
      const quote: string[] = []
      while (index < lines.length && /^\s*>\s?/.test(lines[index])) {
        quote.push(lines[index].replace(/^\s*>\s?/, ''))
        index += 1
      }
      blocks.push(<blockquote key={key++}>{inline(quote.join(' '))}</blockquote>)
      continue
    }

    if (/^\s*([-*+]|\d+\.)\s+/.test(line)) {
      const ordered = /^\s*\d+\.\s+/.test(line)
      const items: string[] = []
      while (index < lines.length && /^\s*([-*+]|\d+\.)\s+/.test(lines[index])) {
        items.push(lines[index].replace(/^\s*([-*+]|\d+\.)\s+/, ''))
        index += 1
        // Continuations indentées rattachées à l'item courant
        while (index < lines.length && /^\s{2,}\S/.test(lines[index]) && !/^\s*([-*+]|\d+\.)\s+/.test(lines[index])) {
          items[items.length - 1] += ' ' + lines[index].trim()
          index += 1
        }
      }
      const listItems = items.map((item, i) => <li key={i}>{inline(item)}</li>)
      blocks.push(ordered ? <ol key={key++}>{listItems}</ol> : <ul key={key++}>{listItems}</ul>)
      continue
    }

    const paragraph: string[] = []
    while (
      index < lines.length &&
      lines[index].trim() &&
      !/^(#{1,4})\s+/.test(lines[index]) &&
      !/^\s*([-*+]|\d+\.)\s+/.test(lines[index]) &&
      !/^\s*>\s?/.test(lines[index])
    ) {
      paragraph.push(lines[index])
      index += 1
    }
    blocks.push(<p key={key++}>{inline(paragraph.join(' '))}</p>)
  }

  return blocks
}

function splitRow(line: string): string[] {
  return line
    .replace(/^\s*\|/, '')
    .replace(/\|\s*$/, '')
    .split('|')
    .map((cell) => cell.trim())
}

/** Gras, italique, code inline, liens, et pastilles de citation [n]. */
function inline(text: string): ReactNode[] {
  const tokens: ReactNode[] = []
  const pattern =
    /(\*\*[^*]+\*\*)|(\*[^*]+\*)|(`[^`]+`)|(\[[^\]]+\]\([^)]+\))|(\[(\d{1,2})\])/g
  let cursor = 0
  let match: RegExpExecArray | null
  let key = 0

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > cursor) tokens.push(text.slice(cursor, match.index))
    const token = match[0]
    if (token.startsWith('**')) {
      tokens.push(<strong key={key++}>{token.slice(2, -2)}</strong>)
    } else if (token.startsWith('`')) {
      tokens.push(<code key={key++}>{token.slice(1, -1)}</code>)
    } else if (/^\[\d{1,2}\]$/.test(token)) {
      tokens.push(
        <sup key={key++} className="cite" title="Référence citée par l'analyse">
          {token.slice(1, -1)}
        </sup>,
      )
    } else if (token.startsWith('[')) {
      const link = /\[([^\]]+)\]\(([^)]+)\)/.exec(token)
      if (link) {
        tokens.push(
          <a key={key++} href={link[2]} target="_blank" rel="noreferrer noopener">
            {link[1]}
          </a>,
        )
      }
    } else {
      tokens.push(<em key={key++}>{token.slice(1, -1)}</em>)
    }
    cursor = match.index + token.length
  }
  if (cursor < text.length) tokens.push(text.slice(cursor))
  return tokens
}
