import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, RETRY_DELAYS_MS, TIMEOUT_MS, getJson, postJson, withQuery } from './client'

function respond(status: number, body: unknown) {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status }))
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('cliente de la API', () => {
  it('construye la query string sin los parámetros vacíos', () => {
    expect(withQuery('/v1/prices', { date: '2026-10-06', start: undefined, end: null, hours: 0 })).toBe(
      '/v1/prices?date=2026-10-06&hours=0',
    )
    expect(withQuery('/health')).toBe('/health')
  })

  it('devuelve el JSON de una respuesta correcta', async () => {
    const fetchMock = respond(200, { status: 'ok' })

    await expect(getJson('/health')).resolves.toEqual({ status: 'ok' })
    expect(fetchMock).toHaveBeenCalledWith('/health', expect.objectContaining({ method: 'GET' }))
  })

  it('envía el cuerpo de los POST como JSON', async () => {
    const fetchMock = respond(200, {})

    await postJson('/api/tools/simulate', { appliance: 'lavadora' })

    const [, init] = fetchMock.mock.calls[0]
    expect(init).toMatchObject({ method: 'POST', body: '{"appliance":"lavadora"}' })
    expect(init.headers).toEqual({ 'Content-Type': 'application/json' })
  })

  it('convierte el formato de error común en un ApiError', async () => {
    respond(422, {
      error: {
        code: 'validation_error',
        message: 'Parámetros no válidos',
        request_id: 'abc123',
        details: [{ field: 'query.date', message: 'Fecha no válida', type: 'value_error' }],
      },
    })

    const error = await getJson('/v1/prices').catch((e: unknown) => e)

    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ status: 422, code: 'validation_error', requestId: 'abc123', message: 'Parámetros no válidos' })
    expect((error as ApiError).details[0].field).toBe('query.date')
  })

  it('un error sin el formato común también es un ApiError', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('Bad Gateway', { status: 502 })))

    await expect(getJson('/health')).rejects.toMatchObject({ status: 502, code: 'http_error' })
  })

  it('con VITE_USE_MOCKS=1 no llama a la API', async () => {
    vi.stubEnv('VITE_USE_MOCKS', '1')
    const fetchMock = respond(500, {})

    const health = await getJson<{ status: string }>('/health')

    expect(health.status).toBe('ok')
    expect(fetchMock).not.toHaveBeenCalled()
  })
})

const json = (status: number, body: unknown) => () => Promise.resolve(new Response(JSON.stringify(body), { status }))
const UNAVAILABLE = { error: { code: 'service_unavailable', message: 'Base de datos no disponible', request_id: 'r1', details: [] } }

describe('reintentos y tiempo máximo', () => {
  beforeEach(() => vi.useFakeTimers())

  it('reintenta un 503 (p. ej. Neon despertando) y devuelve la respuesta buena', async () => {
    const fetchMock = vi.fn().mockImplementationOnce(json(503, UNAVAILABLE)).mockImplementationOnce(json(200, { status: 'ok' }))
    vi.stubGlobal('fetch', fetchMock)

    const result = getJson('/health')
    await vi.advanceTimersByTimeAsync(RETRY_DELAYS_MS[0])

    await expect(result).resolves.toEqual({ status: 'ok' })
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('se rinde tras tres intentos y da el último error', async () => {
    const fetchMock = vi.fn().mockImplementation(json(503, UNAVAILABLE))
    vi.stubGlobal('fetch', fetchMock)

    const result = getJson('/health').catch((e: unknown) => e)
    await vi.advanceTimersByTimeAsync(RETRY_DELAYS_MS.reduce((a, b) => a + b, 0))

    expect(await result).toMatchObject({ status: 503, code: 'service_unavailable' })
    expect(fetchMock).toHaveBeenCalledTimes(1 + RETRY_DELAYS_MS.length)
  })

  it('sin red, reintenta y acaba en un error "network"', async () => {
    const fetchMock = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'))
    vi.stubGlobal('fetch', fetchMock)

    const result = getJson('/health').catch((e: unknown) => e)
    await vi.advanceTimersByTimeAsync(10_000)

    expect(await result).toMatchObject({ status: 0, code: 'network', message: 'No se puede conectar con la API' })
    expect(fetchMock).toHaveBeenCalledTimes(3)
  })

  it.each([
    [404, 'not_found'],
    [422, 'validation_error'],
  ])('no reintenta un %i: repetirlo daría lo mismo', async (status, code) => {
    const fetchMock = vi.fn().mockImplementation(json(status, { error: { code, message: 'x', request_id: null, details: [] } }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(getJson('/v1/prices')).rejects.toMatchObject({ status })
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('no reintenta los POST', async () => {
    const fetchMock = vi.fn().mockImplementation(json(503, UNAVAILABLE))
    vi.stubGlobal('fetch', fetchMock)

    await expect(postJson('/api/tools/plan', {})).rejects.toMatchObject({ status: 503 })
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('corta un intento que tarda demasiado', async () => {
    // AbortSignal.timeout usa un temporizador interno: se sustituye por uno que los temporizadores falsos controlan
    vi.spyOn(AbortSignal, 'timeout').mockImplementation((ms: number) => {
      const controller = new AbortController()
      setTimeout(() => controller.abort(new DOMException('Tiempo agotado', 'TimeoutError')), ms)
      return controller.signal
    })
    const fetchMock = vi.fn().mockImplementation(
      (_url: string, init: RequestInit) =>
        new Promise((_resolve, reject) => init.signal?.addEventListener('abort', () => reject(init.signal?.reason))),
    )
    vi.stubGlobal('fetch', fetchMock)

    const result = getJson('/health').catch((e: unknown) => e)
    await vi.advanceTimersByTimeAsync(3 * TIMEOUT_MS + 2_000)

    expect(await result).toMatchObject({ code: 'timeout', message: 'La API tarda demasiado en responder' })
    expect(fetchMock).toHaveBeenCalledTimes(3)
  })

  it('si quien pide los datos cancela, no reintenta', async () => {
    const fetchMock = vi.fn().mockRejectedValue(new DOMException('Cancelada', 'AbortError'))
    vi.stubGlobal('fetch', fetchMock)
    const controller = new AbortController()
    controller.abort()

    await expect(getJson('/health', undefined, controller.signal)).rejects.toMatchObject({ name: 'AbortError' })
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})
