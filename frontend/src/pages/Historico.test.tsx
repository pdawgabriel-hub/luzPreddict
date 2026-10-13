import { screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderApp } from '../test/render'

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-10-06T10:00:00Z')) // martes 6 de octubre
})

const summary = () => screen.findByRole('region', { name: 'Resumen del periodo' })
const heatmapRows = () => within(screen.getByRole('table', { name: /^Precio por día y hora/ })).getAllByRole('row').slice(1)

describe('Histórico', () => {
  beforeEach(() => vi.stubEnv('VITE_USE_MOCKS', '1'))

  it('por defecto, los últimos 30 días con su resumen, gráficos y mapa de calor', async () => {
    renderApp('/historico')

    expect(screen.getByText('Cargando el histórico…')).toBeInTheDocument()
    const summary = await screen.findByRole('region', { name: 'Resumen del periodo' })
    expect(summary).toHaveTextContent('del 7 sept al 6 oct')
    expect(summary).toHaveTextContent(/[▲▼] \d+ % frente a los 30 días anteriores/)
    expect(summary).toHaveTextContent(/Hora más barata\d,\d{3} €\/kWh[a-záéíóú]{3} \d+ [a-z]+, \d+ h/)
    expect(summary).toHaveTextContent(/\d+ % del periodo/)

    expect(screen.getByRole('button', { name: '30 días' })).toHaveAttribute('aria-pressed', 'true')
    expect(heatmapRows()).toHaveLength(30)
    expect(within(heatmapRows()[0]).getAllByRole('cell')).toHaveLength(24)
    expect(screen.getByRole('img', { name: /^Precio medio de cada día/ })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: /^Precio medio por hora del día en laborables y en fin de semana/ })).toBeInTheDocument()
    expect(screen.getByText(/^Laborables: lo más barato a las \d{2} h/)).toBeInTheDocument()
    expect(screen.getByText(/^El fin de semana la luz sale un \d+ % más (barata|cara) que entre semana\.$/)).toBeInTheDocument()

    const weekdays = screen.getByRole('region', { name: 'Precio medio por día de la semana' })
    expect(within(weekdays).getAllByRole('term').map((t) => t.textContent)).toEqual([
      'Lunes',
      'Martes',
      'Miércoles',
      'Jueves',
      'Viernes',
      'Sábado',
      'Domingo',
    ])
  })

  it('cambia de periodo y lo guarda en la dirección', async () => {
    const { user } = renderApp('/historico')

    await screen.findByRole('region', { name: 'Resumen del periodo' })
    await user.click(screen.getByRole('button', { name: '7 días' }))

    expect(screen.getByRole('button', { name: '7 días' })).toHaveAttribute('aria-pressed', 'true')
    await vi.waitFor(async () => expect(await summary()).toHaveTextContent('del 30 sept al 6 oct'))
    expect(heatmapRows()).toHaveLength(7)
  })

  it('abre el periodo de la dirección y descarta uno que no existe', async () => {
    renderApp('/historico?dias=14')
    expect(await summary()).toHaveTextContent('del 23 sept al 6 oct')
  })

  it('un periodo no válido vuelve a 30 días', async () => {
    renderApp('/historico?dias=99')
    expect(await summary()).toHaveTextContent('del 7 sept al 6 oct')
  })
})

describe('Histórico con errores', () => {
  it('si fallan los precios, explica el motivo y deja reintentar', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          new Response(JSON.stringify({ error: { code: 'not_found', message: 'No hay precios entre el 2026-09-07 y el 2026-10-06', request_id: 'r9', details: [] } }), { status: 404 }),
        ),
      ),
    )
    const { user } = renderApp('/historico')

    expect(await screen.findByRole('alert')).toHaveTextContent('No hay precios entre el 2026-09-07 y el 2026-10-06')
    vi.stubEnv('VITE_USE_MOCKS', '1')
    await user.click(screen.getByRole('button', { name: 'Reintentar' }))
    expect(await screen.findByRole('region', { name: 'Resumen del periodo' })).toBeInTheDocument()
  })
})
