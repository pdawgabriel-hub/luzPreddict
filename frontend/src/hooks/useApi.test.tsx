import { act, renderHook, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/client'
import { useApi } from './useApi'

/** Una carga que se resuelve cuando el test quiere, y registra la señal de cancelación. */
function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

describe('useApi', () => {
  it('pasa de cargando a datos', async () => {
    const { result } = renderHook(() => useApi(() => Promise.resolve(42), []))

    expect(result.current.status).toBe('loading')
    await waitFor(() => expect(result.current).toMatchObject({ status: 'success', data: 42 }))
  })

  it('un error de la API llega tal cual; cualquier otro, como ApiError "unknown"', async () => {
    const apiError = new ApiError(404, 'not_found', 'No hay precios')
    const { result: api } = renderHook(() => useApi(() => Promise.reject(apiError), []))
    const { result: other } = renderHook(() => useApi(() => Promise.reject(new TypeError('se rompió')), []))

    await waitFor(() => expect(api.current.status).toBe('error'))
    await waitFor(() => expect(other.current.status).toBe('error'))
    expect(api.current.status === 'error' && api.current.error).toBe(apiError)
    expect(other.current.status === 'error' && other.current.error).toMatchObject({ code: 'unknown', status: 0, message: 'se rompió' })
  })

  it('reload vuelve a cargar y conserva los datos anteriores mientras tanto', async () => {
    let calls = 0
    const pending = deferred<number>()
    const load = vi.fn(() => (++calls === 1 ? Promise.resolve(1) : pending.promise))
    const { result } = renderHook(() => useApi(load, []))
    await waitFor(() => expect(result.current.status).toBe('success'))

    act(() => result.current.reload())

    expect(result.current).toMatchObject({ status: 'loading', previous: 1 })
    await act(async () => pending.resolve(2))
    expect(result.current).toMatchObject({ status: 'success', data: 2 })
    expect(load).toHaveBeenCalledTimes(2)
  })

  it('al cambiar los parámetros cancela la petición anterior y descarta su resultado', async () => {
    const first = deferred<string>()
    const signals: AbortSignal[] = []
    const { result, rerender } = renderHook(
      ({ day }) =>
        useApi((signal) => {
          signals.push(signal)
          return day === 'lunes' ? first.promise : Promise.resolve(day)
        }, [day]),
      { initialProps: { day: 'lunes' } },
    )

    rerender({ day: 'martes' })
    await waitFor(() => expect(result.current).toMatchObject({ status: 'success', data: 'martes' }))
    expect(signals[0].aborted).toBe(true)

    await act(async () => first.resolve('lunes')) // llega tarde: no pisa a "martes"
    expect(result.current).toMatchObject({ status: 'success', data: 'martes' })
  })

  it('al desmontar cancela la petición en curso', () => {
    let signal: AbortSignal | undefined
    const { unmount } = renderHook(() =>
      useApi((s) => {
        signal = s
        return new Promise(() => {})
      }, []),
    )

    unmount()
    expect(signal?.aborted).toBe(true)
  })
})
