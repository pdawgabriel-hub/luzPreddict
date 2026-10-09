import { describe, expect, it } from 'vitest'
import { ApiError } from '../api/client'
import { errorMessage } from './errors'

describe('mensajes de error', () => {
  it.each([
    [new ApiError(0, 'network', 'x'), 'No se puede conectar con la API. Comprueba tu conexión a internet.'],
    [new ApiError(0, 'timeout', 'x'), 'La API está tardando demasiado en responder.'],
    [new ApiError(503, 'service_unavailable', 'x'), 'El servidor está arrancando. Vuelve a intentarlo en unos segundos.'],
    [new ApiError(500, 'internal_error', 'Error interno del servidor'), 'Algo ha fallado en el servidor.'],
    [new ApiError(404, 'not_found', 'REE aún no ha publicado los precios del 2026-10-11'), 'REE aún no ha publicado los precios del 2026-10-11'],
  ])('%s', (error, message) => {
    expect(errorMessage(error)).toBe(message)
  })
})
