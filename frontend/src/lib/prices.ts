// Cálculos del panel sobre los precios horarios de la API (€/MWh).

export type HourPrice = { datetime: string; price: number }
export type Tier = 'cheap' | 'mid' | 'high'

export const TIER_LABELS: Record<Tier, string> = { cheap: 'barata', mid: 'media', high: 'cara' }

export function mean(values: readonly number[]): number {
  return values.reduce((a, b) => a + b, 0) / values.length
}

/** Cortes de los tercios: el tercio más barato es "barata" y el más caro, "cara". */
export function tierCuts(values: readonly number[]): { low: number; high: number } {
  const sorted = [...values].sort((a, b) => a - b)
  const third = Math.max(1, Math.floor(sorted.length / 3))
  return { low: sorted[third - 1], high: sorted[sorted.length - third] }
}

export function tierOf(value: number, cuts: { low: number; high: number }): Tier {
  if (value <= cuts.low) return 'cheap'
  if (value >= cuts.high) return 'high'
  return 'mid'
}

/** Índice de la hora en curso, o -1 si `now` no cae en ninguna. */
export function currentHourIndex(hours: readonly HourPrice[], now: Date): number {
  const t = now.getTime()
  return hours.findIndex((h) => {
    const start = new Date(h.datetime).getTime()
    return start <= t && t < start + 3_600_000
  })
}

/** Las `n` horas más baratas, de más barata a más cara (con empate, la más temprana). */
export function cheapestHours<T extends HourPrice>(hours: readonly T[], n: number): T[] {
  return [...hours].sort((a, b) => a.price - b.price || a.datetime.localeCompare(b.datetime)).slice(0, n)
}

/** Las `length` horas seguidas más caras: dónde no poner la lavadora. */
export function priciestWindow(hours: readonly HourPrice[], length: number): { start: number; max: number } | null {
  let best: { start: number; avg: number } | null = null
  for (let start = 0; start + length <= hours.length; start++) {
    const avg = mean(hours.slice(start, start + length).map((h) => h.price))
    if (!best || avg > best.avg) best = { start, avg }
  }
  if (!best) return null
  return { start: best.start, max: Math.max(...hours.slice(best.start, best.start + length).map((h) => h.price)) }
}

/** Variación en % de `next` respecto a `base`. */
export function changePct(base: number, next: number): number {
  return ((next - base) / base) * 100
}

/** Horas en las que mañana sale más barato que hoy, comparando la misma posición del día. */
export function cheaperHours(today: readonly HourPrice[], tomorrow: readonly HourPrice[]): number {
  return tomorrow.filter((h, i) => i < today.length && h.price < today[i].price).length
}
