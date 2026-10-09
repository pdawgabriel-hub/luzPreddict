import { describe, expect, it, vi } from 'vitest'
import { ApiError, getJson, postJson, withQuery } from './client'

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
