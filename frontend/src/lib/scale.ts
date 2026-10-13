// Escalas para los gráficos SVG.

/** Función lineal que lleva [d0, d1] a [r0, r1]. */
export function linearScale([d0, d1]: [number, number], [r0, r1]: [number, number]): (value: number) => number {
  const span = d1 - d0 || 1
  return (value) => r0 + ((value - d0) / span) * (r1 - r0)
}

/** Mínimo y máximo, sin contar los huecos (null). */
export function extent(values: readonly (number | null)[]): [number, number] {
  const present = values.filter((v): v is number => v !== null && Number.isFinite(v))
  if (!present.length) return [0, 1]
  return [Math.min(...present), Math.max(...present)]
}

/** Marcas "redondas" del eje (pasos de 1, 2 o 5 × 10ⁿ) que cubren [min, max]. */
export function niceTicks(min: number, max: number, count = 4): number[] {
  if (min === max) max = min + 1
  // Paso de 1, 2 o 5 × 10ⁿ más cercano al ideal (mismo criterio que d3)
  const rough = (max - min) / count
  const power = 10 ** Math.floor(Math.log10(rough))
  const error = rough / power
  const step = power * (error >= Math.sqrt(50) ? 10 : error >= Math.sqrt(10) ? 5 : error >= Math.sqrt(2) ? 2 : 1)
  const first = Math.floor(min / step) * step
  const ticks: number[] = []
  for (let tick = first; tick <= max + step * 1e-9; tick += step) ticks.push(Number(tick.toFixed(10)))
  if (ticks[ticks.length - 1] < max) ticks.push(Number((ticks[ticks.length - 1] + step).toFixed(10)))
  return ticks
}

/** Índices de las etiquetas que caben en `width` px sin solaparse (siempre el primero). */
export function labelIndices(count: number, width: number, minSpacing = 36): number[] {
  const every = Math.max(1, Math.ceil(count / Math.max(1, Math.floor(width / minSpacing))))
  return Array.from({ length: count }, (_, i) => i).filter((i) => i % every === 0)
}
