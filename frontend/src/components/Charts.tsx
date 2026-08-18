import { useMemo, useState } from 'react'

/**
 * Graphiques SVG monochromes, sans dépendance.
 *
 * Contrainte du design system : aucune couleur. L'identité des séries ne peut
 * donc pas reposer sur la teinte — elle repose sur le motif du trait (plein /
 * tirets), sur la légende, et sur l'étiquette directe du dernier point. Un seul
 * axe des ordonnées par graphique, jamais deux échelles. Grille réduite à des
 * filets fins, marques de 2 px, angles droits partout.
 */

export type Point = { label: string; value: number | null }
export type Series = { name: string; points: Point[]; dashed?: boolean }
export type Threshold = { at: number; label: string }

const PAD = { top: 18, right: 20, bottom: 26, left: 34 }
const DASH = '6 4'

function niceDate(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit' })
}

/** Segments continus : on ne relie jamais deux points de part et d'autre d'un trou. */
function toSegments(points: Point[]): { index: number; value: number }[][] {
  const segments: { index: number; value: number }[][] = []
  let current: { index: number; value: number }[] = []
  points.forEach((point, index) => {
    if (point.value === null || point.value === undefined) {
      if (current.length) segments.push(current)
      current = []
    } else {
      current.push({ index, value: point.value })
    }
  })
  if (current.length) segments.push(current)
  return segments
}

type LineChartProps = {
  title: string
  series: Series[]
  yMin?: number
  yMax?: number
  yLabel?: string
  height?: number
  thresholds?: Threshold[]
  unit?: string
}

export function LineChart({
  title,
  series,
  yMin = 0,
  yMax = 10,
  yLabel,
  height = 200,
  thresholds,
  unit = '',
}: LineChartProps) {
  const width = 640
  const [hover, setHover] = useState<number | null>(null)

  const count = Math.max(...series.map((s) => s.points.length), 1)
  const innerWidth = width - PAD.left - PAD.right
  const innerHeight = height - PAD.top - PAD.bottom
  const x = (index: number) =>
    PAD.left + (count <= 1 ? innerWidth / 2 : (index / (count - 1)) * innerWidth)
  const y = (value: number) =>
    PAD.top + innerHeight - ((value - yMin) / (yMax - yMin)) * innerHeight

  const ticks = useMemo(() => {
    const step = (yMax - yMin) / 4
    return [0, 1, 2, 3, 4].map((i) => yMin + i * step)
  }, [yMin, yMax])

  const labels = series[0]?.points.map((p) => p.label) ?? []
  const hasData = series.some((s) => s.points.some((p) => p.value !== null))

  if (!hasData) {
    return (
      <figure style={{ margin: 0 }}>
        <figcaption className="eyebrow">{title}</figcaption>
        <p className="small dim" style={{ marginBottom: 0 }}>
          Pas encore de données à tracer. Elles apparaîtront dès vos premiers check-in.
        </p>
      </figure>
    )
  }

  return (
    <figure style={{ margin: 0 }}>
      <figcaption className="eyebrow">
        {title}
        {yLabel ? ` — ${yLabel}` : ''}
      </figcaption>

      <svg
        className="chart"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={title}
        onMouseLeave={() => setHover(null)}
      >
        {/* Cadre net plutôt qu'une grille complète. */}
        <rect
          x={PAD.left}
          y={PAD.top}
          width={innerWidth}
          height={innerHeight}
          fill="none"
          stroke="var(--paper)"
          strokeWidth={2}
        />

        {ticks.map((tick, index) => (
          <g key={tick}>
            {index > 0 && index < ticks.length - 1 && (
              <line
                x1={PAD.left}
                x2={width - PAD.right}
                y1={y(tick)}
                y2={y(tick)}
                stroke="var(--paper)"
                strokeWidth={1}
                opacity={0.25}
              />
            )}
            <text
              x={PAD.left - 6}
              y={y(tick) + 3}
              textAnchor="end"
              fontSize="9"
              fill="var(--paper)"
              opacity={0.6}
            >
              {Number.isInteger(tick) ? tick : tick.toFixed(1)}
            </text>
          </g>
        ))}

        {/* Seuils : filets en tirets + étiquette, à gauche pour laisser la
            droite à l'étiquette du dernier point. */}
        {thresholds?.map((threshold) => (
          <g key={threshold.label}>
            <line
              x1={PAD.left}
              x2={width - PAD.right}
              y1={y(threshold.at)}
              y2={y(threshold.at)}
              stroke="var(--paper)"
              strokeWidth={1}
              strokeDasharray="2 4"
              opacity={0.75}
            />
            <text
              x={PAD.left + 5}
              y={y(threshold.at) - 4}
              fontSize="8"
              fill="var(--paper)"
              opacity={0.75}
              letterSpacing="1"
            >
              {threshold.label.toUpperCase()}
            </text>
          </g>
        ))}

        {labels.map((label, index) => {
          const every = Math.max(1, Math.ceil(count / 6))
          if (index % every !== 0 && index !== count - 1) return null
          return (
            <text
              key={`${label}-${index}`}
              x={x(index)}
              y={height - 8}
              textAnchor="middle"
              fontSize="9"
              fill="var(--paper)"
              opacity={0.6}
            >
              {niceDate(label)}
            </text>
          )
        })}

        {series.map((serie) =>
          toSegments(serie.points).map((segment, segmentIndex) => (
            <polyline
              key={`${serie.name}-${segmentIndex}`}
              fill="none"
              stroke="var(--paper)"
              strokeWidth={2}
              strokeDasharray={serie.dashed ? DASH : undefined}
              points={segment.map((point) => `${x(point.index)},${y(point.value)}`).join(' ')}
            />
          )),
        )}

        {/* Étiquette directe du dernier point uniquement. Décalage vertical par
            série, sinon deux valeurs identiques se superposent. */}
        {series.map((serie, serieIndex) => {
          const last = [...serie.points].reverse().find((p) => p.value !== null)
          if (!last) return null
          const index = serie.points.lastIndexOf(last)
          const cy = y(last.value as number)
          return (
            <g key={`last-${serie.name}`}>
              <rect x={x(index) - 4} y={cy - 4} width={8} height={8} fill="var(--paper)" />
              <text
                x={x(index) - 9}
                y={cy - 8 - serieIndex * 13}
                textAnchor="end"
                fontSize="11"
                fontWeight="700"
                fill="var(--paper)"
              >
                {last.value}
                {unit}
              </text>
            </g>
          )
        })}

        {hover !== null && (
          <line
            x1={x(hover)}
            x2={x(hover)}
            y1={PAD.top}
            y2={PAD.top + innerHeight}
            stroke="var(--paper)"
            strokeWidth={1}
          />
        )}
        {hover !== null &&
          series.map((serie) => {
            const point = serie.points[hover]
            if (!point || point.value === null) return null
            return (
              <rect
                key={`hover-${serie.name}`}
                x={x(hover) - 4}
                y={y(point.value) - 4}
                width={8}
                height={8}
                fill="var(--paper)"
              />
            )
          })}

        <rect
          x={PAD.left}
          y={PAD.top}
          width={innerWidth}
          height={innerHeight}
          fill="transparent"
          onMouseMove={(event) => {
            const bounds = event.currentTarget.getBoundingClientRect()
            const ratio = (event.clientX - bounds.left) / bounds.width
            setHover(Math.min(count - 1, Math.max(0, Math.round(ratio * (count - 1)))))
          }}
        />
      </svg>

      {hover !== null && labels[hover] && (
        <p className="breath-meta" style={{ textAlign: 'left', marginTop: 4 }}>
          {niceDate(labels[hover])} —{' '}
          {series
            .map((serie) => `${serie.name} ${serie.points[hover]?.value ?? '—'}${unit}`)
            .join(' · ')}
        </p>
      )}

      {series.length >= 2 && (
        <div className="chart-legend">
          {series.map((serie) => (
            <span key={serie.name}>
              <i className={`legend-swatch${serie.dashed ? ' legend-swatch-dash' : ''}`} />
              {serie.name}
            </span>
          ))}
        </div>
      )}
    </figure>
  )
}

