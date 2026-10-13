import { describe, expect, it, vi } from 'vitest'
import { forecastRange, loadDay, rangeNote, type Day } from './days'

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

  it('la previsión trae el nivel de su rango probable', async () => {
    const forecast = { date: '2026-10-07', hours: HOURS, generated_at: 'g', disclaimer: 'd', model: 'lightgbm', interval_level: 0.8 }
    respond(() => error(404, 'not_found'), () => json(200, forecast))
    expect(await loadDay('2026-10-07', signal)).toMatchObject({ intervalLevel: 0.8 })
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

describe('rango probable de la previsión', () => {
  const day = (kind: Day['kind'], hours: Day['hours']): Day => ({ day: '2026-10-07', kind, hours })
  const hour = (lower: number | null, upper: number | null) => ({ datetime: 'h', price: 100, lower, upper })

  it('los límites de cada hora, solo si todas los tienen y es una previsión', () => {
    expect(forecastRange(day('forecast', [hour(80, 120), hour(70, 130)]))).toEqual({ lower: [80, 70], upper: [120, 130] })
    expect(forecastRange(day('forecast', [hour(80, 120), hour(null, null)]))).toBeNull()
    expect(forecastRange(day('published', [{ datetime: 'h', price: 100 }]))).toBeNull()
  })

  it('explica el nivel en horas de cada 10', () => {
    expect(rangeNote(0.8)).toBe('En 8 de cada 10 horas, el precio real queda dentro de la zona sombreada.')
    expect(rangeNote(null)).toBeNull()
    expect(rangeNote(undefined)).toBeNull()
  })
})
