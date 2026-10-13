import { describe, expect, it } from 'vitest'
import spec from '../api/openapi.json'
import { publicEndpoints, requestPath, type OpenApiSpec } from './openapi'

const endpoints = publicEndpoints(spec as unknown as OpenApiSpec)

describe('documentación desde el OpenAPI real', () => {
  it('solo lista los endpoints públicos de lectura', () => {
    expect(endpoints.map((e) => e.path)).toEqual(['/health', '/v1/prices', '/v1/forecast', '/v1/best-hours', '/v1/history', '/v1/market'])
  })

  it('lee los parámetros con su tipo, límites y descripción', () => {
    const bestHours = endpoints.find((e) => e.path === '/v1/best-hours')!
    const hours = bestHours.parameters.find((p) => p.name === 'hours')!

    expect(bestHours.parameters.map((p) => p.name)).toEqual(['hours', 'date', 'from_hour', 'to_hour'])
    expect(hours).toMatchObject({ kind: 'integer', minimum: 1, maximum: 24, default: 1, required: false })
    expect(hours.description).toBe('Duración del consumo, en horas')
    expect(bestHours.parameters.find((p) => p.name === 'date')?.kind).toBe('date')
    expect(bestHours.summary).toBe('Mejores horas para consumir')
  })

  it('construye la ruta sin los parámetros vacíos', () => {
    const prices = endpoints.find((e) => e.path === '/v1/prices')!
    expect(requestPath(prices, { date: '2026-10-13', start: '', end: ' ' })).toBe('/v1/prices?date=2026-10-13')
    expect(requestPath(prices, {})).toBe('/v1/prices')
  })
})