type BarChartProps = {
  title: string
  points: Point[]
  yMax?: number
  height?: number
  unit?: string
}

export function BarChart({ title, points, yMax = 100, height = 140, unit = '%' }: BarChartProps) {
  const width = 640
  const [hover, setHover] = useState<number | null>(null)
  const innerWidth = width - PAD.left - PAD.right
  const innerHeight = height - PAD.top - PAD.bottom
  const barSpace = points.length ? innerWidth / points.length : innerWidth
  // 2 px de fond entre deux barres adjacentes.
  const barWidth = Math.max(2, barSpace - 2)

  if (!points.length) {
    return (
      <figure style={{ margin: 0 }}>
        <figcaption className="eyebrow">{title}</figcaption>
        <p className="small dim" style={{ marginBottom: 0 }}>
          Aucune activité tracée sur la période.
        </p>
      </figure>
    )
  }

  return (
    <figure style={{ margin: 0 }}>
      <figcaption className="eyebrow">{title}</figcaption>
      <svg
        className="chart"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={title}
        onMouseLeave={() => setHover(null)}
      >
        <line
          x1={PAD.left}
          x2={width - PAD.right}
          y1={PAD.top + innerHeight}
          y2={PAD.top + innerHeight}
          stroke="var(--paper)"
          strokeWidth={2}
        />
        {points.map((point, index) => {
          const value = point.value ?? 0
          const barHeight = Math.max(0, (value / yMax) * innerHeight)
          const active = hover === index
          return (
            <rect
              key={`${point.label}-${index}`}
              x={PAD.left + index * barSpace + 1}
              y={PAD.top + innerHeight - barHeight}
              width={barWidth}
              height={barHeight}
              fill={active ? 'var(--paper)' : 'none'}
              stroke="var(--paper)"
              strokeWidth={2}
              onMouseEnter={() => setHover(index)}
            />
          )
        })}
      </svg>
      <p className="breath-meta" style={{ textAlign: 'left', marginTop: 4 }}>
        {hover !== null
          ? `${niceDate(points[hover].label)} — ${points[hover].value ?? 0}${unit}`
          : `0 à ${yMax}${unit} par jour`}
      </p>
    </figure>
  )
}

/** Seuils du GAD-7 : 5 / 10 / 15 (léger / modéré / sévère). */
export const GAD7_THRESHOLDS: Threshold[] = [
  { at: 5, label: 'léger 5' },
  { at: 10, label: 'modéré 10' },
  { at: 15, label: 'sévère 15' },
]
