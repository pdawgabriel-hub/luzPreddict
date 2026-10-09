import { Link } from 'react-router'
import { PageHeader } from '../components/PageHeader'

export default function NotFound() {
  return (
    <>
      <PageHeader eyebrow="Error 404" title="Página no encontrada" />
      <p className="card">
        Esta dirección no existe. <Link to="/">Vuelve al panel</Link> para ver el precio de hoy.
      </p>
    </>
  )
}
