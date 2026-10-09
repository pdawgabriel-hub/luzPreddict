import { Route, Routes } from 'react-router'
import { Layout } from './components/Layout'
import NotFound from './pages/NotFound'
import Panel from './pages/Panel'
import Placeholder from './pages/Placeholder'
import { ROUTES } from './routes'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Panel />} />
        {ROUTES.filter((route) => route.path !== '/').map((route) => (
          <Route key={route.path} path={route.path} element={<Placeholder title={route.title} />} />
        ))}
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}
