import { describe, expect, it } from 'vitest'
import { ApiError } from '../api/client'
import type { Bill, Forecast, Health, History, Market, ModelReport, Plan, Prices, Simulation } from '../api/types'
import { mockRequest } from './index'

const BEFORE = new Date('2026-10-06T16:00:00Z') // 18:00 en Madrid: REE aún no ha publicado mañana
const AFTER = new Date('2026-10-06T19:00:00Z') // 21:00 en Madrid: ya ha publicado

const get = <T>(url: string, now = AFTER) => mockRequest('GET', url, undefined, { now }) as Promise<T>
const post = <T>(url: string, body: unknown, now = AFTER) => mockRequest('POST', url, body, { now }) as Promise<T>

async function apiError(promise: Promise<unknown>): Promise<ApiError> {
  const error = await promise.catch((e: unknown) => e)
  expect(error).toBeInstanceOf(ApiError)
  return error as ApiError
}

describe('datos de ejemplo', () => {
  it('/health sabe si REE ya ha publicado mañana', async () => {
    const before = await get<Health>('/health', BEFORE)
    const after = await get<Health>('/health')

    expect(before.prices).toMatchObject({ last_day: '2026-10-06', has_tomorrow: false })
    expect(after.prices).toMatchObject({ last_day: '2026-10-07', has_tomorrow: true })
    expect(after.forecast?.target_day).toBe('2026-10-08')
  })

  it('los precios de un día son 24 horas con su periodo y la fuente de REE', async () => {
    const prices = await get<Prices>('/v1/prices?date=2026-10-06')

    expect(prices.hours).toHaveLength(24)
    expect(prices.hours[0]).toMatchObject({ datetime: '2026-10-06T00:00:00+02:00', period: 'valle' })
    expect(prices.hours[19].period).toBe('punta')
    expect(prices.hours.every((h) => h.price > 0)).toBe(true)
    expect(prices.source.series).toBe('PVPC 2.0TD')
  })

  it('son reproducibles: el mismo día da los mismos precios', async () => {
    const first = await get<Prices>('/v1/prices?date=2026-10-06')
    const second = await get<Prices>('/v1/prices?date=2026-10-06', BEFORE)
    expect(second).toEqual(first)
  })

  it('tienen la forma típica del PVPC: el mediodía es más barato que la noche', async () => {
    const { hours } = await get<Prices>('/v1/prices?date=2026-10-06')
    expect(hours[14].price).toBeLessThan(hours[20].price)
  })

  it('mañana sin publicar da el mismo 404 que la API', async () => {
    const error = await apiError(get('/v1/prices?date=2026-10-07', BEFORE))
    expect(error.status).toBe(404)
    expect(error.message).toMatch(/^REE aún no ha publicado los precios del 2026-10-07/)
  })

  it('la previsión incluye el precio real cuando ya se conoce', async () => {
    const pending = await get<Forecast>('/v1/forecast')
    const past = await get<Forecast>('/v1/forecast?date=2026-10-05')

    expect(pending.date).toBe('2026-10-08')
    expect(pending.hours.every((h) => h.actual === null)).toBe(true)
    expect(pending.disclaimer).toMatch(/orientativa/)
    expect(past.hours.every((h) => h.actual !== null)).toBe(true)
    expect(past.mae).toBeGreaterThan(0)
  })

  it('el histórico y el mercado cubren los últimos 30 días', async () => {
    const history = await get<History>('/v1/history')
    const market = await get<Market>('/v1/market')

    expect(history.days).toHaveLength(30)
    expect(history.days.at(-1)?.date).toBe('2026-10-06')
    expect(market.days.at(-1)?.provisional).toBe(true)
    expect(market.renewable_pct).toBeGreaterThan(0)
    expect(market.renewable_pct).toBeLessThan(100)
  })

  it('las herramientas responden con la forma de la API', async () => {
    const simulation = await post<Simulation>('/api/tools/simulate', { start_hour: 20 })
    const plan = await post<Plan>('/api/tools/plan', { power_kw: 3.45, tasks: [{ id: 'coche', appliance: 'coche', habitual_hour: 0 }] })
    const bill = await post<Bill>('/api/tools/bill', { total_kwh: 270, fixed_price: 0.13 })

    expect(simulation.simulations).toHaveLength(5)
    expect(simulation.simulations[0].best_cost).toBeLessThanOrEqual(simulation.simulations[0].cost)
    expect(plan.unplaced).toEqual(['coche']) // 3,7 kW más el consumo base superan 3,45 kW
    expect(bill.pvpc_cost).toBeGreaterThan(0)
    expect(bill.periods.map((p) => p.period)).toEqual(['punta', 'llano', 'valle'])
  })

  it('el informe del modelo trae backtest y error real', async () => {
    const report = await get<ModelReport>('/api/model')
    expect(report.backtest?.improvement_pct).toBe(32.4)
    expect(report.live.days.length).toBeGreaterThan(0)
  })

  it('una ruta desconocida o un rango al revés dan error', async () => {
    expect((await apiError(get('/v1/nada'))).status).toBe(404)
    const error = await apiError(get('/v1/history?start=2026-10-06&end=2026-10-01'))
    expect(error.details[0]).toMatchObject({ field: 'query.end' })
  })
})

describe('escenarios de los datos de ejemplo', () => {
  it('"error" hace fallar todas las peticiones con un 503', async () => {
    const error = await apiError(mockRequest('GET', '/v1/prices', undefined, { now: AFTER, scenario: 'error' }))
    expect(error).toMatchObject({ status: 503, code: 'service_unavailable' })
  })

  it('"stale" solo cambia /health', async () => {
    const health = (await mockRequest('GET', '/health', undefined, { now: AFTER, scenario: 'stale' })) as Health
    const prices = await mockRequest('GET', '/v1/prices', undefined, { now: AFTER, scenario: 'stale' })

    expect(health.status).toBe('degraded')
    expect(health.warnings[0]).toMatch(/faltan los de hoy/)
    expect(prices).toEqual(await get('/v1/prices'))
  })

  it('una petición cancelada no responde', async () => {
    const controller = new AbortController()
    const result = mockRequest('GET', '/health', undefined, { delayMs: 50, signal: controller.signal }).catch((e: unknown) => e)
    controller.abort()
    expect(await result).toMatchObject({ name: 'AbortError' })
  })
})
