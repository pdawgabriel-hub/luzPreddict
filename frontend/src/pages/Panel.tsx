import { useEffect, useState } from 'react'
import { getJson, usingMocks } from '../api/client'
import type { Health } from '../api/types'
import { PageHeader } from '../components/PageHeader'

// Provisional: comprueba la conexión con la API. El panel real llega en el 7.7.

type ApiState = { kind: 'loading' } | { kind: 'ok'; health: Health } | { kind: 'error'; message: string }

export default function Panel() {
  const [api, setApi] = useState<ApiState>({ kind: 'loading' })

  useEffect(() => {
    const controller = new AbortController()
    getJson<Health>('/health', undefined, controller.signal)
      .then((health) => setApi({ kind: 'ok', health }))
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setApi({ kind: 'error', message: error instanceof Error ? error.message : String(error) })
        }
      })
    return () => controller.abort()
  }, [])

  return (
    <>
      <PageHeader eyebrow="PVPC · Península" title="Precio de la luz hoy y mañana">
        Precio de la luz (PVPC) publicado por REE y previsión para mañana.
      </PageHeader>
      <p role="status" className="card">
        {api.kind === 'loading' && 'Conectando con la API…'}
        {api.kind === 'ok' &&
          `${usingMocks() ? 'Datos de ejemplo' : 'API conectada'} (${api.health.status}). ` +
            `Último día con precios: ${api.health.prices.last_day ?? '—'}.`}
        {api.kind === 'error' && `Sin conexión con la API: ${api.message}. ¿Está arrancada con make api?`}
      </p>
    </>
  )
}
