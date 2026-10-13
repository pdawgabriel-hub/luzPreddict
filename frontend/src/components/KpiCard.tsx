import type { ReactNode } from 'react'
import styles from './KpiCard.module.css'

type Props = {
  label: string
  value: ReactNode
  unit?: string
  detail?: ReactNode
  badge?: ReactNode
  dark?: boolean // la tarjeta destacada (precio de ahora)
}

/** Tarjeta de cifra clave: etiqueta, valor grande con unidad y detalle. */
export function KpiCard({ label, value, unit, detail, badge, dark = false }: Props) {
  return (
    <div className={styles.card} data-dark={dark || undefined}>
      <span className={styles.label}>{label}</span>
      <span className={`num ${styles.value}`}>
        {value}
        {unit && <span className={styles.unit}> {unit}</span>}
      </span>
      {badge}
      {detail && <span className={styles.detail}>{detail}</span>}
    </div>
  )
}
