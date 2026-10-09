import { getJson, usingMocks } from '../api/client'
import type { Health } from '../api/types'
import { useApi } from '../hooks/useApi'
import styles from './StaleDataBanner.module.css'

/**
 * Aviso de datos desactualizados (/health en estado "degraded"), p. ej. si la tarea
 * diaria no ha podido traer los precios de hoy. Si /health falla no muestra nada:
 * cada página ya enseña su propio error.
 */
export function StaleDataBanner() {
  const health = useApi((signal) => getJson<Health>('/health', undefined, signal), [])

  return (
    <>
      {usingMocks() && (
        <p role="status" className={`${styles.banner} ${styles.info}`}>
          Estás viendo <strong>datos de ejemplo</strong>: la web no está conectada a la API.
        </p>
      )}
      {health.status === 'success' && health.data.status === 'degraded' && (
        <div role="status" className={`${styles.banner} ${styles.warning}`}>
          <p>
            <strong>Los datos pueden estar desactualizados.</strong>
          </p>
          <ul>
            {health.data.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      )}
    </>
  )
}
