import { lazy, Suspense } from 'react'
import { Route, Routes } from 'react-router'
import { Layout } from './components/Layout'
import { LoadingState } from './components/States'
import Alertas from './pages/Alertas'
import Factura from './pages/Factura'
import Historico from './pages/Historico'
import Mercado from './pages/Mercado'
import Modelo from './pages/Modelo'
import NotFound from './pages/NotFound'
import Panel from './pages/Panel'
import Planificador from './pages/Planificador'
import Simulador from './pages/Simulador'

// Se carga aparte: lleva el esquema OpenAPI completo, que solo hace falta en esta página
const Desarrolladores = lazy(() => import('./pages/Desarrolladores'))

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Panel />} />
        <Route path="/historico" element={<Historico />} />
        <Route path="/mercado" element={<Mercado />} />
        <Route path="/simulador" element={<Simulador />} />
        <Route path="/planificador" element={<Planificador />} />
        <Route path="/factura" element={<Factura />} />
        <Route path="/alertas" element={<Alertas />} />
        <Route path="/modelo" element={<Modelo />} />
        <Route
          path="/desarrolladores"
          element={
            <Suspense fallback={<LoadingState label="Cargando la documentación de la API…" />}>
              <Desarrolladores />
            </Suspense>
          }
        />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}
