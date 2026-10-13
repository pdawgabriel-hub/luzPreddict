import { describe, expect, it } from 'vitest'
import { addDays, dayHours, daysBetween, madridDate, toMadridIso, weekday } from './dates'

describe('fechas en hora de Madrid', () => {
  it('un día normal tiene 24 horas desde la medianoche local', () => {
    const hours = dayHours('2026-10-06')
    expect(hours).toHaveLength(24)
    expect(toMadridIso(hours[0])).toBe('2026-10-06T00:00:00+02:00')
    expect(toMadridIso(hours[23])).toBe('2026-10-06T23:00:00+02:00')
  })

  it('el cambio a horario de verano deja un día de 23 horas', () => {
    const hours = dayHours('2026-03-29').map(toMadridIso)
    expect(hours).toHaveLength(23)
    expect(hours.slice(1, 3)).toEqual(['2026-03-29T01:00:00+01:00', '2026-03-29T03:00:00+02:00'])
  })

  it('el cambio a horario de invierno deja un día de 25 horas con la 2:00 repetida', () => {
    const hours = dayHours('2026-10-25').map(toMadridIso)
    expect(hours).toHaveLength(25)
    expect(hours.slice(2, 4)).toEqual(['2026-10-25T02:00:00+02:00', '2026-10-25T02:00:00+01:00'])
  })

  it('el día local no es el día UTC', () => {
    expect(madridDate(new Date('2026-10-06T22:30:00Z'))).toBe('2026-10-07')
  })

  it('suma días y recorre rangos', () => {
    expect(addDays('2026-12-31', 1)).toBe('2027-01-01')
    expect(addDays('2026-03-01', -1)).toBe('2026-02-28')
    expect(daysBetween('2026-10-05', '2026-10-07')).toEqual(['2026-10-05', '2026-10-06', '2026-10-07'])
    expect(weekday('2026-10-06')).toBe(1) // martes
    expect(weekday('2026-10-11')).toBe(6) // domingo
  })
})
