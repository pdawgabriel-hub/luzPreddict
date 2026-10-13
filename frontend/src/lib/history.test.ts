import { describe, expect, it } from 'vitest'
import { dayHours, toMadridIso } from './dates'
import { argExtremes, groupByDay, hourlyProfile, isWeekend, periodStats, weekdayMeans } from './history'

/** Horas de un día con precio = hora de reloj × 10 (o lo que devuelva `price`). */
function day(date: string, price: (i: number) => number = (i) => i * 10) {
  return dayHours(date).map((instant, i) => ({ datetime: toMadridIso(instant), price: price(i) }))
}

describe('histórico', () => {
  it('agrupa por día de Madrid con un valor por hora de reloj', () => {
    const [d1, d2] = groupByDay([...day('2026-10-05'), ...day('2026-10-06', () => 50)])

    expect(d1.day).toBe('2026-10-05')
    expect(d1.byHour).toHaveLength(24)
    expect(d1.byHour[13]).toBe(130)
    expect(d1.mean).toBe(115)
    expect(d1.min.price).toBe(0)
    expect(d1.max.datetime).toBe('2026-10-05T23:00:00+02:00')
    expect(d2.byHour.every((v) => v === 50)).toBe(true)
  })

  it('el día de 25 horas promedia las dos 2:00; el de 23 deja la 2:00 vacía', () => {
    const [autumn] = groupByDay(day('2026-10-25')) // 0, 10, 20 (2:00 verano), 30 (2:00 invierno), 40…
    const [spring] = groupByDay(day('2026-03-29'))

    expect(autumn.byHour[2]).toBe(25)
    expect(autumn.byHour[3]).toBe(40)
    expect(spring.byHour[2]).toBeNull()
    expect(spring.byHour[3]).toBe(20)
  })

  it('resume el periodo', () => {
    const stats = periodStats(day('2026-10-06'), 100)
    expect(stats.mean).toBe(115)
    expect(stats.min.price).toBe(0)
    expect(stats.max.price).toBe(230)
    expect(stats.below).toBe(10) // de 0 a 90
    expect(stats.total).toBe(24)
  })

  it('perfil por hora y media por día de la semana', () => {
    const days = groupByDay([...day('2026-10-05', () => 100), ...day('2026-10-12', () => 200), ...day('2026-10-11', () => 50)])

    expect(hourlyProfile(days.filter((d) => !isWeekend(d.day)))[8]).toBe(150) // los dos lunes
    expect(weekdayMeans(days)).toEqual([150, null, null, null, null, null, 50])
    expect(isWeekend('2026-10-10')).toBe(true) // sábado
    expect(isWeekend('2026-10-09')).toBe(false)
  })

  it('mínimo y máximo sin contar los huecos', () => {
    expect(argExtremes([null, 5, 2, 9, null])).toEqual({ min: 2, max: 3 })
    expect(argExtremes([null])).toEqual({ min: -1, max: -1 })
  })
})
