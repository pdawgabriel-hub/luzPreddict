import type { ApiError } from '../api/client'

/** Qué ha pasado, en palabras de quien usa la web. */
export function errorMessage(error: ApiError): string {
  switch (error.code) {
    case 'network':
      return 'No se puede conectar con la API. Comprueba tu conexión a internet.'
    case 'timeout':
      return 'La API está tardando demasiado en responder.'
    case 'service_unavailable':
      return 'El servidor está arrancando. Vuelve a intentarlo en unos segundos.'
  }
  if (error.status >= 500) return 'Algo ha fallado en el servidor.'
  return error.message // los mensajes de la API ya están en castellano ("REE aún no ha publicado…")
}
