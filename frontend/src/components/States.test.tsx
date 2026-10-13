import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/client'
import { ErrorState, LoadingState } from './States'

describe('estado de carga', () => {
  it('se anuncia a los lectores de pantalla, con texto por defecto o propio', () => {
    const { rerender } = render(<LoadingState />)
    expect(screen.getByRole('status')).toHaveTextContent('Cargando datos…')
    expect(screen.getByRole('status')).toHaveAttribute('aria-live', 'polite')

    rerender(<LoadingState label="Cargando los precios…" />)
    expect(screen.getByRole('status')).toHaveTextContent('Cargando los precios…')
  })
})

describe('estado de error', () => {
  it('explica el motivo, deja reintentar y da el id de la petición', async () => {
    const onRetry = vi.fn()
    render(<ErrorState error={new ApiError(503, 'service_unavailable', 'x', 'abc123')} onRetry={onRetry} />)

    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent('No se han podido cargar los datos')
    expect(alert).toHaveTextContent('El servidor está arrancando. Vuelve a intentarlo en unos segundos.')
    expect(alert).toHaveTextContent('Id de la petición: abc123')

    await userEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it('sin reintento ni id, no muestra el botón ni el id; el título se puede cambiar', () => {
    render(<ErrorState title="No se ha podido calcular" error={new ApiError(0, 'network', 'x')} />)

    expect(screen.getByRole('alert')).toHaveTextContent('No se ha podido calcular')
    expect(screen.getByRole('alert')).toHaveTextContent('No se puede conectar con la API')
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    expect(screen.queryByText(/Id de la petición/)).not.toBeInTheDocument()
  })
})
