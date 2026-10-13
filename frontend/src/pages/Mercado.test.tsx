import { screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderApp } from '../test/render'

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-10-06T10:00:00Z')) // martes 6 de octubre
})

describe('Mercado', () => {
  beforeEach(() => vi.stubEnv('VITE_USE_MOCKS', '1'))

  it('resume el periodo sin contar el día en curso, que REE aún actualiza', async () => {
    renderApp('/mercado')

    expect(screen.getByText('Cargando el mix de generación…')).toBeInTheDocument()
    const summary = await screen.findByRole('region', { name: 'Resumen' })
    expect(summary).toHaveTextContent(/Renovables, últimos 29 días\d+,\d %de toda la generación/)
    expect(summary).toHaveTextContent(/Día más renovable\d+,\d %[a-záéíóú]+ \d+ de [a-z]+/)
    expect(summary).toHaveTextContent(/Precio con más renovables[−+]\d+ %\d+ frente a \d+ €\/MWh de media/)
  })

  it('el mix muestra los 7 grupos y cambia entre el último día y el periodo', async () => {
    const { user } = renderApp('/mercado')

    const mix = await screen.findByRole('region', { name: 'Mix de generación' })
    const items = within(mix).getAllByRole('listitem')
    expect(items.map((li) => li.textContent?.replace(/[\d,]+ %$/, ''))).toEqual([
      'Eólica',
      'Solar',
      'Hidráulica',
      'Otras renovables',
      'Nuclear',
      'Ciclo combinado',
      'Cogeneración y otras',
    ])
    const lastDay = within(mix).getByRole('img').getAttribute('aria-label')
    expect(within(mix).getByRole('button', { name: '5 oct' })).toHaveAttribute('aria-pressed', 'true')

    await user.click(within(mix).getByRole('button', { name: 'Últimos 29 días' }))
    expect(within(mix).getByRole('img').getAttribute('aria-label')).not.toBe(lastDay)
  })

  it('la tecnología elegida se compara día a día con el precio', async () => {
    const { user } = renderApp('/mercado')

    const section = await screen.findByRole('region', { name: 'Renovables y precio, día a día' })
    // En los datos de ejemplo, como en la realidad, más renovables = precio más bajo
    expect(section).toHaveTextContent(/Correlación −\d,\d{2} \(\w+\): cuando hay más renovable, el precio tiende a bajar/)
    expect(within(section).getAllByRole('button', { name: /^[a-záéíóú]+ \d+ de [a-z]+: / })).toHaveLength(29)

    await user.click(within(section).getByRole('button', { name: 'Ciclo combinado' }))
    expect(screen.getByRole('heading', { name: 'Ciclo combinado y precio, día a día' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: '% de ciclo combinado en el mix cada día' })).toBeInTheDocument()
  })

  it('ordena las tecnologías por su correlación con el precio', async () => {
    renderApp('/mercado')

    const ranking = await screen.findByRole('region', { name: '¿Qué tecnología va con el precio?' })
    const values = within(ranking)
      .getAllByRole('listitem')
      .map((li) => Number(li.textContent?.match(/[−-]?\d,\d{2}$/)?.[0].replace('−', '-').replace(',', '.')))
    expect(values).toHaveLength(7)
    expect([...values].sort((a, b) => a - b)).toEqual(values)
    expect(ranking).toHaveTextContent('no qué causa qué')

    const quartiles = screen.getByRole('region', { name: 'Días muy renovables frente a días poco renovables' })
    expect(quartiles).toHaveTextContent(/7 días con más renovables/)
  })
})

describe('Mercado con errores', () => {
  it('si falla la API, explica el motivo y deja reintentar', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          new Response(JSON.stringify({ error: { code: 'not_found', message: 'No hay datos de generación', request_id: 'r3', details: [] } }), { status: 404 }),
        ),
      ),
    )
    renderApp('/mercado')

    expect(await screen.findByRole('alert')).toHaveTextContent('No hay datos de generación')
    expect(screen.getByRole('button', { name: 'Reintentar' })).toBeInTheDocument()
  })
})
