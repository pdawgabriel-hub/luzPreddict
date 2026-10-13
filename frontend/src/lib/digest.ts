// Texto del resumen diario de ntfy, para enseñar en la web cómo llegaría.
// Mismo formato que src/services/digest.py, que es el que envía la tarea diaria.

import { formatDay, madridHour } from './format'
import { cheapestHours, mean, type HourPrice } from './prices'

const WINDOW_HOURS = 2
const TOP_HOURS = 3
const MODEL_NAMES: Record<string, string> = {
  lightgbm: 'LightGBM',
  precio_ayer: 'respaldo "precio de ayer"',
  media_7_dias: 'respaldo "media 7 días"',
}

/** €/MWh → €/kWh con 3 decimales y redondeo comercial (72,5 → "0,073"), como en Python. */
export function digestKwh(priceMwh: number): string {
  return (Math.round(priceMwh) / 1000).toFixed(3).replace('.', ',')
}

/** Ventana de `length` horas seguidas con la media más baja (o más alta). */
function window(hours: readonly HourPrice[], length: number, cheapest: boolean): { start: number; avg: number } {
  let best: { start: number; avg: number } | null = null
  for (let start = 0; start + length <= hours.length; start++) {
    const avg = mean(hours.slice(start, start + length).map((h) => h.price))
    if (!best || (cheapest ? avg < best.avg - 1e-9 : avg > best.avg + 1e-9)) best = { start, avg }
  }
  return best ?? { start: 0, avg: mean(hours.map((h) => h.price)) }
}

function range(hours: readonly HourPrice[], start: number, length: number): string {
  const end = hours[start + length] ? madridHour(hours[start + length].datetime) : 24
  return `${madridHour(hours[start].datetime)}–${end} h`
}

export type DigestSource = { kind: 'published' | 'forecast'; model?: string }

/** Título y líneas del resumen de un día (precios en €/MWh). */
export function buildDigest(day: string, hours: readonly HourPrice[], source: DigestSource, previous?: readonly HourPrice[]): { title: string; lines: string[] } {
  const avg = mean(hours.map((h) => h.price))
  const cheap = window(hours, WINDOW_HOURS, true)
  const pricy = window(hours, WINDOW_HOURS, false)
  const best = cheapestHours(hours, TOP_HOURS).map((h) => `${madridHour(h.datetime)} h`)
  const worst = [...hours]
    .sort((a, b) => b.price - a.price || a.datetime.localeCompare(b.datetime))
    .slice(0, TOP_HOURS)
    .map((h) => `${madridHour(h.datetime)} h`)

  const lines = [
    `Más barata: ${range(hours, cheap.start, WINDOW_HOURS)} (${digestKwh(cheap.avg)} €/kWh)`,
    `Más cara: ${range(hours, pricy.start, WINDOW_HOURS)} (${digestKwh(pricy.avg)} €/kWh)`,
    `Mejores horas: ${best.join(', ')} · Evita: ${worst.join(', ')}`,
  ]
  if (previous?.length) {
    const change = avg / mean(previous.map((h) => h.price)) - 1
    lines.push(Math.abs(change) >= 0.005 ? `Un ${Math.round(Math.abs(change) * 100)} % más ${change > 0 ? 'cara' : 'barata'} que el día anterior.` : 'Similar al día anterior.')
  }
  lines.push(
    source.kind === 'published'
      ? 'Precios publicados por REE.'
      : `Previsión de luzPreddict (${MODEL_NAMES[source.model ?? ''] ?? source.model ?? 'modelo desconocido'}).`,
  )
  return { title: `Luz el ${formatDay(day)}: media ${digestKwh(avg)} €/kWh`, lines }
}
