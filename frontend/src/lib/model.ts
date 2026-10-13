// Evaluación de la previsión: errores de LightGBM y de las referencias simples
// frente al precio publicado. Las referencias siguen las reglas de
// src/models/baselines.py: si falta el dato principal, se usa el siguiente.

import { isWeekend, type DayPrices } from './history'
import { mean } from './prices'

export const MODEL_LABELS: Record<string, string> = {
  lightgbm: 'LightGBM',
  media_7_dias: 'Media 7 días',
  precio_ayer: 'Precio de ayer',
}
export const BASELINES = ['media_7_dias', 'precio_ayer'] as const
export type Baseline = (typeof BASELINES)[number]

/** Una hora evaluada: hora de reloj, precio real y previsión (€/MWh), con su rango probable si lo tiene. */
export type Point = { hour: number; actual: number; predicted: number; lower?: number | null; upper?: number | null }
export type EvaluatedDay = { day: string; points: Point[] }

const present = (values: (number | null)[]) => values.filter((v): v is number => v !== null)

/** Previsión de una referencia para el día `index` de `days` (con los días anteriores), por hora de reloj. */
export function baselineForecast(days: readonly DayPrices[], index: number, baseline: Baseline): (number | null)[] {
  const yesterday = days[index - 1]
  const lastWeek = days.slice(Math.max(0, index - 7), index)
  const previousMean = yesterday ? mean(present(yesterday.byHour)) : null
  return Array.from({ length: 24 }, (_, hour) => {
    const lag = yesterday?.byHour[hour] ?? null
    const week = present(lastWeek.map((d) => d.byHour[hour]))
    const weekMean = lastWeek.length === 7 && week.length ? mean(week) : null
    const order = baseline === 'precio_ayer' ? [lag, weekMean, previousMean] : [weekMean, lag, previousMean]
    return order.find((v) => v !== null && v !== undefined) ?? null
  })
}

/** Días evaluados de una referencia: los de `days` desde `from` que tienen previsión y precio. */
export function evaluateBaseline(days: readonly DayPrices[], baseline: Baseline, from: string): EvaluatedDay[] {
  return days.flatMap((day, index) => {
    if (day.day < from || index === 0) return []
    const forecast = baselineForecast(days, index, baseline)
    const points = day.byHour.flatMap((actual, hour) =>
      actual !== null && forecast[hour] !== null ? [{ hour, actual, predicted: forecast[hour] as number }] : [],
    )
    return points.length ? [{ day: day.day, points }] : []
  })
}

const errors = (points: readonly Point[]) => points.map((p) => Math.abs(p.predicted - p.actual))

export function mae(days: readonly EvaluatedDay[]): number | null {
  const all = days.flatMap((d) => errors(d.points))
  return all.length ? mean(all) : null
}

/** Parte de las horas con rango probable en que el precio real cayó dentro (0-1), o null si ninguna lo tiene. */
export function intervalCoverage(days: readonly EvaluatedDay[]): { coverage: number; hours: number } | null {
  const points = days.flatMap((d) => d.points).filter((p) => p.lower != null && p.upper != null)
  if (!points.length) return null
  const inside = points.filter((p) => (p.lower as number) <= p.actual && p.actual <= (p.upper as number)).length
  return { coverage: inside / points.length, hours: points.length }
}

/** Error medio de cada hora del día (0-23). */
export function maeByHour(days: readonly EvaluatedDay[]): (number | null)[] {
  return Array.from({ length: 24 }, (_, hour) => {
    const values = days.flatMap((d) => errors(d.points.filter((p) => p.hour === hour)))
    return values.length ? mean(values) : null
  })
}

/** Error medio de cada día. */
export function maeByDay(days: readonly EvaluatedDay[]): { day: string; mae: number }[] {
  return days.map((d) => ({ day: d.day, mae: mean(errors(d.points)) }))
}

/** Error medio en laborables y en fin de semana, con cuántos días hay de cada. */
export function maeByDayType(days: readonly EvaluatedDay[]) {
  const workdays = days.filter((d) => !isWeekend(d.day))
  const weekend = days.filter((d) => isWeekend(d.day))
  return { workdays: { mae: mae(workdays), days: workdays.length }, weekend: { mae: mae(weekend), days: weekend.length } }
}
