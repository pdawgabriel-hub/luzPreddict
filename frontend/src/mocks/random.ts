// Números pseudoaleatorios con semilla: los mismos datos de ejemplo para el mismo día.

/** Generador mulberry32: devuelve números en [0, 1). */
export function seeded(seed: string): () => number {
  let state = 0
  for (const char of seed) state = (Math.imul(state, 31) + char.charCodeAt(0)) | 0
  return () => {
    state = (state + 0x6d2b79f5) | 0
    let t = Math.imul(state ^ (state >>> 15), 1 | state)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}
