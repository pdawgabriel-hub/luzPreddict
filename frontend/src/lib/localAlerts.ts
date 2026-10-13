// Alertas de precio guardadas solo en este navegador (localStorage): sin cuentas y
// sin enviar nada a ningún servidor. La web las comprueba con los precios de mañana.

import { groupByDay } from './history'
import type { HourPrice } from './prices'

export type Direction = 'below' | 'above'

export type Alert = {
  id: string
  direction: Direction
  threshold: number // €/MWh, como los precios de la API
  active: boolean
}

export const STORAGE_KEY = 'luzpreddict:alertas:v1'
export const MAX_ALERTS = 10

function isAlert(value: unknown): value is Alert {
  if (typeof value !== 'object' || value === null) return false
  const a = value as Record<string, unknown>
  return (
    typeof a.id === 'string' &&
    (a.direction === 'below' || a.direction === 'above') &&
    typeof a.threshold === 'number' &&
    Number.isFinite(a.threshold) &&
    typeof a.active === 'boolean'
  )
}

/** Alertas guardadas; si no hay, o lo guardado no es válido, o el navegador lo impide: ninguna. */
export function loadAlerts(storage: Storage | undefined = globalThis.localStorage): Alert[] {
  try {
    const raw = storage?.getItem(STORAGE_KEY)
    const parsed: unknown = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? parsed.filter(isAlert).slice(0, MAX_ALERTS) : []
  } catch {
    return [] // JSON roto o almacenamiento bloqueado (modo privado, cookies desactivadas…)
  }
}

/** Guarda las alertas; devuelve false si el navegador no lo permite. */
export function saveAlerts(alerts: readonly Alert[], storage: Storage | undefined = globalThis.localStorage): boolean {
  try {
    storage?.setItem(STORAGE_KEY, JSON.stringify(alerts.slice(0, MAX_ALERTS)))
    return storage !== undefined
  } catch {
    return false
  }
}

export function newAlertId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`
}

export function matches(alert: Pick<Alert, 'direction' | 'threshold'>, price: number): boolean {
  return alert.direction === 'below' ? price < alert.threshold : price > alert.threshold
}

/** Horas de `hours` que cumplen la alerta. */
export function matchingHours<T extends HourPrice>(alert: Pick<Alert, 'direction' | 'threshold'>, hours: readonly T[]): T[] {
  return hours.filter((h) => matches(alert, h.price))
}

/** Cuántos días (y horas) habría saltado la alerta en un periodo. */
export function history(alert: Pick<Alert, 'direction' | 'threshold'>, hours: readonly HourPrice[]): { days: number; hours: number; total: number } {
  const days = groupByDay(hours)
  const hits = matchingHours(alert, hours)
  const hitDays = new Set(hits.map((h) => h.datetime.slice(0, 10)))
  return { days: hitDays.size, hours: hits.length, total: days.length }
}
