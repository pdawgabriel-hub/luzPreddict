import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Heatmap } from './Heatmap'
import { HourlyBars, type Bar } from './HourlyBars'
import { LineChart } from './LineChart'

const BARS: Bar[] = [10, 50, 30].map((value, hour) => ({
  key: String(hour),
  label: String(hour),
  name: `${hour}–${hour + 1} h`,
  value,
  display: `${value} €/MWh`,
  color: 'var(--color-price-3)',
  current: hour === 1,
}))

describe('HourlyBars', () => {
  it('dibuja una barra por hora, proporcional a su valor', () => {
    render(<HourlyBars bars={BARS} ariaLabel="Precio de hoy" formatTick={String} />)

    const bars = screen.getAllByTestId('bar')
    expect(bars).toHaveLength(3)
    const heights = bars.map((b) => Number(b.getAttribute('height')))
    expect(heights[1]).toBeGreaterThan(heights[2])
    expect(heights[2]).toBeGreaterThan(heights[0])
    expect(bars[1]).toHaveAttribute('data-current', 'true')
    expect(bars[0]).not.toHaveAttribute('data-current')
    expect(bars[0]).toHaveStyle({ fill: 'var(--color-price-3)' })
  })

  it('es accesible: resumen, texto de cada barra y tabla de datos', () => {
    render(<HourlyBars bars={BARS} ariaLabel="Precio de hoy" formatTick={String} valueLabel="Precio" />)

    expect(screen.getByRole('img', { name: 'Precio de hoy' })).toBeInTheDocument()
    expect(screen.getAllByTestId('bar')[1]).toHaveTextContent('1–2 h: 50 €/MWh')
    const table = screen.getByRole('table', { name: 'Precio de hoy' })
    expect(within(table).getAllByRole('row')).toHaveLength(4)
    expect(within(table).getByRole('row', { name: '1–2 h 50 €/MWh' })).toBeInTheDocument()
  })
})

describe('LineChart', () => {
  const props = {
    labels: ['0', '1', '2'],
    series: [
      { key: 'real', label: 'Precio real', color: 'blue', values: [10, 20, null] },
      { key: 'prev', label: 'Previsión', color: 'orange', values: [12, 18, 25], dashed: true },
    ],
    ariaLabel: 'Previsión frente a real',
    formatTick: String,
    formatValue: (v: number) => `${v} €`,
  }

  it('dibuja una línea por serie, cortada donde no hay dato', () => {
    render(<LineChart {...props} />)

    expect(screen.getByTestId('line-real').getAttribute('d')?.match(/[ML]/g)).toHaveLength(2)
    expect(screen.getByTestId('line-prev').getAttribute('d')?.match(/[ML]/g)).toHaveLength(3)
    expect(screen.getByTestId('line-prev')).toHaveAttribute('stroke-dasharray', '6 4')
  })

  it('lleva leyenda y tabla con los huecos marcados', () => {
    render(<LineChart {...props} band={{ label: 'Mínimo – máximo', color: 'grey', lower: [5, 5, 5], upper: [30, 30, 30] }} />)

    const legend = screen.getByRole('list')
    expect(within(legend).getAllByRole('listitem').map((li) => li.textContent)).toEqual(['Precio real', 'Previsión', 'Mínimo – máximo'])
    expect(screen.getByTestId('band')).toBeInTheDocument()
    const table = screen.getByRole('table', { name: 'Previsión frente a real' })
    expect(within(table).getByRole('row', { name: '2 — 25 €' })).toBeInTheDocument()
  })
})

describe('Heatmap', () => {
  const steps = [
    { max: 60, color: 'rgb(1, 1, 1)', label: '< 0,06' },
    { max: Infinity, color: 'rgb(2, 2, 2)', label: '≥ 0,06' },
  ]

  it('es una tabla de días × horas con el color de cada tramo', () => {
    render(
      <Heatmap
        caption="Precio por día y hora"
        columns={['0', '1']}
        rows={[{ key: 'd1', label: '3 oct', values: [40, 90] }, { key: 'd2', label: '4 oct', values: [null, 10] }]}
        steps={steps}
        formatValue={(v) => `${v} €/MWh`}
      />,
    )

    const table = screen.getByRole('table', { name: 'Precio por día y hora' })
    const cells = within(table).getAllByRole('cell')
    expect(cells).toHaveLength(4)
    expect(cells[0]).toHaveStyle({ background: 'rgb(1, 1, 1)' })
    expect(cells[1]).toHaveStyle({ background: 'rgb(2, 2, 2)' })
    expect(cells[2]).toHaveAttribute('data-empty', 'true')
    expect(cells[2]).toHaveTextContent('sin dato')
    expect(cells[1]).toHaveAttribute('title', '3 oct, 1: 90 €/MWh')
    expect(screen.getByRole('region', { name: 'Precio por día y hora' })).toHaveAttribute('tabindex', '0')
    expect(screen.getByText('≥ 0,06')).toBeInTheDocument()
  })
})
