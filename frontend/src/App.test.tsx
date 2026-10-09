import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import App from './App'

describe('App', () => {
  it('con datos de ejemplo funciona sin API', async () => {
    vi.stubEnv('VITE_USE_MOCKS', '1')
    render(<App />)

    expect(screen.getByRole('status')).toHaveTextContent('Conectando con la API…')
    expect(await screen.findByText(/^Datos de ejemplo \(ok\)/)).toBeInTheDocument()
  })

  it('avisa si la API no responde', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    render(<App />)

    expect(await screen.findByText(/Sin conexión con la API: Failed to fetch/)).toBeInTheDocument()
  })
})
