import { getJson, usingMocks } from '../api/client'
import type { Health } from '../api/types'
import { PageHeader } from '../components/PageHeader'
import { ErrorState, LoadingState } from '../components/States'
import { useApi } from '../hooks/useApi'

// Provisional: comprueba la conexión con la API. El panel real llega en el 7.7.
export default function Panel() {
  const health = useApi((signal) => getJson<Health>('/health', undefined, signal), [])

  return (
    <>
      <PageHeader eyebrow="PVPC · Península" title="Precio de la luz hoy y mañana">
        Precio de la luz (PVPC) publicado por REE y previsión para mañana.
      </PageHeader>
      {health.status === 'loading' && <LoadingState label="Conectando con la API…" />}
      {health.status === 'error' && <ErrorState error={health.error} onRetry={health.reload} />}
      {health.status === 'success' && (
        <p className="card">
          {usingMocks() ? 'Datos de ejemplo' : 'API conectada'} ({health.data.status}). Último día con precios:{' '}
          {health.data.prices.last_day ?? '—'}.
        </p>
      )}
    </>
  )
}
