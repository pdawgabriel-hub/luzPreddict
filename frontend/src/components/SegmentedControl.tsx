import styles from './SegmentedControl.module.css'

export type Segment<T extends string> = { value: T; label: string; disabled?: boolean }

type Props<T extends string> = {
  label: string // nombre del grupo para lectores de pantalla
  segments: Segment<T>[]
  value: T
  onChange: (value: T) => void
}

/** Botones excluyentes (Hoy / Mañana / Comparar). */
export function SegmentedControl<T extends string>({ label, segments, value, onChange }: Props<T>) {
  return (
    <div role="group" aria-label={label} className={styles.group}>
      {segments.map((segment) => (
        <button
          key={segment.value}
          type="button"
          className={styles.segment}
          aria-pressed={segment.value === value}
          disabled={segment.disabled}
          onClick={() => onChange(segment.value)}
        >
          {segment.label}
        </button>
      ))}
    </div>
  )
}
