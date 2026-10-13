import { describe, expect, it } from 'vitest'
import { GROUPS, groupShares, pearson, quartileComparison, strength } from './market'

describe('mercado', () => {
  it('agrupa las tecnologías de REE como en el prototipo; el resto va a "Cogeneración y otras"', () => {
    const shares = groupShares({
      Eólica: 300,
      'Solar fotovoltaica': 150,
      'Solar térmica': 50,
      Nuclear: 200,
      'Ciclo combinado': 200,
      Carbón: 60,
      Cogeneración: 40,
    })

    expect(shares.Solar).toBe(20)
    expect(shares.Eólica).toBe(30)
    expect(shares['Cogeneración y otras']).toBe(10)
    expect(shares['Otras renovables']).toBe(0)
    expect(Object.values(shares).reduce((a, b) => a + b, 0)).toBeCloseTo(100)
    expect(GROUPS.filter((g) => g.renewable).map((g) => g.name)).toEqual(['Eólica', 'Solar', 'Hidráulica', 'Otras renovables'])
  })

  it('correlación de Pearson', () => {
    expect(pearson([1, 2, 3], [2, 4, 6])).toBeCloseTo(1)
    expect(pearson([1, 2, 3], [6, 4, 2])).toBeCloseTo(-1)
    expect(pearson([1, 1, 1], [1, 2, 3])).toBeNull()
    expect([0.6, -0.35, 0.1].map(strength)).toEqual(['fuerte', 'moderada', 'débil'])
  })

  it('compara el cuarto de días más renovable con el menos renovable', () => {
    const days = [10, 20, 30, 40, 50, 60, 70, 80].map((renewable) => ({ renewable, price: 200 - renewable }))
    expect(quartileComparison(days)).toEqual({ size: 2, high: 125, low: 185 })
  })
})
