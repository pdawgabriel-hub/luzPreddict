// Cálculos de los gráficos, separados de los componentes para probarlos sin dibujar.

export type Step = { max: number; color: string; label: string } // valores ≤ max (el último, Infinity)

export function stepFor(value: number, steps: Step[]): Step {
  return steps.find((step) => value <= step.max) ?? steps[steps.length - 1]
}

export type Point = [number, number | null]

/** Trazo SVG de una línea; los huecos (null) la cortan. */
export function linePath(points: Point[]): string {
  let path = ''
  let drawing = false
  for (const [x, y] of points) {
    if (y === null) {
      drawing = false
      continue
    }
    path += `${drawing ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`
    drawing = true
  }
  return path
}

/** Área entre dos líneas (banda), solo donde las dos tienen valor. */
export function bandPath(xs: number[], lower: (number | null)[], upper: (number | null)[]): string {
  const segments: string[] = []
  let run: number[] = []
  const close = () => {
    if (run.length) {
      const top = run.map((i) => `${xs[i].toFixed(1)},${(upper[i] as number).toFixed(1)}`)
      const bottom = [...run].reverse().map((i) => `${xs[i].toFixed(1)},${(lower[i] as number).toFixed(1)}`)
      segments.push(`M${top.join('L')}L${bottom.join('L')}Z`)
    }
    run = []
  }
  xs.forEach((_, i) => (lower[i] === null || upper[i] === null ? close() : run.push(i)))
  close()
  return segments.join('')
}
