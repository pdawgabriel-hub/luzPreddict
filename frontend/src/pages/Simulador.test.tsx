import { screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderApp } from '../test/render'

const BEFORE_PUBLISHING = new Date('2026-10-06T16:00:00Z') // 18:00 en Madrid
const AFTER_PUBLISHING = new Date('2026-10-06T19:30:00Z') // 21:30 en Madrid

function at(now: Date) {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(now)
}

const result = () => screen.getByRole('region', { name: 'Resultado' })
const table = () => screen.getByRole('table', { name: 'Todos tus aparatos' })

async function ready() {
  await screen.findByRole('table', { name: 'Todos tus aparatos' })
  await vi.waitFor(() => expect(result()).toHaveAttribute('aria-busy', 'false'))
}

describe('Simulador', () => {
  beforeEach(() => vi.stubEnv('VITE_USE_MOCKS', '1'))

  it('antes de que REE publique simula hoy y explica cuándo estará mañana', async () => {
    at(BEFORE_PUBLISHING)
    renderApp('/simulador')
    await ready()

    expect(screen.getByRole('button', { name: 'Hoy · 6 oct' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'Mañana' })).toBeDisabled()
    expect(screen.getByText(/cuando REE publique sus precios, hacia las 20:15/)).toBeInTheDocument()

    expect(result()).toHaveTextContent('Tu elección · 20–22 h')
    expect(result()).toHaveTextContent(/Mejor hora · \d+–\d+ h/)
    expect(result()).toHaveTextContent(/Ahorro estimado al año\d+ €/)
    expect(screen.getByRole('heading', { name: 'Precios del martes 6 de octubre, lavadora' })).toBeInTheDocument()
  })

  it('después de publicar, simula mañana por defecto', async () => {
    at(AFTER_PUBLISHING)
    renderApp('/simulador')
    await ready()

    expect(screen.getByRole('button', { name: 'Mañana · 7 oct' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('heading', { name: 'Precios del miércoles 7 de octubre, lavadora' })).toBeInTheDocument()
  })

  it('compara los 5 aparatos y marca el elegido', async () => {
    at(BEFORE_PUBLISHING)
    renderApp('/simulador')
    await ready()

    const rows = within(table()).getAllByRole('row')
    expect(rows.slice(1, 6).map((r) => within(r).getByRole('rowheader').textContent)).toEqual([
      'Lavadora',
      'Lavavajillas',
      'Secadora',
      'Horno',
      'Coche eléctrico (cargador de 3,7 kW)',
    ])
    expect(rows[1]).toHaveAttribute('data-selected', 'true')
    expect(within(table()).getByRole('row', { name: /^Total si los mueves todos \d+ €$/ })).toBeInTheDocument()
  })

  it('cambiar la hora, pulsar una barra o "Usar la mejor hora" recalcula', async () => {
    at(BEFORE_PUBLISHING)
    const { user } = renderApp('/simulador')
    await ready()

    await user.click(screen.getByRole('button', { name: 'Hora de inicio: una hora después' }))
    await ready()
    expect(result()).toHaveTextContent('Tu elección · 21–23 h')

    await user.click(screen.getByRole('button', { name: /^Empezar a las 08:00: / }))
    await ready()
    expect(result()).toHaveTextContent('Tu elección · 8–10 h')

    await user.click(screen.getByRole('button', { name: 'Usar la mejor hora' }))
    await ready()
    expect(result()).toHaveTextContent('Ya estás en la mejor hora')
    expect(screen.queryByRole('button', { name: 'Usar la mejor hora' })).not.toBeInTheDocument()
  })

  it('avisa si la franja es más corta que el programa', async () => {
    at(BEFORE_PUBLISHING)
    const { user } = renderApp('/simulador')
    await ready()

    await user.click(screen.getByRole('button', { name: /^Coche eléctrico/ }))
    for (let i = 0; i < 20; i++) await user.click(screen.getByRole('button', { name: 'Disponible desde: una hora después' }))
    await ready()

    expect(screen.getByRole('alert')).toHaveTextContent('La franja es más corta que el programa (6 h)')
    expect(result()).toHaveTextContent('Mejor hora · sin hueco en tu franja')
    expect(within(table()).getByRole('row', { name: /^Coche eléctrico.*No cabe en tu franja/ })).toBeInTheDocument()
  }, 15_000) // 20 pulsaciones: con cobertura y la máquina cargada puede pasar de los 5 s por defecto

  it('simula un aparato propio con su potencia y duración', async () => {
    at(BEFORE_PUBLISHING)
    const { user } = renderApp('/simulador')
    await ready()

    await user.click(screen.getByRole('button', { name: /^Otro aparato/ }))
    const power = screen.getByRole('textbox', { name: 'Potencia (kW)' })
    await user.clear(power)
    expect(screen.getByText('Entre 0,1 y 15 kW')).toBeInTheDocument() // vacío: no vale
    await user.type(power, '3')
    expect(power).toHaveAttribute('aria-invalid', 'false')
    await user.click(screen.getByRole('button', { name: 'Duración (h): más' }))
    await ready()

    expect(result()).toHaveTextContent('9,0 kWh') // 3 kW durante 3 h
    expect(result()).toHaveTextContent('Tu elección · 20–23 h')
    expect(screen.getByRole('heading', { name: 'Precios del martes 6 de octubre, mi aparato' })).toBeInTheDocument()

    await user.clear(power)
    await user.type(power, '1,5') // coma decimal, como se escribe en España
    await ready()
    expect(result()).toHaveTextContent('4,5 kWh')
  })
})

describe('Simulador con errores', () => {
  it('si falla el catálogo, explica el motivo y deja reintentar', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(new Response(JSON.stringify({ error: { code: 'internal_error', message: 'x', request_id: 'r5', details: [] } }), { status: 500 }))),
    )
    renderApp('/simulador')

    expect(await screen.findByRole('alert')).toHaveTextContent('Algo ha fallado en el servidor.')
    expect(screen.getByRole('button', { name: 'Reintentar' })).toBeInTheDocument()
  })
})
