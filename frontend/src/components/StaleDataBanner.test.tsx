import { screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { renderApp } from '../test/render'

const health = (status: string, warnings: string[]) => ({
  status,
  warnings,
  prices: { last_day: '2026-10-08', last_hour: null, has_tomorrow: false },
  forecast: null,
  model: null,
})
const respond = (status: number, body: unknown) => vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify(body), { status })))

describe('aviso de datos desactualizados', () => {
  it('muestra los avisos de /health cuando los datos están desactualizados', async () => {
    vi.stubGlobal('fetch', respond(200, health('degraded', ['El último precio es del 2026-10-08: faltan los de hoy'])))
    renderApp('/historico')

    expect(await screen.findByText('Los datos pueden estar desactualizados.')).toBeInTheDocument()
    expect(screen.getByText('El último precio es del 2026-10-08: faltan los de hoy')).toBeInTheDocument()
  })

  it('no muestra nada si los datos están al día', async () => {
    const fetchMock = respond(200, health('ok', []))
    vi.stubGlobal('fetch', fetchMock)
    renderApp('/historico')

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled())
    expect(screen.queryByText('Los datos pueden estar desactualizados.')).not.toBeInTheDocument()
  })

  it('si /health falla no muestra nada (cada página enseña su error)', async () => {
    const fetchMock = respond(404, { error: { code: 'not_found', message: 'x', request_id: null, details: [] } })
    vi.stubGlobal('fetch', fetchMock)
    renderApp('/historico')

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled())
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.queryByText('Los datos pueden estar desactualizados.')).not.toBeInTheDocument()
  })

  it('con datos de ejemplo lo dice, y el escenario "stale" muestra el aviso', async () => {
    vi.stubEnv('VITE_USE_MOCKS', '1')
    vi.stubEnv('VITE_MOCK_SCENARIO', 'stale')
    renderApp('/historico')

    expect(screen.getByText('datos de ejemplo')).toBeInTheDocument()
    expect(await screen.findByText(/faltan los de hoy/)).toBeInTheDocument()
  })
})
