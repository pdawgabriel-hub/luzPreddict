// Sustituto de la API para VITE_USE_MOCKS=1: responde a las mismas rutas con datos
// de ejemplo (./data) y los mismos errores (404 si REE aún no ha publicado, etc.).

import { ApiError } from '../api/client'
import type { BillRequest, Health, PlanRequest, SimulateRequest } from '../api/types'
import * as data from './data'
import { addDays } from './time'

const DELAY_MS = 150 // para ver los estados de carga en desarrollo
const SLOW_DELAY_MS = 3_000

/**
 * Escenarios para ver en el navegador cada estado de la web (VITE_MOCK_SCENARIO):
 * - stale: /health avisa de datos desactualizados
 * - error: todas las peticiones fallan con 503 (base de datos no disponible)
 * - slow: las respuestas tardan 3 s
 */
export type Scenario = 'stale' | 'error' | 'slow'

type Options = { now?: Date; delayMs?: number; signal?: AbortSignal; scenario?: Scenario | '' }

function notFound(message: string): never {
  throw new ApiError(404, 'not_found', message, 'mock')
}

function invalid(field: string, message: string): never {
  throw new ApiError(422, 'validation_error', 'Parámetros no válidos', 'mock', [{ field, message, type: 'value_error' }])
}

function noPrices(start: string, end: string, tomorrow: string): never {
  if (start === end && start === tomorrow) {
    notFound(`REE aún no ha publicado los precios del ${start} (lo hace hacia las 20:15)`)
  }
  notFound(start === end ? `No hay precios del ${start}` : `No hay precios entre el ${start} y el ${end}`)
}

function range(query: URLSearchParams, defaultStart: string, defaultEnd: string): [string, string] {
  const start = query.get('start')
  const end = query.get('end')
  if (!start && !end) return [defaultStart, defaultEnd]
  if (!start || !end) invalid(`query.${start ? 'end' : 'start'}`, 'Hay que indicar start y end')
  if (end < start) invalid('query.end', 'end no puede ser anterior a start')
  return [start, end]
}

function route(method: string, url: URL, body: unknown, now: Date): unknown {
  const query = url.searchParams
  const today = data.today(now)
  const tomorrow = addDays(today, 1)
  const lastDay = data.lastPublishedDay(now)
  const key = `${method} ${url.pathname}`

  switch (key) {
    case 'GET /health':
      return data.health(now)

    case 'GET /v1/prices': {
      const day = query.get('date')
      const [start, end] = day ? [day, day] : range(query, today, today)
      const prices = data.prices(start, end, lastDay)
      return prices.hours.length ? prices : noPrices(start, end, tomorrow)
    }

    case 'GET /v1/forecast': {
      const day = query.get('date') ?? addDays(lastDay, 1)
      return day > addDays(lastDay, 1) ? notFound(`No hay previsión para el ${day}`) : data.forecast(day, lastDay, now)
    }

    case 'GET /v1/best-hours': {
      const day = query.get('date') ?? lastDay
      if (day > lastDay) noPrices(day, day, tomorrow)
      const hours = Number(query.get('hours') ?? 1)
      const result = data.bestHours(day, hours, Number(query.get('from_hour') ?? 0), Number(query.get('to_hour') ?? 24))
      return result ?? notFound(`No hay ${hours} horas seguidas con precio publicado en esa franja`)
    }

    case 'GET /v1/history': {
      const [start, end] = range(query, addDays(today, -29), today)
      const history = data.history(start, end, lastDay)
      return history.days.length ? history : noPrices(start, end, tomorrow)
    }

    case 'GET /v1/market': {
      const [start, end] = range(query, addDays(today, -29), today)
      const market = data.market(start, end, today)
      return market.days.length ? market : notFound(`No hay datos de generación entre el ${start} y el ${end}`)
    }

    case 'GET /api/model':
      return data.modelReport(now, Number(query.get('days') ?? 30))

    case 'GET /api/tools/catalog':
      return data.CATALOG

    case 'POST /api/tools/simulate': {
      const request = body as SimulateRequest
      const day = request.date ?? lastDay
      if (day > lastDay) noPrices(day, day, tomorrow)
      return data.simulate(request, day)
    }

    case 'POST /api/tools/plan': {
      const request = body as PlanRequest
      const day = request.date ?? lastDay
      if (day > lastDay) noPrices(day, day, tomorrow)
      return data.plan(request, day)
    }

    case 'POST /api/tools/bill': {
      const request = body as BillRequest
      const start = request.start ?? addDays(today, -29)
      const end = request.end ?? today
      if (start > lastDay) noPrices(start, end, tomorrow)
      return data.bill(request, start, end, lastDay)
    }

    default:
      return notFound('No encontrado')
  }
}

function stale(health: Health): Health {
  return {
    ...health,
    status: 'degraded',
    warnings: [`El último precio es del ${addDays(health.prices.last_day ?? '', -2)}: faltan los de hoy`],
  }
}

function delay(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, ms)
    signal?.addEventListener('abort', () => {
      clearTimeout(timer)
      reject(signal.reason)
    })
  })
}

/** Responde como la API a `method` + `url` (ruta con su query string). */
export async function mockRequest(method: string, url: string, body?: unknown, options: Options = {}): Promise<unknown> {
  const scenario = options.scenario ?? (import.meta.env.VITE_MOCK_SCENARIO as Scenario | undefined) ?? ''
  const defaultDelay = import.meta.env.MODE === 'test' ? 0 : scenario === 'slow' ? SLOW_DELAY_MS : DELAY_MS
  const delayMs = options.delayMs ?? defaultDelay
  if (delayMs) await delay(delayMs, options.signal)
  options.signal?.throwIfAborted()

  if (scenario === 'error') {
    throw new ApiError(503, 'service_unavailable', 'Base de datos no disponible', 'mock')
  }
  const response = route(method, new URL(url, 'http://mock'), body, options.now ?? new Date())
  if (scenario === 'stale' && url.startsWith('/health')) return stale(response as Health)
  return response
}
