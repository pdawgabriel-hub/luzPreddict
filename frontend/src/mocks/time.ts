// Fechas en hora de Madrid para los datos de ejemplo, con los cambios de hora
// (días de 23 y 25 horas), igual que la API.

const TZ = 'Europe/Madrid'
const HOUR_MS = 3_600_000

const dateFormat = new Intl.DateTimeFormat('en-CA', { timeZone: TZ, year: 'numeric', month: '2-digit', day: '2-digit' })
const offsetFormat = new Intl.DateTimeFormat('en-US', { timeZone: TZ, timeZoneName: 'longOffset' })
const hourFormat = new Intl.DateTimeFormat('en-GB', { timeZone: TZ, hour: '2-digit', hourCycle: 'h23' })

/** Día de Madrid (AAAA-MM-DD) de un instante. */
export function madridDate(instant: Date): string {
  return dateFormat.format(instant)
}

/** Desfase de Madrid en un instante, como "+02:00". */
export function madridOffset(instant: Date): string {
  const name = offsetFormat.formatToParts(instant).find((p) => p.type === 'timeZoneName')?.value ?? 'GMT'
  return name === 'GMT' ? '+00:00' : name.replace('GMT', '')
}

/** Hora de reloj (0-23) en Madrid. */
export function madridHour(instant: Date): number {
  return Number(hourFormat.format(instant))
}

/** Instante en ISO 8601 con el desfase de Madrid, como lo da la API. */
export function toMadridIso(instant: Date): string {
  const hour = String(madridHour(instant)).padStart(2, '0')
  const minutes = String(instant.getUTCMinutes()).padStart(2, '0')
  const seconds = String(instant.getUTCSeconds()).padStart(2, '0')
  return `${madridDate(instant)}T${hour}:${minutes}:${seconds}${madridOffset(instant)}`
}

export function addDays(day: string, days: number): string {
  const [y, m, d] = day.split('-').map(Number)
  return new Date(Date.UTC(y, m - 1, d + days)).toISOString().slice(0, 10)
}

/** Días entre dos fechas, ambas incluidas. */
export function daysBetween(start: string, end: string): string[] {
  const days: string[] = []
  for (let day = start; day <= end; day = addDays(day, 1)) days.push(day)
  return days
}

/** Día de la semana (0 = lunes ... 6 = domingo). */
export function weekday(day: string): number {
  const [y, m, d] = day.split('-').map(Number)
  return (new Date(Date.UTC(y, m - 1, d)).getUTCDay() + 6) % 7
}

/** Inicio de cada hora del día de Madrid: 23, 24 o 25 instantes. */
export function dayHours(day: string): Date[] {
  const [y, m, d] = day.split('-').map(Number)
  // Medianoche local: se parte de las 00:00 UTC y se corrige con el desfase de ese momento
  const guess = new Date(Date.UTC(y, m - 1, d))
  const offsetHours = Number(madridOffset(guess).slice(0, 3))
  let instant = new Date(guess.getTime() - offsetHours * HOUR_MS)
  const hours: Date[] = []
  while (madridDate(instant) === day) {
    hours.push(instant)
    instant = new Date(instant.getTime() + HOUR_MS)
  }
  return hours
}
