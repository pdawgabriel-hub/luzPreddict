import { screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { modelReport, prices } from '../mocks/data'
import { renderApp } from '../test/render'

const NOW = new Date('2026-10-06T10:00:00Z') // martes 6 de octubre

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(NOW)
})

const metrics = () => screen.getByRole('region', { name: 'Métricas' })

describe('Modelo', () => {
  beforeEach(() => vi.stubEnv('VITE_USE_MOCKS', '1'))

  it('evalúa LightGBM con las previsiones guardadas y muestra el backtest', async () => {
    renderApp('/modelo')

    expect(screen.getByText('Cargando la evaluación del modelo…')).toBeInTheDocument()
    await screen.findByRole('region', { name: 'Métricas' })
    expect(screen.getByRole('button', { name: 'LightGBM (en uso)' })).toHaveAttribute('aria-pressed', 'true')
    expect(metrics()).toHaveTextContent(/Error medio por hora · LightGBM[\d,]+ €\/MWh14 días evaluados \(del 23 sept al 6 oct\)/)
    expect(metrics()).toHaveTextContent('Mejora frente a la mejor referencia32,4 %Backtest de 90 días')
    expect(metrics()).toHaveTextContent(/Modelo en uso21,9 €\/MWhEntrenado el \w+ \d+ de \w+ con 17\.520 horas/)

    expect(screen.getByRole('img', { name: 'Precio real y previsión de LightGBM, en €/MWh' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Error medio de LightGBM por hora del día, en €/MWh' })).toBeInTheDocument()
    expect(screen.getByText(/^Falla más a las \d+ h/)).toBeInTheDocument()
    expect(screen.getByText(/^Mejor día: \d+ \w+ \([\d,]+ €\/MWh\)\. Peor día:/)).toBeInTheDocument()

    const backtest = screen.getByRole('table', { name: 'Comparativa de modelos' })
    expect(within(backtest).getAllByRole('rowheader').map((r) => r.textContent?.trim())).toEqual(['LightGBM En uso', 'Media 7 días', 'Precio de ayer'])
    expect(screen.getByText(/el precio real cayó dentro en el 79,5 % de las horas \(se busca el 80 %\), con un rango medio de 54,8 €\/MWh\./)).toBeInTheDocument()
    expect(screen.getByText(/^Rango probable: el precio real cayó dentro en el \d+ % de las \d+ horas evaluadas que lo tienen\.$/)).toBeInTheDocument()
  })

  it('las referencias se calculan con los precios y se comparan por tipo de día', async () => {
    const { user } = renderApp('/modelo')
    await screen.findByRole('region', { name: 'Métricas' })

    await user.click(screen.getByRole('button', { name: 'Precio de ayer' }))
    expect(metrics()).toHaveTextContent(/Error medio por hora · Precio de ayer[\d,]+ €\/MWh14 días evaluados/)
    expect(screen.queryByText(/^Rango probable:/)).not.toBeInTheDocument() // las referencias no tienen rango
    expect(screen.getByRole('img', { name: 'Precio real y previsión de Precio de ayer, en €/MWh' })).toBeInTheDocument()

    const dayTypes = screen.getByRole('table', { name: 'Laborables frente a fin de semana' })
    const rows = within(dayTypes).getAllByRole('row').slice(1)
    expect(rows.map((r) => within(r).getByRole('rowheader').textContent)).toEqual([
      'LightGBM (10 + 4 días)',
      'Media 7 días (10 + 4 días)',
      'Precio de ayer (10 + 4 días)',
    ])
    expect(dayTypes.querySelectorAll('td[data-best]')).toHaveLength(2) // el mejor de cada columna
  })

  it('se puede ver la previsión de un solo día', async () => {
    const { user } = renderApp('/modelo')
    const section = await screen.findByRole('region', { name: 'Previsión frente a precio real' })

    await user.click(within(section).getByRole('button', { name: '5 oct' }))

    expect(section).toHaveTextContent(/LightGBM · lunes 5 de octubre · error medio [\d,]+ €\/MWh/)
    const table = within(section).getByRole('table')
    expect(within(table).getAllByRole('row')).toHaveLength(25) // cabecera + 24 horas
    expect(within(table).getByRole('rowheader', { name: '14 h' })).toBeInTheDocument()

    await user.click(within(section).getByRole('button', { name: 'Todos' }))
    expect(within(section).getByRole('rowheader', { name: '5 oct, 14 h' })).toBeInTheDocument() // cada fila, con su día
  })
})

describe('Modelo sin previsiones guardadas', () => {
  it('explica que LightGBM aún no tiene días evaluados, pero sí las referencias', async () => {
    const json = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status }))
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        if (url.startsWith('/api/model')) return json(modelReport(NOW, 30))
        if (url.startsWith('/v1/prices')) return json(prices('2026-09-16', '2026-10-06', '2026-10-06'))
        return json({ error: { code: 'not_found', message: 'No hay previsión', request_id: 'r', details: [] } }, 404)
      }),
    )
    const { user } = renderApp('/modelo')

    expect(await screen.findByText(/^Todavía no hay previsiones de LightGBM con su precio real/)).toBeInTheDocument()
    expect(metrics()).toHaveTextContent('Sin días evaluados todavía')

    await user.click(screen.getByRole('button', { name: 'Media 7 días' }))
    expect(screen.getByRole('img', { name: 'Precio real y previsión de Media 7 días, en €/MWh' })).toBeInTheDocument()
  })
})
