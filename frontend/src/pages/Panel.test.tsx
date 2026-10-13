import { screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { prices as mockPrices } from '../mocks/data'
import { renderApp } from '../test/render'

// Martes 6 de octubre de 2026 en Madrid
const BEFORE_PUBLISHING = new Date('2026-10-06T17:30:00Z') // 19:30: REE aún no ha publicado mañana
const AFTER_PUBLISHING = new Date('2026-10-06T19:30:00Z') // 21:30: ya ha publicado

function at(now: Date) {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(now)
}

const json = (status: number, body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status }))
const notFound = (message: string) => json(404, { error: { code: 'not_found', message, request_id: 'r1', details: [] } })

describe('Panel con datos de ejemplo', () => {
  beforeEach(() => vi.stubEnv('VITE_USE_MOCKS', '1'))

  it('antes de que REE publique: precio de ahora, próximas horas con previsión y mejores horas de mañana', async () => {
    at(BEFORE_PUBLISHING)
    renderApp('/')

    expect(screen.getByText('Cargando los precios…')).toBeInTheDocument()
    expect(await screen.findByRole('heading', { level: 1, name: 'Precio de la luz, martes 6 de octubre' })).toBeInTheDocument()

    const summary = screen.getByRole('region', { name: 'Resumen' })
    expect(summary).toHaveTextContent('Ahora · 19–20 h')
    expect(summary).toHaveTextContent(/Hora (barata|media|cara)/)
    expect(summary).toHaveTextContent('Mañana (previsto)')
    expect(summary).toHaveTextContent(/[▲▼] \d+ % respecto a hoy/)

    const next = within(screen.getByRole('region', { name: 'Próximas horas' })).getAllByRole('listitem')
    expect(next).toHaveLength(8)
    expect(next[0]).toHaveTextContent('Ahora · 19:00')
    expect(next[4]).toHaveTextContent('23:00') // de 19 a 23 h, precio publicado
    expect(next[4]).not.toHaveTextContent('previsión')
    expect(next[5]).toHaveTextContent('00:00') // desde medianoche, previsión de mañana
    expect(next[5]).toHaveTextContent('previsión')

    const best = screen.getByRole('complementary', { name: 'Mejores horas mañana' })
    expect(within(best).getAllByRole('listitem')).toHaveLength(4)
    expect(best).toHaveTextContent(/Evita \d+–\d+ h: se prevén hasta/)
    expect(within(best).getByRole('link', { name: 'Calcular cuánto ahorro' })).toHaveAttribute('href', '/simulador')

    expect(within(screen.getByRole('region', { name: 'Más herramientas' })).getAllByRole('link')).toHaveLength(6)
  })

  it('después de que REE publique, mañana es precio publicado', async () => {
    at(AFTER_PUBLISHING)
    renderApp('/')

    const summary = await screen.findByRole('region', { name: 'Resumen' })
    expect(summary).toHaveTextContent('Mañana (publicado)')
    expect(screen.getByRole('region', { name: 'Próximas horas' })).not.toHaveTextContent('previsión')
    expect(screen.getByRole('complementary', { name: 'Mejores horas mañana' })).toHaveTextContent('llega a hasta')
  })

  it('el gráfico empieza en la hora actual y se puede elegir otra con el ratón o las flechas', async () => {
    at(BEFORE_PUBLISHING)
    const { user } = renderApp('/')

    await screen.findByRole('region', { name: 'Resumen' })
    const day = screen.getByRole('group', { name: 'Día' })
    expect(within(day).getByRole('button', { name: 'Hoy · 6 oct' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: /^19–20 h: / })).toHaveAttribute('aria-pressed', 'true')

    await user.click(screen.getByRole('button', { name: /^3–4 h: / }))
    expect(screen.getByRole('button', { name: /^3–4 h: / })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByText('3–4 h', { selector: 'span' })).toBeInTheDocument()

    await user.keyboard('{ArrowRight}')
    expect(screen.getByRole('button', { name: /^4–5 h: / })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: /^4–5 h: / })).toHaveFocus()
  })

  it('la pestaña Mañana enseña la previsión con su aviso, y Comparar las dos líneas', async () => {
    at(BEFORE_PUBLISHING)
    const { user } = renderApp('/')

    await user.click(await screen.findByRole('button', { name: 'Mañana · 7 oct' }))
    expect(screen.getByRole('img', { name: /^Previsión del precio por horas del miércoles 7 de octubre/ })).toBeInTheDocument()
    expect(screen.getByText(/Previsión orientativa/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Comparar' }))
    expect(screen.getByText(/^Mañana sale más barato en \d+ de 24 horas\.$/)).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Precio de hoy frente a la previsión de mañana, en €/kWh' })).toBeInTheDocument()
  })
})

describe('Panel sin datos de mañana o con errores', () => {
  afterEach(() => vi.useRealTimers())

  it('si no hay precio ni previsión de mañana, lo explica y usa hoy', async () => {
    at(BEFORE_PUBLISHING)
    const today = mockPrices('2026-10-06', '2026-10-06', '2026-10-06')
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        if (url === '/v1/prices') return json(200, today)
        if (url.startsWith('/v1/prices?date=')) return notFound('REE aún no ha publicado los precios del 2026-10-07')
        if (url.startsWith('/v1/forecast')) return notFound('No hay previsión para el 2026-10-07')
        return json(200, { status: 'ok', warnings: [], prices: {}, forecast: null, model: null })
      }),
    )
    renderApp('/')

    const summary = await screen.findByRole('region', { name: 'Resumen' })
    expect(summary).toHaveTextContent('REE publica los precios hacia las 20:15')
    expect(screen.getByRole('button', { name: 'Mañana' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Comparar' })).toBeDisabled()
    expect(screen.getByRole('complementary', { name: 'Mejores horas hoy' })).toBeInTheDocument()
  })

  it('si fallan los precios de hoy, explica el motivo y deja reintentar', async () => {
    at(BEFORE_PUBLISHING)
    vi.stubGlobal('fetch', vi.fn(() => notFound('No hay precios del 2026-10-06')))
    const { user } = renderApp('/')

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('No hay precios del 2026-10-06')
    expect(alert).toHaveTextContent('Id de la petición: r1')

    vi.stubEnv('VITE_USE_MOCKS', '1')
    await user.click(screen.getByRole('button', { name: 'Reintentar' }))
    expect(await screen.findByRole('region', { name: 'Resumen' })).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
