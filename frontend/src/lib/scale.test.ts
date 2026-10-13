import { describe, expect, it } from 'vitest'
import { bandPath, linePath, stepFor } from './chart'
import { extent, labelIndices, linearScale, niceTicks } from './scale'

describe('escalas', () => {
  it('lleva el dominio al rango, también invertido (el eje Y crece hacia arriba)', () => {
    const y = linearScale([0, 200], [100, 0])
    expect(y(0)).toBe(100)
    expect(y(200)).toBe(0)
    expect(y(50)).toBe(75)
  })

  it('el extremo ignora los huecos', () => {
    expect(extent([3, null, 9, 1])).toEqual([1, 9])
    expect(extent([null])).toEqual([0, 1])
  })

  it.each([
    [0, 252, [0, 50, 100, 150, 200, 250, 300]],
    [48, 218, [0, 50, 100, 150, 200, 250]],
    [0, 0.9, [0, 0.2, 0.4, 0.6, 0.8, 1]],
    [-12, 30, [-20, -10, 0, 10, 20, 30]],
  ])('marcas redondas de %s a %s', (min, max, ticks) => {
    expect(niceTicks(min, max)).toEqual(ticks)
  })

  it('reparte las etiquetas para que no se solapen', () => {
    expect(labelIndices(24, 1000)).toHaveLength(24)
    expect(labelIndices(24, 300, 36)).toEqual([0, 3, 6, 9, 12, 15, 18, 21])
  })
})

describe('trazos y colores', () => {
  it('una línea se corta en los huecos', () => {
    expect(
      linePath([
        [0, 10],
        [1, 20],
        [2, null],
        [3, 5],
      ]),
    ).toBe('M0.0,10.0L1.0,20.0M3.0,5.0')
  })

  it('la banda solo cubre los tramos con los dos bordes', () => {
    expect(bandPath([0, 1, 2], [5, 6, null], [1, 2, 3])).toBe('M0.0,1.0L1.0,2.0L1.0,6.0L0.0,5.0Z')
  })

  it('cada valor cae en su tramo de color', () => {
    const steps = [
      { max: 60, color: 'a', label: '< 60' },
      { max: 120, color: 'b', label: '60–120' },
      { max: Infinity, color: 'c', label: '> 120' },
    ]
    expect([0, 60, 61, 500].map((v) => stepFor(v, steps).color)).toEqual(['a', 'a', 'b', 'c'])
  })
})
