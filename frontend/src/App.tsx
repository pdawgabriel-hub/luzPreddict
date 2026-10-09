import { useEffect, useState } from 'react'

// Página provisional: comprueba que la web llega a la API a través del proxy de Vite.
// Las páginas reales llegan en los siguientes commits de la Fase 7.

type Health = {
  status: 'ok' | 'degraded'
  warnings: string[]
  prices: { last_day: string | null }
}

type ApiState = { kind: 'loading' } | { kind: 'ok'; health: Health } | { kind: 'error'; message: string }

export default function App() {
  const [api, setApi] = useState<ApiState>({ kind: 'loading' })

  useEffect(() => {
    const controller = new AbortController()
    fetch('/health', { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error(`La API respondió ${response.status}`)
        setApi({ kind: 'ok', health: (await response.json()) as Health })
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setApi({ kind: 'error', message: error instanceof Error ? error.message : String(error) })
        }
      })
    return () => controller.abort()
  }, [])

  return (
    <main style={{ fontFamily: 'system-ui, sans-serif', maxWidth: 640, margin: '48px auto', padding: '0 16px' }}>
      <h1>luzPreddict</h1>
      <p>Precio de la luz (PVPC) y previsión para mañana. Web en construcción.</p>
      <p>
        {api.kind === 'loading' && 'Conectando con la API…'}
        {api.kind === 'ok' &&
          `API conectada (${api.health.status}). Último día con precios: ${api.health.prices.last_day ?? '—'}.`}
        {api.kind === 'error' && `Sin conexión con la API: ${api.message}. ¿Está arrancada con make api?`}
      </p>
    </main>
  )
}
