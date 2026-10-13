// Precios de un día tal como los necesita la web: publicados por REE o, si aún no, la previsión.

import { ApiError, getJson } from './client'
import type { Forecast, Prices } from './types'
import type { HourPrice } from '../lib/prices'

export type Day = {
  day: string
  kind: 'published' | 'forecast'
  hours: HourPrice[]
  generatedAt?: string
  disclaimer?: string
  model?: string
}

const isNotFound = (error: unknown) => error instanceof ApiError && error.status === 404

/** Un día: el precio publicado si REE ya lo dio entero; si no, la previsión; si tampoco, null. */
export async function loadDay(day: string, signal: AbortSignal): Promise<Day | null> {
  try {
    const prices = await getJson<Prices>('/v1/prices', { date: day }, signal)
    if (!prices.missing_days.length) return { day, kind: 'published', hours: prices.hours }
  } catch (error) {
    if (!isNotFound(error)) throw error
  }
  try {
    const forecast = await getJson<Forecast>('/v1/forecast', { date: day }, signal)
    return {
      day,
      kind: 'forecast',
      hours: forecast.hours,
      generatedAt: forecast.generated_at,
      disclaimer: forecast.disclaimer,
      model: forecast.model,
    }
  } catch (error) {
    if (isNotFound(error)) return null
    throw error
  }
}
