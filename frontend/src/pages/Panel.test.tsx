import { screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { renderApp } from '../test/render'

const HEALTH = { status: 'ok', warnings: [], prices: { last_day: '2026-10-10', last_hour: null, has_tomorrow: false }, forecast: null, model: null }
const respond = (status: number, body: unknown) => () => Promise.resolve(new Response(JSON.stringify(body), { status }))

describe('Panel', () => {
  it('muestra la carga y después los datos', async () => {
    vi.stubEnv('VITE_USE_MOCKS', '1')
    renderApp('/')

    expect(screen.getByText('Conectando con la API…')).toBeInTheDocument()
    expect(await screen.findByText(/^Datos de ejemplo \(ok\)/)).toBeInTheDocument()
  })

  it('si falla, explica el motivo y deja reintentar', async () => {
    const notFound = { error: { code: 'not_found', message: 'No hay precios del 2026-10-10', request_id: 'abc123', details: [] } }
    vi.stubGlobal('fetch', vi.fn().mockImplementation(respond(404, notFound)))
    const { user } = renderApp('/')

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('No se han podido cargar los datos')
    expect(alert).toHaveTextContent('No hay precios del 2026-10-10')
    expect(alert).toHaveTextContent('Id de la petición: abc123')

    vi.stubGlobal('fetch', vi.fn().mockImplementation(respond(200, HEALTH)))
    await user.click(screen.getByRole('button', { name: 'Reintentar' }))

    expect(await screen.findByText(/^API conectada \(ok\)/)).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
