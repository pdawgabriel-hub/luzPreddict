import { screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { renderApp } from '../test/render'

describe('Panel', () => {
  it('con datos de ejemplo funciona sin API', async () => {
    vi.stubEnv('VITE_USE_MOCKS', '1')
    renderApp('/')

    expect(screen.getByRole('status')).toHaveTextContent('Conectando con la API…')
    expect(await screen.findByText(/^Datos de ejemplo \(ok\)/)).toBeInTheDocument()
  })

  it('avisa si la API no responde', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    renderApp('/')

    expect(await screen.findByText(/Sin conexión con la API: Failed to fetch/)).toBeInTheDocument()
  })
})
