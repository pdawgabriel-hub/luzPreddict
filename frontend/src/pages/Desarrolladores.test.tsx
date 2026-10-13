import { screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderApp } from '../test/render'

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-10-06T19:30:00Z')) // 21:30 en Madrid: mañana ya publicado
})

const consoleSection = () => screen.getByRole('region', { name: /^\/(v1|health)/ })

async function open(path = '/desarrolladores') {
  const result = renderApp(path)
  await screen.findByRole('navigation', { name: 'Endpoints' })
  return result
}

describe('API pública', () => {
  beforeEach(() => vi.stubEnv('VITE_USE_MOCKS', '1'))

  it('lista los endpoints públicos con su resumen', async () => {
    await open()

    const nav = screen.getByRole('navigation', { name: 'Endpoints' })
    expect(within(nav).getAllByRole('button').map((b) => b.textContent)).toEqual([
      'GET/healthEstado del servicio',
      'GET/v1/pricesPrecios por día o rango',
      'GET/v1/forecastPrevisión de un día',
      'GET/v1/best-hoursMejores horas para consumir',
      'GET/v1/historyResumen diario',
      'GET/v1/marketMix de generación',
    ])
    expect(screen.getByText('Sin clave de API')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '/docs' })).toHaveAttribute('href', '/docs')
  })

  it('arma la petición con los parámetros y enseña la respuesta', async () => {
    const { user } = await open()

    await user.click(screen.getByRole('button', { name: /^GET\/v1\/best-hours/ }))
    const section = consoleSection()
    expect(within(section).getByRole('spinbutton', { name: 'hours' })).toHaveValue(2)
    expect(within(section).getByLabelText('date')).toHaveValue('2026-10-06')
    expect(within(section).getByText('Duración del consumo, en horas (1–24) Por defecto, 1.')).toBeInTheDocument()
    expect(section).toHaveTextContent(`curl -s "${window.location.origin}/v1/best-hours?hours=2&date=2026-10-06"`)

    await user.click(within(section).getByRole('button', { name: 'Enviar' }))
    expect(await within(section).findByText(/^200 OK/)).toBeInTheDocument()
    const body = within(section).getByLabelText('Cuerpo de la respuesta')
    expect(JSON.parse(body.textContent ?? '')).toMatchObject({ date: '2026-10-06', hours: 2, unit: '€/MWh' })
  })

  it('los errores también se ven, con su formato común', async () => {
    const { user } = await open()

    await user.click(screen.getByRole('button', { name: /^GET\/v1\/prices/ }))
    const section = consoleSection()
    const date = within(section).getByLabelText('date')
    await user.clear(date)
    await user.type(date, '2026-10-09') // pasado mañana: aún no hay precios
    await user.click(within(section).getByRole('button', { name: 'Enviar' }))

    expect(await within(section).findByText(/^404 Not Found/)).toBeInTheDocument()
    expect(JSON.parse(within(section).getByLabelText('Cuerpo de la respuesta').textContent ?? '').error.code).toBe('not_found')
  })

  it('copia el curl', async () => {
    const { user } = await open()

    await user.click(within(consoleSection()).getByRole('button', { name: 'Copiar curl' }))
    expect(await navigator.clipboard.readText()).toBe(`curl -s "${window.location.origin}/health"`)
  })
})

describe('API pública contra el servidor', () => {
  it('enseña el estado y las cabeceras reales de la respuesta', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          new Response(JSON.stringify({ status: 'ok' }), {
            status: 200,
            headers: { 'content-type': 'application/json', 'cache-control': 'public, max-age=60, s-maxage=60', 'x-request-id': 'abc123', 'x-otra': 'no' },
          }),
        ),
      ),
    )
    const { user } = await open()

    await user.click(within(consoleSection()).getByRole('button', { name: 'Enviar' }))

    const headers = await within(consoleSection()).findByLabelText('Cabeceras de la respuesta')
    expect(headers.textContent).toBe('content-type: application/json\ncache-control: public, max-age=60, s-maxage=60\nx-request-id: abc123')
  })
})
