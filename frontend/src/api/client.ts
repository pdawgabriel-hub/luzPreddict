// Única puerta de la web a la API. Con VITE_USE_MOCKS=1 responde con datos de
// ejemplo (src/mocks) en lugar de llamar a la API, para trabajar sin backend.

import type { ErrorResponse, FieldError } from './types'

export type Query = Record<string, string | number | boolean | undefined | null>

/** Error de la API con el formato común: código, mensaje en castellano e id de la petición. */
export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly requestId: string | null
  readonly details: FieldError[]

  constructor(status: number, code: string, message: string, requestId: string | null = null, details: FieldError[] = []) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.requestId = requestId
    this.details = details
  }
}

export function usingMocks(): boolean {
  return import.meta.env.VITE_USE_MOCKS === '1'
}

/** Ruta con su query string, sin los parámetros vacíos. */
export function withQuery(path: string, query: Query = {}): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== '') params.set(key, String(value))
  }
  const search = params.toString()
  return search ? `${path}?${search}` : path
}

async function toApiError(response: Response): Promise<ApiError> {
  try {
    const { error } = (await response.json()) as ErrorResponse
    return new ApiError(response.status, error.code, error.message, error.request_id ?? null, error.details ?? [])
  } catch {
    // Respuesta sin el formato común (p. ej. un proxy caído)
    return new ApiError(response.status, 'http_error', `La API respondió ${response.status}`)
  }
}

/** Tiempo máximo de cada intento. */
export const TIMEOUT_MS = 10_000
/** Espera antes de cada reintento: tres intentos en total. */
export const RETRY_DELAYS_MS = [500, 1_500]
/** Fallos pasajeros: sin red, tiempo agotado, proxy caído o la base de datos despertando. */
const RETRYABLE = new Set(['network', 'timeout'])
const RETRYABLE_STATUS = new Set([502, 503, 504])

function isRetryable(error: unknown): boolean {
  return error instanceof ApiError && (RETRYABLE.has(error.code) || RETRYABLE_STATUS.has(error.status))
}

function wait(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, ms)
    signal?.addEventListener('abort', () => {
      clearTimeout(timer)
      reject(signal.reason)
    })
  })
}

async function attempt<T>(method: Method, url: string, body: unknown, signal?: AbortSignal): Promise<T> {
  // Comprobación en línea (no con usingMocks): en el build de producción la condición es
  // constante y el minificador elimina la rama, con lo que los datos de ejemplo no se incluyen
  if (import.meta.env.VITE_USE_MOCKS === '1') {
    const { mockRequest } = await import('../mocks')
    return mockRequest(method, url, body, { signal }) as Promise<T>
  }

  const timeout = AbortSignal.timeout(TIMEOUT_MS)
  let response: Response
  try {
    response = await fetch(url, {
      method,
      signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch (error) {
    if (signal?.aborted) throw error // la ha cancelado quien la pidió (p. ej. al cambiar de página)
    if (timeout.aborted) throw new ApiError(0, 'timeout', 'La API tarda demasiado en responder')
    throw new ApiError(0, 'network', 'No se puede conectar con la API')
  }
  if (!response.ok) throw await toApiError(response)
  return (await response.json()) as T
}

type Method = 'GET' | 'POST'

async function request<T>(method: Method, url: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  // Solo se reintentan las consultas: repetir un GET no tiene efectos
  const delays = method === 'GET' ? RETRY_DELAYS_MS : []
  for (let retry = 0; ; retry++) {
    try {
      return await attempt<T>(method, url, body, signal)
    } catch (error) {
      if (retry >= delays.length || !isRetryable(error) || signal?.aborted) throw error
      await wait(delays[retry], signal)
    }
  }
}

export function getJson<T>(path: string, query?: Query, signal?: AbortSignal): Promise<T> {
  return request<T>('GET', withQuery(path, query), undefined, signal)
}

export function postJson<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  return request<T>('POST', path, body, signal)
}

export type RawResponse = { status: number; headers: Record<string, string>; body: unknown; ms: number }

/** Cabeceras que interesa enseñar en la consola de la API. */
export const SHOWN_HEADERS = ['content-type', 'cache-control', 'x-request-id', 'retry-after']

/**
 * Petición GET tal cual, sin reintentos ni conversión a ApiError: para la consola de la
 * página de desarrolladores, que enseña el estado, las cabeceras y el cuerpo de la respuesta.
 */
export async function inspect(path: string, signal?: AbortSignal): Promise<RawResponse> {
  const started = performance.now()
  if (import.meta.env.VITE_USE_MOCKS === '1') {
    const { mockRequest } = await import('../mocks')
    const headers = { 'content-type': 'application/json', 'x-request-id': 'datos-de-ejemplo' }
    try {
      const body = await mockRequest('GET', path, undefined, { signal })
      return { status: 200, headers, body, ms: performance.now() - started }
    } catch (error) {
      if (!(error instanceof ApiError)) throw error
      const body = { error: { code: error.code, message: error.message, request_id: error.requestId, details: error.details } }
      return { status: error.status, headers, body, ms: performance.now() - started }
    }
  }
  const response = await fetch(path, { signal })
  const headers = Object.fromEntries(SHOWN_HEADERS.flatMap((name) => (response.headers.has(name) ? [[name, response.headers.get(name) as string]] : [])))
  const text = await response.text()
  let body: unknown = text
  try {
    body = JSON.parse(text)
  } catch {
    // No es JSON (p. ej. la página de error de un proxy): se enseña el texto
  }
  return { status: response.status, headers, body, ms: performance.now() - started }
}
