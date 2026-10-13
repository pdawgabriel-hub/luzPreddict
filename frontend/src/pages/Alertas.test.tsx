import { fireEvent, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { STORAGE_KEY } from '../lib/localAlerts'
import { renderApp } from '../test/render'

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-10-06T16:00:00Z')) // 18:00 en Madrid: mañana aún es previsión
  vi.stubEnv('VITE_USE_MOCKS', '1')
})

const myAlerts = () => screen.getByRole('region', { name: 'Mis alertas' })
const saved = () => JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '[]')

describe('Alertas', () => {
  it('previsualiza la alerta con la previsión de mañana y su historial', async () => {
    renderApp('/alertas')

    const form = await screen.findByRole('region', { name: 'Nueva alerta' })
    expect(form).toHaveTextContent(/Con la previsión de mañana: saltaría en (ninguna hora|\d+ horas? \()/)
    expect(form).toHaveTextContent(/Últimos 30 días: habría saltado \d+ días? \(\d+ horas?\)\./)

    fireEvent.change(screen.getByRole('slider', { name: 'Umbral' }), { target: { value: '400' } })
    expect(screen.getByText('0,400 €/kWh')).toBeInTheDocument()
    expect(form).toHaveTextContent('saltaría en 24 horas') // todas por debajo de 0,40 €/kWh
  })

  it('guarda, pausa y borra alertas en el navegador', async () => {
    const { user } = renderApp('/alertas')
    await screen.findByRole('region', { name: 'Nueva alerta' })
    expect(myAlerts()).toHaveTextContent('No tienes alertas')

    await user.click(screen.getByRole('button', { name: 'Suba de' }))
    fireEvent.change(screen.getByRole('slider', { name: 'Umbral' }), { target: { value: '150' } })
    await user.click(screen.getByRole('button', { name: 'Guardar alerta' }))

    const item = within(myAlerts()).getByRole('listitem')
    expect(item).toHaveTextContent('Cuando suba de 0,150 €/kWh')
    expect(item).toHaveTextContent(/(Salta mañana: \d+ horas?|Mañana no salta)/)
    expect(saved()).toEqual([expect.objectContaining({ direction: 'above', threshold: 150, active: true })])
    expect(screen.getByRole('button', { name: 'Guardar alerta' })).toBeDisabled() // ya hay una igual
    expect(screen.getByText('Ya tienes una alerta igual.')).toBeInTheDocument()

    await user.click(within(item).getByRole('button', { name: 'Activa' }))
    expect(within(item).getByRole('button', { name: 'En pausa' })).toHaveAttribute('aria-pressed', 'false')
    expect(saved()[0].active).toBe(false)
    expect(myAlerts()).toHaveTextContent('0 activas')

    await user.click(within(item).getByRole('button', { name: 'Borrar la alerta: cuando suba de 0,150 €/kwh' }))
    expect(myAlerts()).toHaveTextContent('No tienes alertas')
    expect(saved()).toEqual([])
  })

  it('recupera las alertas guardadas al volver', async () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify([{ id: 'x', direction: 'below', threshold: 80, active: true }]))
    renderApp('/alertas')

    expect(await within(await screen.findByRole('region', { name: 'Mis alertas' })).findByText('Cuando baje de 0,080 €/kWh')).toBeInTheDocument()
  })

  it('avisa si el navegador no deja guardar', async () => {
    const { user } = renderApp('/alertas')
    await screen.findByRole('region', { name: 'Nueva alerta' })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('QuotaExceededError')
    })

    await user.click(screen.getByRole('button', { name: 'Guardar alerta' }))

    expect(screen.getByRole('alert')).toHaveTextContent('Tu navegador no deja guardar datos')
    expect(within(myAlerts()).getAllByRole('listitem')).toHaveLength(1) // sigue en la página
  })

  it('explica cómo suscribirse a ntfy y cómo llegaría el resumen', async () => {
    const { user } = renderApp('/alertas') // userEvent trae su propio portapapeles de pruebas

    const ntfy = await screen.findByRole('region', { name: 'Resumen diario en el móvil' })
    expect(ntfy).toHaveTextContent('Suscríbete al tema luzpreddict')
    expect(within(ntfy).getByRole('link', { name: 'ntfy.sh/luzpreddict' })).toHaveAttribute('href', 'https://ntfy.sh/luzpreddict')

    const notification = within(ntfy).getByRole('article', { name: 'Ejemplo de notificación' })
    expect(notification).toHaveTextContent(/Luz el miércoles 7 de octubre: media 0,\d{3} €\/kWh/)
    expect(notification).toHaveTextContent('Previsión de luzPreddict (LightGBM).')
    expect(notification).toHaveTextContent(/Un \d+ % más (cara|barata) que el día anterior\.|Similar al día anterior\./)

    await user.click(within(ntfy).getByRole('button', { name: 'Copiar' }))
    expect(await navigator.clipboard.readText()).toBe('luzpreddict')
    expect(within(ntfy).getByRole('button', { name: 'Copiado' })).toBeInTheDocument()
  })
})
