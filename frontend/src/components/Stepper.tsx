import { useId } from 'react'
import styles from './Stepper.module.css'

type Props = {
  label: string
  value: number
  onChange: (value: number) => void
  min: number
  max: number
  format?: (value: number) => string // p. ej. 7 → "07:00"
  decrementLabel?: string
  incrementLabel?: string
}

/** Valor con botones − y + (horas, usos por semana…). Los límites desactivan el botón. */
export function Stepper({ label, value, onChange, min, max, format = String, decrementLabel = 'Menos', incrementLabel = 'Más' }: Props) {
  const id = useId()
  return (
    <div className={styles.field}>
      <span id={id} className={styles.label}>
        {label}
      </span>
      <div role="group" aria-labelledby={id} className={styles.stepper}>
        <button type="button" aria-label={`${label}: ${decrementLabel.toLowerCase()}`} disabled={value <= min} onClick={() => onChange(value - 1)}>
          −
        </button>
        <output className="num" aria-live="polite">
          {format(value)}
        </output>
        <button type="button" aria-label={`${label}: ${incrementLabel.toLowerCase()}`} disabled={value >= max} onClick={() => onChange(value + 1)}>
          +
        </button>
      </div>
    </div>
  )
}
