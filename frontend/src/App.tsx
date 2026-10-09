import { useEffect, useState } from 'react'
import { getJson, usingMocks } from './api/client'
import type { Health } from './api/types'

// Página provisional: comprueba que la web llega a la API (o a los datos de ejemplo).
// Las páginas reales llegan en los siguientes commits de la Fase 7.

type ApiState = { kind: 'loading' } | { kind: 'ok'; health: Health } | { kind: 'error'; message: string }

export default function App() {
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
    <main className="container" style={{ paddingBlock: 'var(--space-8) var(--space-14)', display: 'grid', gap: 'var(--space-6)' }}>
      <div style={{ display: 'grid', gap: 'var(--space-1)' }}>
        <p className="eyebrow">PVPC · Península</p>
        <h1>luzPreddict</h1>
        <p className="muted">Precio de la luz (PVPC) y previsión para mañana. Web en construcción.</p>
      </div>
      <p role="status" className="card">
        {api.kind === 'loading' && 'Conectando con la API…'}
        {api.kind === 'ok' &&
          `${usingMocks() ? 'Datos de ejemplo' : 'API conectada'} (${api.health.status}). ` +
            `Último día con precios: ${api.health.prices.last_day ?? '—'}.`}
        {api.kind === 'error' && `Sin conexión con la API: ${api.message}. ¿Está arrancada con make api?`}
      </p>
    </main>
  )
}
