// Precios de un día tal como los necesita la web: publicados por REE o, si aún no, la previsión.

import { ApiError, getJson } from './client'
import type { Forecast, Prices } from './types'
import type { HourPrice } from '../lib/prices'

/** Hora de un día; en la previsión, con su rango probable (`null` si el modelo no lo da). */
export type DayHour = HourPrice & { lower?: number | null; upper?: number | null }

export type Day = {
  day: string
  kind: 'published' | 'forecast'
  hours: DayHour[]
  generatedAt?: string
  disclaimer?: string
  model?: string
  intervalLevel?: number | null // parte de las horas en que el precio real cae dentro del rango (0,8)
}

/** Rango probable de cada hora de una previsión, o null si alguna hora no lo tiene. */
export function forecastRange(day: Day): { lower: number[]; upper: number[] } | null {
  if (day.kind !== 'forecast' || !day.hours.every((h) => h.lower != null && h.upper != null)) return null
  return { lower: day.hours.map((h) => h.lower as number), upper: day.hours.map((h) => h.upper as number) }
}

/** "En 8 de cada 10 horas…": cómo leer el rango probable. */
export function rangeNote(level: number | null | undefined): string | null {
  if (!level) return null
  return `En ${Math.round(level * 10)} de cada 10 horas, el precio real queda dentro de la zona sombreada.`
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
      intervalLevel: forecast.interval_level,
    }
  } catch (error) {
    if (isNotFound(error)) return null
    throw error
  }
}
