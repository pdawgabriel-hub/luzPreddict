import { Route, Routes } from 'react-router'
import { Layout } from './components/Layout'
import Alertas from './pages/Alertas'
import Factura from './pages/Factura'
import Historico from './pages/Historico'
import Mercado from './pages/Mercado'
import NotFound from './pages/NotFound'
import Panel from './pages/Panel'
import Placeholder from './pages/Placeholder'
import Planificador from './pages/Planificador'
import Simulador from './pages/Simulador'
import { ROUTES } from './routes'

// Páginas ya hechas; el resto aún muestra el aviso de "en construcción"
const PAGES = new Set(['/', '/historico', '/mercado', '/simulador', '/planificador', '/factura', '/alertas'])

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
        {ROUTES.filter((route) => !PAGES.has(route.path)).map((route) => (
          <Route key={route.path} path={route.path} element={<Placeholder title={route.title} />} />
        ))}
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}
