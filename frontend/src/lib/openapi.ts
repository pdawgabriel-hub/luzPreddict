// Lectura del esquema OpenAPI de la API (src/api/openapi.json, generado con make api-types)
// para documentar los endpoints públicos en la web sin escribirlos a mano.

type Schema = { type?: string; format?: string; minimum?: number; maximum?: number; default?: unknown; anyOf?: Schema[] }
type RawParameter = { name: string; in: string; required?: boolean; description?: string; schema?: Schema }
type RawOperation = { summary?: string; description?: string; tags?: string[]; parameters?: RawParameter[] }
export type OpenApiSpec = { info: { title: string; version: string }; paths: Record<string, Record<string, RawOperation>> }

export type Parameter = {
  name: string
  kind: 'date' | 'integer' | 'string'
  required: boolean
  description: string
  minimum?: number
  maximum?: number
  default?: unknown
}

export type Endpoint = { path: string; summary: string; description: string; tag: string; parameters: Parameter[] }

/** El tipo real de un parámetro: los opcionales vienen como anyOf [tipo, null]. */
function resolve(schema: Schema = {}): Schema {
  return schema.anyOf?.find((s) => s.type !== 'null') ?? schema
}

function parameter(raw: RawParameter): Parameter {
  const schema = resolve(raw.schema)
  return {
    name: raw.name,
    kind: schema.format === 'date' ? 'date' : schema.type === 'integer' ? 'integer' : 'string',
    required: raw.required ?? false,
    description: raw.description ?? '',
    minimum: schema.minimum,
    maximum: schema.maximum,
    default: raw.schema?.default ?? schema.default,
  }
}

/** Endpoints públicos (GET de /v1 y /health), en el orden del esquema. */
export function publicEndpoints(spec: OpenApiSpec): Endpoint[] {
  return Object.entries(spec.paths).flatMap(([path, item]) => {
    const op = item.get
    if (!op || !(path.startsWith('/v1/') || path === '/health')) return []
    return [
      {
        path,
        summary: op.summary ?? path,
        description: op.description ?? '',
        tag: op.tags?.[0] ?? '',
        parameters: (op.parameters ?? []).filter((p) => p.in === 'query').map(parameter),
      },
    ]
  })
}

/** Ruta con los parámetros rellenos (los vacíos no se envían). */
export function requestPath(endpoint: Endpoint, values: Record<string, string>): string {
  const query = new URLSearchParams()
  for (const p of endpoint.parameters) {
    const value = values[p.name]?.trim()
    if (value) query.set(p.name, value)
  }
  const search = query.toString()
  return search ? `${endpoint.path}?${search}` : endpoint.path
}
