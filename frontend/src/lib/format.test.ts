import { describe, expect, it } from 'vitest'
import {
  formatDay,
  formatEuros,
  formatHourRange,
  formatKwh,
  formatMwh,
  formatNumber,
  formatPercent,
  formatPeriod,
  formatShortDay,
  formatTime,
  formatWeekdayDay,
  madridHour,
} from './format'

describe('números', () => {
  it('usan coma decimal y punto de miles', () => {
    expect(formatNumber(1234.5, 1)).toBe('1.234,5')
    expect(formatNumber(0.5)).toBe('1') // redondeo
    expect(formatNumber(-3.25, 2)).toBe('-3,25')
  })

  it('los precios de la API (€/MWh) se muestran en €/kWh, como en la factura', () => {
    expect(formatKwh(252.3)).toBe('0,252')
    expect(formatKwh(49)).toBe('0,049')
    expect(formatMwh(169.34)).toBe('169,3')
  })

  it('euros y porcentajes llevan espacio antes del símbolo', () => {
    expect(formatEuros(1.234)).toBe('1,23 €')
    expect(formatPercent(12)).toBe('12 %')
    expect(formatPercent(32.44, 1)).toBe('32,4 %')
  })
})

describe('horas en Madrid', () => {
  it('lee la hora de reloj de las fechas ISO de la API', () => {
    expect(formatTime('2026-10-06T13:00:00+02:00')).toBe('13:00')
    expect(formatTime('2026-10-06T11:00:00Z')).toBe('13:00')
    expect(madridHour('2026-12-01T23:00:00+01:00')).toBe(23)
  })

  it('da la franja de una o varias horas', () => {
    expect(formatHourRange('2026-10-06T13:00:00+02:00')).toBe('13–14 h')
    expect(formatHourRange('2026-10-06T22:00:00+02:00', 2)).toBe('22–24 h')
    expect(formatHourRange('2026-10-06T23:00:00+02:00')).toBe('23–24 h')
  })

  it('respeta los cambios de hora', () => {
    expect(formatHourRange('2026-03-29T01:00:00+01:00')).toBe('1–3 h') // la 2:00 no existe
    expect(formatHourRange('2026-10-25T02:00:00+02:00')).toBe('2–3 h') // la 2:00 se repite
    expect(formatHourRange('2026-10-25T02:00:00+01:00')).toBe('2–3 h')
  })
})

describe('fechas', () => {
  it('se escriben como en el prototipo', () => {
    expect(formatDay('2026-10-03')).toBe('sábado 3 de octubre')
    expect(formatShortDay('2026-10-03')).toBe('3 oct')
  })

  it('día de la semana abreviado y periodos', () => {
    expect(formatWeekdayDay('2026-10-04')).toBe('dom 4 oct')
    expect(formatPeriod('2026-10-01', '2026-10-13')).toBe('del 1 oct al 13 oct')
  })

  it('un día de la API es un día de Madrid, sin desplazarse por la zona horaria', () => {
    expect(formatDay('2026-01-01')).toBe('jueves 1 de enero')
  })
})
