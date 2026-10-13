import { describe, expect, it } from 'vitest'
import { dayHours, toMadridIso } from './dates'
import { buildDigest, digestKwh } from './digest'

// Los mismos datos que tests/test_services_digest.py: el texto debe salir igual que en Python
const DAY = '2026-10-07'
const PROFILE = [150, 140, 130, 125, 120, 130, 160, 200, 220, 180, 150, 120, 100, 90, 70, 75, 95, 140, 250, 300, 320, 290, 200, 170]
const hours = (day: string, prices: number[]) => dayHours(day).map((instant, i) => ({ datetime: toMadridIso(instant), price: prices[i] }))

describe('resumen diario (mismo formato que src/services/digest.py)', () => {
  it('previsión de un día', () => {
    const digest = buildDigest(DAY, hours(DAY, PROFILE), { kind: 'forecast', model: 'lightgbm' })

    expect(digest.title).toBe(`Luz el miércoles 7 de octubre: media ${digestKwh(PROFILE.reduce((a, b) => a + b, 0) / 24)} €/kWh`)
    expect(digest.lines).toEqual([
      'Más barata: 14–16 h (0,073 €/kWh)',
      'Más cara: 19–21 h (0,310 €/kWh)',
      'Mejores horas: 14 h, 15 h, 13 h · Evita: 20 h, 19 h, 21 h',
      'Previsión de luzPreddict (LightGBM).',
    ])
  })

  it('precios publicados, comparados con el día anterior', () => {
    const digest = buildDigest(DAY, hours(DAY, PROFILE), { kind: 'published' }, hours('2026-10-06', PROFILE.map((p) => p / 1.12)))
    expect(digest.lines.slice(-2)).toEqual(['Un 12 % más cara que el día anterior.', 'Precios publicados por REE.'])
  })

  it('una franja que acaba a medianoche acaba a las 24', () => {
    const prices = PROFILE.map((_, i) => (i >= 22 ? 300 : 100))
    expect(buildDigest(DAY, hours(DAY, prices), { kind: 'published' }).lines[1]).toBe('Más cara: 22–24 h (0,300 €/kWh)')
  })

  it('redondea como en la factura: 0,0725 → 0,073', () => {
    expect(digestKwh(72.5)).toBe('0,073')
    expect(digestKwh(72.4)).toBe('0,072')
  })
})
