import type { ApiError } from '../api/client'
import { errorMessage } from '../lib/errors'
import styles from './States.module.css'

/** Mientras llegan los datos. */
export function LoadingState({ label = 'Cargando datos…' }: { label?: string }) {
  return (
    <div role="status" aria-live="polite" className={styles.loading}>
      <span className={styles.spinner} aria-hidden="true" />
      {label}
    </div>
  )
}

type ErrorProps = {
  error: ApiError
  onRetry?: () => void
  title?: string
}

/** Error con el motivo, el botón de reintentar y el id de la petición (para buscarla en los logs). */
export function ErrorState({ error, onRetry, title = 'No se han podido cargar los datos' }: ErrorProps) {
  return (
    <div role="alert" className={styles.error}>
      <p className={styles.errorTitle}>{title}</p>
      <p>{errorMessage(error)}</p>
      <div className={styles.errorActions}>
        {onRetry && (
          <button type="button" className={styles.retry} onClick={onRetry}>
            Reintentar
          </button>
        )}
        {error.requestId && <span className={styles.requestId}>Id de la petición: {error.requestId}</span>}
      </div>
    </div>
  )
}
