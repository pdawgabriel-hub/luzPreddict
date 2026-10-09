import { describe, expect, it } from 'vitest'
import css from './tokens.css?raw'

// Lee los colores de tokens.css y comprueba el contraste de las parejas que usa la web.
const tokens = Object.fromEntries([...css.matchAll(/--([\w-]+):\s*(#[0-9a-f]{6})\b/gi)].map((m) => [m[1], m[2]]))

function luminance(hex: string): number {
  const channels = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
  const [r, g, b] = channels.map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4))
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

function contrast(foreground: string, background: string): number {
  const [light, dark] = [luminance(tokens[foreground]), luminance(tokens[background])].sort((a, b) => b - a)
  return (light + 0.05) / (dark + 0.05)
}

// Texto normal: 4,5:1 (WCAG AA)
const TEXT_PAIRS: [string, string][] = [
  ['color-text', 'color-bg'],
  ['color-text', 'color-surface'],
  ['color-text-muted', 'color-bg'],
  ['color-text-muted', 'color-surface'],
  ['color-text-muted', 'color-surface-muted'],
  ['color-text-muted', 'color-surface-sunken'],
  ['color-text-inverse', 'color-inverse'],
  ['color-text-inverse-muted', 'color-inverse'],
  ['color-text-inverse-muted', 'color-inverse-raised'],
  ['color-code-inverse', 'color-inverse'],
  ['color-accent', 'color-surface'],
  ['color-accent', 'color-bg'],
  ['color-text-inverse', 'color-accent'],
  ['color-cheap-text', 'color-cheap-bg'],
  ['color-expensive-text', 'color-expensive-bg'],
  ['color-success-text', 'color-success-bg'],
  ['color-danger-text', 'color-danger-bg'],
  ['color-danger-text', 'color-surface'],
  ['color-text', 'color-brand'],
  ['color-text', 'color-brand-soft'],
]

// Bordes de campos y botones: 3:1 (WCAG 1.4.11)
const UI_PAIRS: [string, string][] = [
  ['color-border-strong', 'color-surface'],
  ['color-border-strong', 'color-bg'],
  ['color-accent', 'color-surface'],
]

describe('tokens de color', () => {
  it('se leen de tokens.css', () => {
    expect(Object.keys(tokens).length).toBeGreaterThan(40)
    expect(tokens['color-accent']).toBe('#1f4e9c')
  })

  it.each(TEXT_PAIRS)('el texto %s sobre %s se lee bien (≥ 4,5:1)', (foreground, background) => {
    expect(contrast(foreground, background)).toBeGreaterThanOrEqual(4.5)
  })

  it.each(UI_PAIRS)('el borde %s se distingue sobre %s (≥ 3:1)', (foreground, background) => {
    expect(contrast(foreground, background)).toBeGreaterThanOrEqual(3)
  })

  it('el precio publicado y la previsión usan escalas distintas', () => {
    const published = [1, 2, 3, 4, 5].map((i) => tokens[`color-price-${i}`])
    const forecast = [1, 2, 3].map((i) => tokens[`color-forecast-${i}`])
    expect(published.filter((c) => forecast.includes(c))).toEqual([])
  })
})
