import { screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderApp } from '../test/render'

const BEFORE_PUBLISHING = new Date('2026-10-06T16:00:00Z') // 18:00 en Madrid
const AFTER_PUBLISHING = new Date('2026-10-06T19:30:00Z') // 21:30 en Madrid

function at(now: Date) {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(now)
}

const summary = () => screen.getByRole('region', { name: 'Resumen' })
const planSection = () => screen.getByRole('region', { name: 'Plan del día' })
const removeButtons = () => screen.queryAllByRole('button', { name: /^Quitar / })

async function ready() {
  await screen.findByRole('region', { name: 'Resumen' })
  await vi.waitFor(() => expect(planSection()).toHaveAttribute('aria-busy', 'false'))
}

describe('Planificador', () => {
  beforeEach(() => vi.stubEnv('VITE_USE_MOCKS', '1'))

  it('antes de que REE publique planifica hoy, con las 4 tareas de ejemplo', async () => {
    at(BEFORE_PUBLISHING)
    renderApp('/planificador')
    await ready()

    expect(screen.getByText('Planificador · hoy, martes 6 de octubre')).toBeInTheDocument()
    expect(screen.getByText(/se publican hacia las 20:15; hasta entonces se planifica hoy/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '4,6 kW' })).toHaveAttribute('aria-pressed', 'true')
    expect(removeButtons().map((b) => b.getAttribute('aria-label'))).toEqual(['Quitar Coche eléctrico', 'Quitar Lavadora', 'Quitar Lavavajillas', 'Quitar Horno'])
    expect(summary()).toHaveTextContent(/Con el plan\d+,\d{2} €[\d,]+ kWh en 4 de 4 tareas/)
    expect(summary()).toHaveTextContent(/Ahorro\d+,\d{2} €\d+ % menos · \d+ € al mes si lo repites/)
    expect(screen.getByTestId('threshold')).toHaveTextContent('Contratada: 4,6 kW')
  })

  it('después de publicar planifica mañana', async () => {
    at(AFTER_PUBLISHING)
    renderApp('/planificador')
    await ready()

    expect(screen.getByText('Planificador · mañana, miércoles 7 de octubre')).toBeInTheDocument()
  })

  it('con poca potencia, el coche no cabe y el horario habitual haría saltar el limitador', async () => {
    at(BEFORE_PUBLISHING)
    const { user } = renderApp('/planificador')
    await ready()

    await user.click(screen.getByRole('button', { name: '3,45 kW' }))
    await ready()

    expect(summary()).toHaveTextContent('saltaría el limitador')
    expect(summary()).toHaveTextContent('en 3 de 4 tareas')
    expect(planSection()).toHaveTextContent('No cabesube la potencia o quita tareas')
    expect(screen.getByTestId('threshold')).toHaveTextContent('Contratada: 3,45 kW')
  })

  it('una tarea fija se queda a su hora habitual', async () => {
    at(BEFORE_PUBLISHING)
    const { user } = renderApp('/planificador')
    await ready()

    const pin = screen.getByRole('button', { name: 'Lavadora: flexible, el plan la mueve' })
    await user.click(pin)
    await ready()

    expect(screen.getByRole('button', { name: 'Lavadora: fija a su hora habitual' })).toHaveAttribute('aria-pressed', 'true')
    expect(planSection()).toHaveTextContent(/20–22 h[\d,]+ € · a su hora/)
  })

  it('se pueden añadir, quitar y cambiar la hora habitual de las tareas', async () => {
    at(BEFORE_PUBLISHING)
    const { user } = renderApp('/planificador')
    await ready()

    await user.click(within(screen.getByRole('group', { name: 'Añadir tarea' })).getByRole('button', { name: '+ Secadora' }))
    await ready()
    expect(removeButtons()).toHaveLength(5)

    await user.selectOptions(screen.getByRole('combobox', { name: 'Hora habitual de Horno' }), '13')
    await ready()
    expect(planSection()).toHaveTextContent(/13–14 h[\d,]+ € · a su hora/)

    for (const button of removeButtons()) await user.click(button)
    expect(screen.getByText('Añade una tarea con los botones de arriba.')).toBeInTheDocument()
  })
})

describe('Planificador con errores', () => {
  it('si falla el catálogo, explica el motivo y deja reintentar', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(new Response(JSON.stringify({ error: { code: 'service_unavailable', message: 'x', request_id: 'r7', details: [] } }), { status: 503 }))),
    )
    vi.useFakeTimers({ toFake: ['setTimeout'], shouldAdvanceTime: true })
    renderApp('/planificador')

    expect(await screen.findByRole('alert', {}, { timeout: 5000 })).toHaveTextContent('El servidor está arrancando')
  })
})
