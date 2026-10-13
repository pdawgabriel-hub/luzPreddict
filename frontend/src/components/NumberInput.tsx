import { useId, useState } from 'react'
import { formatNumber } from '../lib/format'
import styles from './NumberInput.module.css'

type Props = {
  label: string
  value: number
  onChange: (value: number) => void
  min: number // mínimo admitido (incluido)
  max: number
  decimals?: number // para mostrar el valor inicial y los límites
  unit?: string // en el mensaje de error: "Entre 0,1 y 15 kW"
  hint?: string
}

/**
 * Número con coma decimal ("2,5"), como se escribe en España. Guarda lo que se teclea y
 * solo avisa del cambio cuando el valor es válido; si no, lo marca y dice el rango admitido.
 */
export function NumberInput({ label, value, onChange, min, max, decimals = 1, unit, hint }: Props) {
  const show = (v: number) => formatNumber(v, Number.isInteger(v) ? 0 : decimals)
  const [text, setText] = useState(formatNumber(value, decimals))
  const inputId = useId()
  const hintId = useId()
  const errorId = useId()
  const parse = (raw: string) => (raw.trim() === '' ? NaN : Number(raw.replace(',', '.')))
  const parsed = parse(text)
  const valid = parsed >= min && parsed <= max

  return (
    <div className={styles.field}>
      <label htmlFor={inputId} className={styles.label}>
        {label}
      </label>
      <input
        id={inputId}
        type="text"
        inputMode="decimal"
        className={styles.input}
        value={text}
        aria-invalid={!valid}
        aria-describedby={valid ? (hint ? hintId : undefined) : errorId}
        onChange={(event) => {
          setText(event.target.value)
          const next = parse(event.target.value)
          if (next >= min && next <= max) onChange(next)
        }}
      />
      {valid ? (
        hint && (
          <span id={hintId} className={styles.hint}>
            {hint}
          </span>
        )
      ) : (
        <span id={errorId} className={styles.error}>
          Entre {show(min)} y {show(max)}
          {unit && ` ${unit}`}
        </span>
      )}
    </div>
  )
}
