// Cálculos de la página de mercado: grupos de tecnologías, % en el mix y correlación con el precio.

import { mean } from './prices'

export type TechGroup = { name: string; color: string; renewable: boolean; technologies: string[] }

// Las tecnologías de REE, agrupadas como en el prototipo. "Cogeneración y otras" recoge el resto.
export const GROUPS: TechGroup[] = [
  { name: 'Eólica', color: 'var(--color-tech-wind)', renewable: true, technologies: ['Eólica'] },
  { name: 'Solar', color: 'var(--color-tech-solar)', renewable: true, technologies: ['Solar fotovoltaica', 'Solar térmica'] },
  { name: 'Hidráulica', color: 'var(--color-tech-hydro)', renewable: true, technologies: ['Hidráulica'] },
  {
    name: 'Otras renovables',
    color: 'var(--color-tech-other-renewable)',
    renewable: true,
    technologies: ['Otras renovables', 'Residuos renovables', 'Hidroeólica'],
  },
  { name: 'Nuclear', color: 'var(--color-tech-nuclear)', renewable: false, technologies: ['Nuclear'] },
  { name: 'Ciclo combinado', color: 'var(--color-tech-gas)', renewable: false, technologies: ['Ciclo combinado'] },
  { name: 'Cogeneración y otras', color: 'var(--color-tech-other)', renewable: false, technologies: [] },
]

const LISTED = new Set(GROUPS.flatMap((g) => g.technologies))

/** % de cada grupo en un mix (MWh por tecnología de REE). */
export function groupShares(mix: Record<string, number>): Record<string, number> {
  const total = Object.values(mix).reduce((a, b) => a + b, 0)
  const shares: Record<string, number> = {}
  for (const group of GROUPS) {
    const mwh = Object.entries(mix)
      .filter(([tech]) => (group.technologies.length ? group.technologies.includes(tech) : !LISTED.has(tech)))
      .reduce((a, [, value]) => a + value, 0)
    shares[group.name] = total > 0 ? (mwh / total) * 100 : 0
  }
  return shares
}

/** Coeficiente de correlación de Pearson; null si alguna serie no varía. */
export function pearson(a: readonly number[], b: readonly number[]): number | null {
  const ma = mean(a)
  const mb = mean(b)
  let ab = 0
  let aa = 0
  let bb = 0
  a.forEach((v, i) => {
    ab += (v - ma) * (b[i] - mb)
    aa += (v - ma) ** 2
    bb += (b[i] - mb) ** 2
  })
  return aa && bb ? ab / Math.sqrt(aa * bb) : null
}

export function strength(r: number): 'fuerte' | 'moderada' | 'débil' {
  const abs = Math.abs(r)
  return abs >= 0.5 ? 'fuerte' : abs >= 0.3 ? 'moderada' : 'débil'
}

/** Precio medio del cuarto de días más renovable frente al cuarto menos renovable. */
export function quartileComparison(days: readonly { renewable: number; price: number }[]) {
  const sorted = [...days].sort((x, y) => y.renewable - x.renewable)
  const size = Math.max(1, Math.floor(sorted.length / 4))
  const top = sorted.slice(0, size)
  const bottom = sorted.slice(-size)
  return { size, high: mean(top.map((d) => d.price)), low: mean(bottom.map((d) => d.price)) }
}
