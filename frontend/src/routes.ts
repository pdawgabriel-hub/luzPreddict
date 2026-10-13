// Páginas de la web, en el orden de la navegación.
// La de la API no está en /api: esa ruta es de FastAPI (proxy de Vite y Vercel).

export type PageRoute = {
  path: string
  label: string // texto del menú
  title: string // título de la pestaña
}

export const ROUTES: PageRoute[] = [
  { path: '/', label: 'Panel', title: 'Precio de la luz hoy y mañana' },
  { path: '/historico', label: 'Histórico', title: 'Histórico de precios' },
  { path: '/mercado', label: 'Mercado', title: '¿De dónde viene la luz?' },
  { path: '/simulador', label: 'Simulador', title: '¿Cuándo me sale más barato?' },
  { path: '/planificador', label: 'Planificador', title: 'Organiza tu día' },
  { path: '/factura', label: 'Factura', title: 'PVPC frente a precio fijo' },
  { path: '/alertas', label: 'Alertas', title: 'Alertas de precio' },
  { path: '/modelo', label: 'Modelo', title: 'Cómo funciona la previsión' },
  { path: '/desarrolladores', label: 'API', title: 'API pública' },
]

export const SITE_NAME = 'luzPreddict'

export function documentTitle(title: string): string {
  return `${title} · ${SITE_NAME}`
}
