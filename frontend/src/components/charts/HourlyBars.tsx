import { DataTable, Legend, type LegendItem } from './ChartParts'
import styles from './Charts.module.css'
import { useWidth } from '../../hooks/useWidth'
import { labelIndices, linearScale, niceTicks } from '../../lib/scale'

export type Bar = {
  key: string
  label: string // eje X, p. ej. "13"
  name: string // nombre completo, p. ej. "13–14 h"
  value: number
  display: string // valor formateado, p. ej. "0,049 €/kWh"
  color: string // un token: 'var(--color-price-3)'
  current?: boolean // la hora actual, con borde
}

type Props = {
  bars: Bar[]
  ariaLabel: string // resumen para lectores de pantalla
  formatTick: (value: number) => string
  height?: number
  legend?: LegendItem[]
  valueLabel?: string // cabecera de la columna de valores en la tabla
}

const MARGIN = { top: 8, right: 4, bottom: 22, left: 44 }

/** Barras hora a hora (precio de un día, previsión, error por hora…). */
export function HourlyBars({ bars, ariaLabel, formatTick, height = 220, legend = [], valueLabel = 'Valor' }: Props) {
  const [ref, width] = useWidth<HTMLDivElement>()
  const plotWidth = Math.max(width - MARGIN.left - MARGIN.right, 1)
  const plotHeight = height - MARGIN.top - MARGIN.bottom
  const max = Math.max(0, ...bars.map((b) => b.value))
  const min = Math.min(0, ...bars.map((b) => b.value))
  const ticks = niceTicks(min, max)
  const y = linearScale([ticks[0], ticks[ticks.length - 1]], [plotHeight, 0])
  const slot = plotWidth / Math.max(bars.length, 1)
  const gap = Math.min(4, slot * 0.2)
  const labels = new Set(labelIndices(bars.length, plotWidth, 28))

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
            {bars.map((bar, i) => {
              const top = y(Math.max(bar.value, 0))
              return (
                <rect
                  key={bar.key}
                  data-testid="bar"
                  className={styles.bar}
                  data-current={bar.current || undefined}
                  x={i * slot + gap / 2}
                  y={top}
                  width={Math.max(slot - gap, 1)}
                  height={Math.max(Math.abs(y(bar.value) - y(0)), 1)}
                  rx={2}
                  style={{ fill: bar.color }}
                >
                  <title>{`${bar.name}: ${bar.display}`}</title>
                </rect>
              )
            })}
            <line className={styles.axis} x1={0} x2={plotWidth} y1={y(0)} y2={y(0)} />
            {bars.map((bar, i) =>
              labels.has(i) ? (
                <text key={bar.key} className={styles.tickLabel} x={i * slot + slot / 2} y={plotHeight + 16} textAnchor="middle">
                  {bar.label}
                </text>
              ) : null,
            )}
          </g>
        </svg>
      </div>
      <Legend items={legend} />
      <DataTable caption={ariaLabel} columns={['Hora', valueLabel]} rows={bars.map((b) => [b.name, b.display])} />
    </figure>
  )
}
