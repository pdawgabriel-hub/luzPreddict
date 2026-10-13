import { describe, expect, it } from 'vitest'
import { dayHours, toMadridIso } from './dates'
import { groupByDay } from './history'
import { baselineForecast, evaluateBaseline, intervalCoverage, mae, maeByDay, maeByDayType, maeByHour, type EvaluatedDay } from './model'

/** Días seguidos desde el 1 de octubre de 2026; cada uno con precio = (día + 1) × 10 en todas las horas. */
function days(n: number, price = (d: number, _h: number) => (d + 1) * 10) {
  const hours = Array.from({ length: n }, (_, d) => {
    const day = `2026-10-${String(d + 1).padStart(2, '0')}`
    return dayHours(day).map((instant, h) => ({ datetime: toMadridIso(instant), price: price(d, h) }))
  }).flat()
  return groupByDay(hours)
}

describe('referencias (mismas reglas que src/models/baselines.py)', () => {
  it('precio de ayer: la misma hora del día anterior', () => {
    expect(baselineForecast(days(3), 2, 'precio_ayer')[8]).toBe(20)
  })

  it('media 7 días: la media de esa hora en los 7 días anteriores', () => {
    expect(baselineForecast(days(9), 8, 'media_7_dias')[8]).toBe(50) // días 2…8 → 20…80
  })

  it('sin 7 días anteriores, la media usa el precio de ayer como respaldo', () => {
    expect(baselineForecast(days(3), 2, 'media_7_dias')[8]).toBe(20)
  })

  it('la 2:00 que no existe el día del cambio a horario de verano usa el respaldo', () => {
    const hours = ['2026-03-28', '2026-03-29', '2026-03-30'].flatMap((day) => dayHours(day).map((i) => ({ datetime: toMadridIso(i), price: 100 })))
    const grouped = groupByDay(hours)
    expect(grouped[1].byHour[2]).toBeNull()
    expect(baselineForecast(grouped, 2, 'precio_ayer')[2]).toBe(100) // media del día anterior
  })

  it('evalúa desde el día pedido y solo donde hay previsión', () => {
    const evaluated = evaluateBaseline(days(5), 'precio_ayer', '2026-10-03')
    expect(evaluated.map((d) => d.day)).toEqual(['2026-10-03', '2026-10-04', '2026-10-05'])
    expect(mae(evaluated)).toBe(10) // cada día sube 10
  })
})

describe('errores', () => {
  const evaluated: EvaluatedDay[] = [
    { day: '2026-10-09', points: [{ hour: 0, actual: 100, predicted: 110 }, { hour: 1, actual: 100, predicted: 70 }] }, // viernes
    { day: '2026-10-10', points: [{ hour: 0, actual: 100, predicted: 100 }, { hour: 1, actual: 100, predicted: 120 }] }, // sábado
  ]

  it('por hora, por día y por tipo de día', () => {
    expect(mae(evaluated)).toBe(15)
    expect(maeByHour(evaluated).slice(0, 3)).toEqual([5, 25, null])
    expect(maeByDay(evaluated)).toEqual([
      { day: '2026-10-09', mae: 20 },
      { day: '2026-10-10', mae: 10 },
    ])
    expect(maeByDayType(evaluated)).toEqual({ workdays: { mae: 20, days: 1 }, weekend: { mae: 10, days: 1 } })
    expect(mae([])).toBeNull()
  })

  it('cobertura del rango probable: solo cuentan las horas que lo tienen, con los bordes dentro', () => {
    const withRange: EvaluatedDay[] = [
      {
        day: '2026-10-09',
        points: [
          { hour: 0, actual: 100, predicted: 110, lower: 90, upper: 130 }, // dentro
          { hour: 1, actual: 100, predicted: 70, lower: 50, upper: 90 }, // fuera
          { hour: 2, actual: 100, predicted: 100, lower: 100, upper: 100 }, // en el borde
          { hour: 3, actual: 100, predicted: 100, lower: null, upper: null }, // sin rango
        ],
      },
    ]

    expect(intervalCoverage(withRange)).toEqual({ coverage: 2 / 3, hours: 3 })
    expect(intervalCoverage(evaluated)).toBeNull()
  })
})
