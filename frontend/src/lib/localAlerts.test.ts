import { describe, expect, it, vi } from 'vitest'
import { MAX_ALERTS, STORAGE_KEY, history, loadAlerts, matches, matchingHours, newAlertId, saveAlerts, type Alert } from './localAlerts'

const alert = (patch: Partial<Alert> = {}): Alert => ({ id: 'a1', direction: 'below', threshold: 100, active: true, ...patch })
const hour = (day: string, h: number, price: number) => ({ datetime: `${day}T${String(h).padStart(2, '0')}:00:00+02:00`, price })

describe('alertas guardadas en el navegador', () => {
  it('se guardan y se recuperan', () => {
    expect(loadAlerts()).toEqual([])
    expect(saveAlerts([alert(), alert({ id: 'a2', direction: 'above', threshold: 300, active: false })])).toBe(true)

    expect(loadAlerts().map((a) => a.id)).toEqual(['a1', 'a2'])
    expect(JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '[]')).toHaveLength(2)
  })

  it('ignoran lo guardado que no es válido', () => {
    localStorage.setItem(STORAGE_KEY, '{roto')
    expect(loadAlerts()).toEqual([])

    localStorage.setItem(STORAGE_KEY, JSON.stringify([alert(), { id: 'x', direction: 'sideways', threshold: 1, active: true }, { id: 'y' }, null]))
    expect(loadAlerts().map((a) => a.id)).toEqual(['a1'])
  })

  it('no fallan si el navegador no deja guardar (modo privado)', () => {
    const blocked = {
      getItem: () => {
        throw new Error('SecurityError')
      },
      setItem: () => {
        throw new Error('QuotaExceededError')
      },
    } as unknown as Storage

    expect(loadAlerts(blocked)).toEqual([])
    expect(saveAlerts([alert()], blocked)).toBe(false)
  })

  it('sin almacenamiento disponible no hay alertas ni se pueden guardar', () => {
    vi.stubGlobal('localStorage', undefined) // p. ej. un navegador que lo tiene desactivado
    expect(loadAlerts()).toEqual([])
    expect(saveAlerts([alert()])).toBe(false)
  })

  it('cada alerta tiene un id distinto, también sin crypto.randomUUID', () => {
    expect(newAlertId()).not.toBe(newAlertId())
    vi.stubGlobal('crypto', {})
    expect(newAlertId()).toMatch(/^\d+-[a-z0-9]+$/)
  })

  it(`guardan como mucho ${MAX_ALERTS}`, () => {
    saveAlerts(Array.from({ length: MAX_ALERTS + 3 }, (_, i) => alert({ id: String(i) })))
    expect(loadAlerts()).toHaveLength(MAX_ALERTS)
  })
})

describe('qué horas cumplen una alerta', () => {
  const hours = [hour('2026-10-07', 0, 50), hour('2026-10-07', 1, 100), hour('2026-10-07', 2, 150)]

  it('"baje de" y "suba de" son estrictos', () => {
    expect(matches(alert(), 100)).toBe(false)
    expect(matchingHours(alert(), hours).map((h) => h.price)).toEqual([50])
    expect(matchingHours(alert({ direction: 'above' }), hours).map((h) => h.price)).toEqual([150])
  })

  it('cuenta días y horas en los que habría saltado', () => {
    const past = [...hours, hour('2026-10-08', 0, 200), hour('2026-10-08', 1, 90), hour('2026-10-09', 0, 300)]
    expect(history(alert(), past)).toEqual({ days: 2, hours: 2, total: 3 })
  })
})
