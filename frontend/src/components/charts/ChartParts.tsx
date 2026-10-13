import styles from './Charts.module.css'

export type LegendItem = { label: string; color: string; shape?: 'square' | 'line' | 'dashed' | 'band' }

/** Leyenda bajo el gráfico. */
export function Legend({ items }: { items: LegendItem[] }) {
  if (!items.length) return null
  return (
    <ul className={styles.legend}>
      {items.map((item) => (
        <li key={item.label}>
          <span className={styles.swatch} data-shape={item.shape ?? 'square'} style={{ color: item.color }} aria-hidden="true" />
          {item.label}
        </li>
      ))}
    </ul>
  )
}

/** Los datos del gráfico como tabla, solo para lectores de pantalla. */
export function DataTable({ caption, columns, rows }: { caption: string; columns: string[]; rows: string[][] }) {
  return (
    <table className="visually-hidden">
      <caption>{caption}</caption>
      <thead>
        <tr>
          {columns.map((column) => (
            <th key={column} scope="col">
              {column}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row[0]}>
            {row.map((cell, i) => (i === 0 ? <th key={i} scope="row">{cell}</th> : <td key={i}>{cell}</td>))}
          </tr>
        ))}
      </tbody>
    </table>
  )
}
