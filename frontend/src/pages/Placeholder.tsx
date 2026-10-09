import { PageHeader } from '../components/PageHeader'

// Página aún sin contenido: cada sección llega en su commit de la Fase 7.
export default function Placeholder({ title }: { title: string }) {
  return (
    <>
      <PageHeader title={title} />
      <p className="card muted">Esta sección está en construcción.</p>
    </>
  )
}
