import { describe, expect, it, vi } from 'vitest'
import { loadDay } from './days'

const json = (status: number, body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status }))
const error = (status: number, code: string) => json(status, { error: { code, message: code, request_id: 'r', details: [] } })
const signal = new AbortController().signal

function respond(prices: () => Promise<Response>, forecast: () => Promise<Response>) {
  vi.stubGlobal('fetch', vi.fn((url: string) => (url.startsWith('/v1/prices') ? prices() : forecast())))
}

const HOURS = [{ datetime: '2026-10-07T00:00:00+02:00', price: 100, period: 'valle' }]

describe('cargar un día (publicado o previsión)', () => {
  it('si REE ya lo publicó entero, el precio publicado', async () => {
    respond(() => json(200, { missing_days: [], hours: HOURS }), () => error(500, 'no debería pedirse'))
    expect(await loadDay('2026-10-07', signal)).toMatchObject({ kind: 'published', hours: HOURS })
  })

  it('si falta o está incompleto, la previsión', async () => {
    const forecast = { date: '2026-10-07', hours: HOURS, generated_at: 'g', disclaimer: 'd', model: 'lightgbm' }
    respond(() => json(200, { missing_days: ['2026-10-07'], hours: [] }), () => json(200, forecast))
    expect(await loadDay('2026-10-07', signal)).toMatchObject({ kind: 'forecast', model: 'lightgbm', disclaimer: 'd' })

    respond(() => error(404, 'not_found'), () => json(200, forecast))
    expect(await loadDay('2026-10-07', signal)).toMatchObject({ kind: 'forecast' })
  })

  it('si no hay ni precio ni previsión, null', async () => {
    respond(() => error(404, 'not_found'), () => error(404, 'not_found'))
    expect(await loadDay('2026-10-07', signal)).toBeNull()
  })

  it('otros errores no se tapan', async () => {
    respond(() => error(422, 'validation_error'), () => error(404, 'not_found'))
    await expect(loadDay('2026-10-07', signal)).rejects.toMatchObject({ status: 422 })

    respond(() => error(404, 'not_found'), () => error(422, 'validation_error'))
    await expect(loadDay('2026-10-07', signal)).rejects.toMatchObject({ status: 422 })
  })
})
