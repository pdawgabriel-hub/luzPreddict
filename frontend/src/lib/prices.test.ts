import { describe, expect, it } from 'vitest'
import { changePct, cheaperHours, cheapestHours, currentHourIndex, mean, priciestWindow, tierCuts, tierOf } from './prices'

const hours = (prices: number[]) => prices.map((price, i) => ({ datetime: `2026-10-06T${String(i).padStart(2, '0')}:00:00+02:00`, price }))

describe('cálculos del panel', () => {
  it('reparte el día en tercios: barata, media y cara', () => {
    const prices = Array.from({ length: 24 }, (_, i) => i + 1)
    const cuts = tierCuts(prices)
    expect(cuts).toEqual({ low: 8, high: 17 })
    expect(prices.map((p) => tierOf(p, cuts)).filter((t) => t === 'cheap')).toHaveLength(8)
    expect(prices.map((p) => tierOf(p, cuts)).filter((t) => t === 'high')).toHaveLength(8)
  })

  it('encuentra la hora en curso', () => {
    const day = hours([1, 2, 3])
    expect(currentHourIndex(day, new Date('2026-10-06T01:30:00+02:00'))).toBe(1)
    expect(currentHourIndex(day, new Date('2026-10-06T05:00:00+02:00'))).toBe(-1)
  })

  it('ordena las horas más baratas y, con empate, la más temprana', () => {
    expect(cheapestHours(hours([5, 1, 3, 1]), 3).map((h) => h.price)).toEqual([1, 1, 3])
    expect(cheapestHours(hours([5, 1, 3, 1]), 1)[0].datetime).toContain('T01:')
  })

  it('la franja más cara de 3 horas y su máximo', () => {
    expect(priciestWindow(hours([1, 9, 8, 7, 2, 10]), 3)).toEqual({ start: 1, max: 9 })
    expect(priciestWindow(hours([1, 2]), 3)).toBeNull()
  })

  it('compara días', () => {
    expect(mean([1, 2, 3])).toBe(2)
    expect(changePct(100, 112)).toBeCloseTo(12)
    expect(cheaperHours(hours([10, 10, 10]), hours([5, 15, 9]))).toBe(2)
  })
})
