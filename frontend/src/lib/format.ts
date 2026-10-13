// Formatos de números, precios, horas y fechas en castellano y en hora de Madrid.

const TZ = 'Europe/Madrid'
const LOCALE = 'es-ES'

const numberFormats = new Map<string, Intl.NumberFormat>()

/** Número con coma decimal y separador de miles: 1234,5 → "1.234,5". */
export function formatNumber(value: number, decimals = 0): string {
  const key = String(decimals)
  let format = numberFormats.get(key)
  if (!format) {
    // useGrouping 'always': en español los miles de 4 cifras también se separan (1.234)
    format = new Intl.NumberFormat(LOCALE, { minimumFractionDigits: decimals, maximumFractionDigits: decimals, useGrouping: 'always' })
    numberFormats.set(key, format)
  }
  return format.format(value)
}

/** Precio de la API (€/MWh) en €/kWh, como en la factura: 252,3 → "0,252". */
export function formatKwh(eurPerMwh: number, decimals = 3): string {
  return formatNumber(eurPerMwh / 1000, decimals)
}

/** €/MWh con un decimal: 169,34 → "169,3". */
export function formatMwh(eurPerMwh: number, decimals = 1): string {
  return formatNumber(eurPerMwh, decimals)
}

export function formatEuros(value: number, decimals = 2): string {
  return `${formatNumber(value, decimals)} €`
}

/** Porcentaje con espacio, como manda la RAE: 12 → "12 %". */
export function formatPercent(value: number, decimals = 0): string {
  return `${formatNumber(value, decimals)} %`
}

const hourFormat = new Intl.DateTimeFormat(LOCALE, { timeZone: TZ, hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })
const hourNumberFormat = new Intl.DateTimeFormat('en-GB', { timeZone: TZ, hour: '2-digit', hourCycle: 'h23' })

/** Hora de reloj en Madrid de una fecha ISO de la API: "13:00". */
export function formatTime(iso: string): string {
  return hourFormat.format(new Date(iso))
}

/** Hora de reloj (0-23) en Madrid. */
export function madridHour(iso: string): number {
  return Number(hourNumberFormat.format(new Date(iso)))
}

/** Franja de una hora: "13–14 h". La última hora del día acaba a las 24. */
export function formatHourRange(iso: string, hours = 1): string {
  const start = madridHour(iso)
  let end = madridHour(new Date(new Date(iso).getTime() + hours * 3_600_000).toISOString())
  // La 2:00 repetida del cambio a horario de invierno acabaría "a las 2": se muestra como 2–3
  if (end === start) end = start + hours
  return `${start}–${end === 0 ? 24 : end} h`
}

const dayFormat = new Intl.DateTimeFormat(LOCALE, { timeZone: 'UTC', weekday: 'long', day: 'numeric', month: 'long' })
const shortDayFormat = new Intl.DateTimeFormat(LOCALE, { timeZone: 'UTC', day: 'numeric', month: 'short' })

// Los días de la API (AAAA-MM-DD) son días de Madrid: se formatean como fechas sin hora
const asDate = (day: string) => new Date(`${day}T00:00:00Z`)

/** "sábado 3 de octubre" (sin la coma que pone Intl tras el día de la semana). */
export function formatDay(day: string): string {
  return dayFormat.format(asDate(day)).replace(',', '')
}

/** "3 oct". */
export function formatShortDay(day: string): string {
  return shortDayFormat.format(asDate(day)).replace('.', '')
}
