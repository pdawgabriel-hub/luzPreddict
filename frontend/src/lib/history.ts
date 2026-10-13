// Cálculos del histórico sobre los precios horarios de la API (€/MWh).

import { weekday } from './dates'
import { madridHour } from './format'
import { mean, type HourPrice } from './prices'

export type DayPrices = {
  day: string
  byHour: (number | null)[] // 24 posiciones por hora de reloj: la 2:00 repetida se promedia; la que falta, null
  mean: number
  min: HourPrice
  max: HourPrice
}

const madridDay = (iso: string) => iso.slice(0, 10) // la API da las horas con el día de Madrid

/** Agrupa las horas por día de Madrid, en orden. */
export function groupByDay(hours: readonly HourPrice[]): DayPrices[] {
  const days = new Map<string, HourPrice[]>()
  for (const hour of hours) days.set(madridDay(hour.datetime), [...(days.get(madridDay(hour.datetime)) ?? []), hour])
  return [...days.entries()].map(([day, rows]) => {
    const buckets: number[][] = Array.from({ length: 24 }, () => [])
    for (const row of rows) buckets[madridHour(row.datetime)].push(row.price)
    const sorted = [...rows].sort((a, b) => a.price - b.price || a.datetime.localeCompare(b.datetime))
    const priciest = [...rows].sort((a, b) => b.price - a.price || a.datetime.localeCompare(b.datetime))[0]
    return {
      day,
      byHour: buckets.map((values) => (values.length ? mean(values) : null)),
      mean: mean(rows.map((r) => r.price)),
      min: sorted[0],
      max: priciest,
    }
  })
}

export const isWeekend = (day: string) => weekday(day) >= 5

export type PeriodStats = { mean: number; min: HourPrice; max: HourPrice; below: number; total: number }

/** Media, hora más barata y más cara, y horas por debajo de `threshold` (€/MWh). */
export function periodStats(hours: readonly HourPrice[], threshold: number): PeriodStats {
  const byPrice = [...hours].sort((a, b) => a.price - b.price || a.datetime.localeCompare(b.datetime))
  return {
    mean: mean(hours.map((h) => h.price)),
    min: byPrice[0],
    max: [...hours].sort((a, b) => b.price - a.price || a.datetime.localeCompare(b.datetime))[0],
    below: hours.filter((h) => h.price < threshold).length,
    total: hours.length,
  }
}

/** Precio medio de cada hora del día (0-23) en los días elegidos; null si ninguno la tiene. */
export function hourlyProfile(days: readonly DayPrices[]): (number | null)[] {
  return Array.from({ length: 24 }, (_, hour) => {
    const values = days.map((d) => d.byHour[hour]).filter((v): v is number => v !== null)
    return values.length ? mean(values) : null
  })
}

/** Media de cada día de la semana (0 = lunes … 6 = domingo); null si no hay ninguno en el periodo. */
export function weekdayMeans(days: readonly DayPrices[]): (number | null)[] {
  return Array.from({ length: 7 }, (_, wd) => {
    const values = days.filter((d) => weekday(d.day) === wd).map((d) => d.mean)
    return values.length ? mean(values) : null
  })
}

/** Índice del mínimo y del máximo, sin contar los huecos. */
export function argExtremes(values: readonly (number | null)[]): { min: number; max: number } {
  let min = -1
  let max = -1
  values.forEach((v, i) => {
    if (v === null) return
    if (min < 0 || v < (values[min] as number)) min = i
    if (max < 0 || v > (values[max] as number)) max = i
  })
  return { min, max }
}
