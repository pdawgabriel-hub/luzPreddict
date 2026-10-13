import { screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ROUTES } from '../routes'
import { renderApp } from '../test/render'

beforeEach(() => vi.stubEnv('VITE_USE_MOCKS', '1')) // el panel llama a la API

const nav = () => screen.getByRole('navigation', { name: 'Secciones' })

describe('navegación', () => {
  it('enlaza las 9 secciones del prototipo', () => {
    renderApp()

    const links = within(nav()).getAllByRole('link')
    expect(links.map((a) => a.textContent)).toEqual([
      'Panel',
      'Histórico',
      'Mercado',
      'Simulador',
      'Planificador',
      'Factura',
      'Alertas',
      'Modelo',
      'API',
    ])
    expect(links.map((a) => a.getAttribute('href'))).toEqual(ROUTES.map((r) => r.path))
  })

  it('la página de la API no está en /api, que es la ruta de FastAPI', () => {
    expect(ROUTES.every((route) => !/^\/(api|v1|health)(\/|$)/.test(route.path))).toBe(true)
  })

  it('marca la página actual, y el panel solo en la portada', () => {
    renderApp('/mercado')

    expect(within(nav()).getByRole('link', { name: 'Mercado' })).toHaveAttribute('aria-current', 'page')
    expect(within(nav()).getByRole('link', { name: 'Panel' })).not.toHaveAttribute('aria-current')
  })

  it.each(ROUTES)('$path tiene su título de página y de pestaña', async ({ path, title }) => {
    renderApp(path)

    expect(screen.getByRole('heading', { level: 1, name: title })).toBeInTheDocument()
    expect(document.title).toBe(`${title} · luzPreddict`)
  })

  it('una dirección desconocida muestra la página 404 con la navegación', async () => {
    const { user } = renderApp('/no-existe')

    expect(screen.getByRole('heading', { level: 1, name: 'Página no encontrada' })).toBeInTheDocument()
    await user.click(screen.getByRole('link', { name: 'Vuelve al panel' }))
    // Al cargar los precios, el título del panel pasa a llevar la fecha
    expect(await screen.findByRole('heading', { level: 1, name: /^Precio de la luz/ })).toBeInTheDocument()
  })

  it('el logo lleva al panel', async () => {
    const { user } = renderApp('/factura')

    await user.click(screen.getByRole('link', { name: 'luzPreddict, ir al panel' }))
    expect(within(nav()).getByRole('link', { name: 'Panel' })).toHaveAttribute('aria-current', 'page')
  })
})

describe('menú del móvil', () => {
  const menuButton = () => screen.getByRole('button', { name: 'Menú' })

  it('se abre y se cierra con el botón', async () => {
    const { user } = renderApp()

    expect(menuButton()).toHaveAttribute('aria-expanded', 'false')
    expect(menuButton()).toHaveAttribute('aria-controls', nav().id)
    await user.click(menuButton())
    expect(menuButton()).toHaveAttribute('aria-expanded', 'true')
    expect(nav()).toHaveAttribute('data-open', 'true')
    await user.click(menuButton())
    expect(menuButton()).toHaveAttribute('aria-expanded', 'false')
  })

  it('se cierra con Escape', async () => {
    const { user } = renderApp()

    await user.click(menuButton())
    await user.keyboard('{Escape}')
    expect(menuButton()).toHaveAttribute('aria-expanded', 'false')
  })

  it('se cierra al ir a otra página', async () => {
    const { user } = renderApp()

    await user.click(menuButton())
    await user.click(within(nav()).getByRole('link', { name: 'Simulador' }))
    expect(menuButton()).toHaveAttribute('aria-expanded', 'false')
    expect(screen.getByRole('heading', { level: 1, name: '¿Cuándo me sale más barato?' })).toBeInTheDocument()
  })
})

describe('estructura y pie', () => {
  it('permite saltar la navegación con el teclado', () => {
    renderApp()

    const skip = screen.getByRole('link', { name: 'Saltar al contenido' })
    expect(skip).toHaveAttribute('href', '#contenido')
    expect(screen.getByRole('main')).toHaveAttribute('id', 'contenido')
  })

  it('el pie cita a REE, avisa de que la previsión es orientativa y enlaza la API', () => {
    renderApp()

    const footer = screen.getByRole('contentinfo')
    expect(within(footer).getByRole('link', { name: /Red Eléctrica \(REE\)/ })).toHaveAttribute(
      'href',
      'https://www.ree.es/es/apidatos',
    )
    expect(footer).toHaveTextContent('La previsión es orientativa')
    expect(within(footer).getByRole('link', { name: 'API pública' })).toHaveAttribute('href', '/desarrolladores')
    expect(within(footer).getByRole('link', { name: 'Código en GitHub' })).toHaveAttribute(
      'href',
      'https://github.com/pdawgabriel-hub/luzPreddict',
    )
  })
})
