import { fireEvent, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderApp } from '../test/render'

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-10-06T10:00:00Z')) // martes 6 de octubre
})

const result = () => screen.getByRole('region', { name: 'Resultado' })
const verdict = () => within(result()).getByRole('status')

async function ready() {
  await screen.findByRole('region', { name: 'Resultado' })
  await vi.waitFor(() => expect(result()).toHaveAttribute('aria-busy', 'false'))
  await within(result()).findByRole('status')
}

describe('Factura', () => {
  beforeEach(() => vi.stubEnv('VITE_USE_MOCKS', '1'))

  it('compara los últimos 30 días con PVPC y con un precio fijo', async () => {
    renderApp('/factura')
    await ready()

    expect(screen.getByRole('button', { name: /^Hogar típico/ })).toHaveAttribute('aria-pressed', 'true')
    expect(verdict()).toHaveTextContent(/^En los últimos 30 díasTe compensa el (PVPC|precio fijo)Con el PVPC habrías pagado [\d,]+ € (menos|más) que con tu precio fijo de 0,150 €\/kWh\.$/)

    const options = within(result()).getAllByRole('term').map((t) => t.textContent)
    expect(options[0]).toMatch(/^PVPC[\d,]+ €\/kWh efectivo$/)
    expect(options[2]).toBe('Tu precio fijo0,150 €/kWh')
    expect(result()).toHaveTextContent(/Precio de equilibrio0,\d{3} €\/kWh/)
    expect(result()).toHaveTextContent(/Días en que el fijo salió mejor\d+ de 30/)
    expect(screen.getByTestId('threshold')).toHaveTextContent(/^Tu fijo: [\d,]+ €\/día$/)

    const periods = within(screen.getByRole('table', { name: 'Coste por tramos de la tarifa 2.0TD' })).getAllByRole('rowheader')
    expect(periods.map((p) => p.textContent)).toEqual(['Punta', 'Llano', 'Valle'])
    expect(result()).toHaveTextContent('Precios PVPC reales del 7 sept al 6 oct')
  })

  it('con un fijo muy barato gana el fijo; con uno muy caro, el PVPC', async () => {
    const { user } = renderApp('/factura')
    await ready()

    const fixed = screen.getByRole('textbox', { name: 'Precio fijo de tu contrato (€/kWh)' })
    await user.clear(fixed)
    await user.type(fixed, '0,02')
    await ready()
    expect(verdict()).toHaveTextContent('Te compensa el precio fijo')

    await user.clear(fixed)
    await user.type(fixed, '0,5')
    await ready()
    expect(verdict()).toHaveTextContent('Te compensa el PVPC')
  })

  it('mover consumo a horas baratas abarata el PVPC', async () => {
    renderApp('/factura')
    await ready()

    const before = within(result()).getAllByRole('definition').filter((d) => d.classList.contains('num'))[1].textContent
    const slider = screen.getByRole('slider', { name: 'Consumo que puedo mover a horas baratas' })
    fireEvent.change(slider, { target: { value: '20' } }) // jsdom no mueve un range con el teclado
    await ready()

    expect(screen.getByText('20 %', { selector: 'output' })).toBeInTheDocument()
    expect(verdict()).toHaveTextContent('Con el PVPC y moviendo consumo')
    const after = within(result()).getAllByRole('definition').filter((d) => d.classList.contains('num'))[1].textContent
    const euros = (text: string | null) => Number(text?.replace(/[^\d,]/g, '').replace(',', '.'))
    expect(euros(after)).toBeLessThan(euros(before))
  })

  it('el consumo y el perfil cambian el cálculo', async () => {
    const { user } = renderApp('/factura')
    await ready()

    await user.click(screen.getByRole('button', { name: 'Consumo al mes: más consumo' }))
    expect(screen.getByText('260 kWh')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /^Constante/ }))
    await ready()

    const periods = within(screen.getByRole('table', { name: 'Coste por tramos de la tarifa 2.0TD' })).getAllByRole('row').slice(1)
    const kwh = periods.map((r) => Number(r.textContent?.match(/(\d+) kWh/)?.[1]))
    expect(kwh.reduce((a, b) => a + b, 0)).toBeGreaterThanOrEqual(259) // los 260 kWh repartidos (con redondeo)
  })
})

describe('Factura con errores', () => {
  it('si falla el catálogo, explica el motivo y deja reintentar', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(new Response(JSON.stringify({ error: { code: 'not_found', message: 'No encontrado', request_id: 'r8', details: [] } }), { status: 404 }))),
    )
    renderApp('/factura')

    expect(await screen.findByRole('alert')).toHaveTextContent('No encontrado')
  })
})
