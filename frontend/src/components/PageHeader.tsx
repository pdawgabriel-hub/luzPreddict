import type { ReactNode } from 'react'
import { usePageTitle } from '../hooks/usePageTitle'
import styles from './PageHeader.module.css'

type Props = {
  title: string
  eyebrow?: string
  aside?: ReactNode // a la derecha en escritorio (p. ej. "Actualizado a las…")
  children?: ReactNode // entradilla bajo el título
}

/** Cabecera de cada página: etiqueta, título (h1) y entradilla. También pone el título de la pestaña. */
export function PageHeader({ title, eyebrow, aside, children }: Props) {
  usePageTitle(title)
  return (
    <div className={styles.header}>
      <div className={styles.text}>
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h1>{title}</h1>
        {children && <div className={`muted ${styles.intro}`}>{children}</div>}
      </div>
      {aside && <div className={`muted ${styles.aside}`}>{aside}</div>}
    </div>
  )
}
