import { Legend } from './ChartParts'
import styles from './Charts.module.css'
import { type Step, stepFor } from '../../lib/chart'

export type HeatmapRow = { key: string; label: string; values: (number | null)[] }

type Props = {
  caption: string
  columns: string[] // p. ej. las horas "0" … "23"
  rows: HeatmapRow[]
  steps: Step[]
  formatValue: (value: number) => string
  columnHeader?: string
}

/**
 * Mapa de calor como tabla HTML (días × horas): se puede recorrer con el teclado y con
 * lector de pantalla, y en el móvil se desplaza en horizontal.
 */
export function Heatmap({ caption, columns, rows, steps, formatValue, columnHeader = 'Día' }: Props) {
  return (
    <figure className={styles.figure}>
      <div className={styles.heatmapScroll} tabIndex={0} role="region" aria-label={caption}>
        <table className={styles.heatmap}>
          <caption className="visually-hidden">{caption}</caption>
          <thead>
            <tr>
              <th scope="col">
                <span className="visually-hidden">{columnHeader}</span>
              </th>
              {columns.map((column) => (
                <th key={column} scope="col">
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.key}>
                <th scope="row">{row.label}</th>
                {row.values.map((value, i) => (
                  <td
                    key={columns[i] ?? i}
                    data-empty={value === null || undefined}
                    style={value === null ? undefined : { background: stepFor(value, steps).color }}
                    title={value === null ? `${row.label}, ${columns[i]}: sin dato` : `${row.label}, ${columns[i]}: ${formatValue(value)}`}
                  >
                    <span className="visually-hidden">{value === null ? 'sin dato' : formatValue(value)}</span>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Legend items={steps.map((step) => ({ label: step.label, color: step.color }))} />
    </figure>
  )
}
