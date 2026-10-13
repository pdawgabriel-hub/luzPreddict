import { useCallback, useEffect, useState } from 'react'
import { ApiError } from '../api/client'

export type ApiState<T> =
  | { status: 'loading'; previous?: T } // `previous`: los últimos datos, para no vaciar la pantalla al recargar
  | { status: 'error'; error: ApiError }
  | { status: 'success'; data: T }

type Result<T> = { key: string } & ({ data: T } | { error: ApiError })

function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error
  return new ApiError(0, 'unknown', error instanceof Error ? error.message : String(error))
}

/**
 * Carga datos de la API y da su estado: cargando, error o datos, más `reload` para reintentar.
 *
 * `load` se vuelve a llamar cuando cambian `deps` o se pide `reload`; la petición anterior se
 * cancela. El estado de carga se deduce de si el último resultado es de la petición actual,
 * sin cambiar el estado dentro del efecto.
 */
export function useApi<T>(load: (signal: AbortSignal) => Promise<T>, deps: readonly unknown[]): ApiState<T> & { reload: () => void } {
  const [attempt, setAttempt] = useState(0)
  const [result, setResult] = useState<Result<T> | null>(null)
  const key = `${attempt}:${JSON.stringify(deps)}`

  useEffect(() => {
    const controller = new AbortController()
    load(controller.signal).then(
      (data) => setResult({ key, data }),
      (error: unknown) => {
        if (!controller.signal.aborted) setResult({ key, error: toApiError(error) })
      },
    )
    return () => controller.abort()
    // `load` cambia en cada render; lo que decide si hay que volver a cargar es `key`
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])

  const reload = useCallback(() => setAttempt((n) => n + 1), [])

  if (result?.key !== key) {
    return result && 'data' in result ? { status: 'loading', previous: result.data, reload } : { status: 'loading', reload }
  }
  if ('error' in result) return { status: 'error', error: result.error, reload }
  return { status: 'success', data: result.data, reload }
}
