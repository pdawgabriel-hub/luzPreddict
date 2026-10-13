import { DataTable, Legend, type LegendItem } from './ChartParts'
import styles from './Charts.module.css'
import { useWidth } from '../../hooks/useWidth'
import { bandPath, linePath } from '../../lib/chart'
import { extent, labelIndices, linearScale, niceTicks } from '../../lib/scale'

export type Series = {
  key: string
  label: string
  color: string
  values: (number | null)[] // null: hueco (p. ej. previsión sin precio real todavía)
  dashed?: boolean
}

export type Band = { label: string; color: string; lower: (number | null)[]; upper: (number | null)[] }

type Props = {
  labels: string[] // eje X, uno por punto
  series: Series[]
  ariaLabel: string
  formatTick: (value: number) => string
  formatValue: (value: number) => string // para la tabla de datos
  band?: Band // banda de fondo: mínimo–máximo o diferencia entre previsión y real
  height?: number
  xLabel?: string // cabecera de la primera columna de la tabla
  zeroBased?: boolean
}

const MARGIN = { top: 10, right: 8, bottom: 22, left: 44 }

/** Líneas sobre un eje común (previsión frente a real, evolución diaria…). */
export function LineChart({ labels, series, ariaLabel, formatTick, formatValue, band, height = 240, xLabel = 'Hora', zeroBased = false }: Props) {
  const [ref, width] = useWidth<HTMLDivElement>()
  const plotWidth = Math.max(width - MARGIN.left - MARGIN.right, 1)
  const plotHeight = height - MARGIN.top - MARGIN.bottom
  const all = [...series.flatMap((s) => s.values), ...(band ? [...band.lower, ...band.upper] : [])]
  const [low, high] = extent(all)
  const ticks = niceTicks(zeroBased ? Math.min(0, low) : low, high)
  const y = linearScale([ticks[0], ticks[ticks.length - 1]], [plotHeight, 0])
  const x = linearScale([0, Math.max(labels.length - 1, 1)], [0, plotWidth])
  const xs = labels.map((_, i) => x(i))
  const scaled = (values: (number | null)[]) => values.map((v) => (v === null ? null : y(v)))
  const shown = new Set(labelIndices(labels.length, plotWidth, 40))

  const legend: LegendItem[] = [
    ...series.map((s) => ({ label: s.label, color: s.color, shape: s.dashed ? ('dashed' as const) : ('line' as const) })),
    ...(band ? [{ label: band.label, color: band.color, shape: 'band' as const }] : []),
  ]

  return (
    <figure className={styles.figure}>
      <div ref={ref} className={styles.plot}>
        <svg width={width} height={height} role="img" aria-label={ariaLabel}>
          <g transform={`translate(${MARGIN.left},${MARGIN.top})`}>
            {ticks.map((tick) => (
              <g key={tick} className={styles.gridLine}>
                <line x1={0} x2={plotWidth} y1={y(tick)} y2={y(tick)} />
                <text x={-8} y={y(tick)} dy="0.32em" textAnchor="end">
                  {formatTick(tick)}
                </text>
              </g>
            ))}
            {band && <path data-testid="band" d={bandPath(xs, scaled(band.lower), scaled(band.upper))} style={{ fill: band.color }} />}
            {series.map((s) => (
              <path
                key={s.key}
                data-testid={`line-${s.key}`}
                className={styles.line}
                d={linePath(xs.map((px, i) => [px, scaled(s.values)[i]]))}
                strokeDasharray={s.dashed ? '6 4' : undefined}
                style={{ stroke: s.color }}
              />
            ))}
            <line className={styles.axis} x1={0} x2={plotWidth} y1={plotHeight} y2={plotHeight} />
            {labels.map((label, i) =>
              shown.has(i) ? (
                <text key={`${label}-${i}`} className={styles.tickLabel} x={xs[i]} y={plotHeight + 16} textAnchor="middle">
                  {label}
                </text>
              ) : null,
            )}
          </g>
        </svg>
      </div>
      <Legend items={legend} />
      <DataTable
        caption={ariaLabel}
        columns={[xLabel, ...series.map((s) => s.label)]}
        rows={labels.map((label, i) => [label, ...series.map((s) => (s.values[i] === null ? '—' : formatValue(s.values[i] as number)))])}
      />
    </figure>
  )
}
