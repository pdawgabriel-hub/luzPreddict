import { useState } from 'react'
import { inspect, type RawResponse } from '../api/client'
import spec from '../api/openapi.json'
import { PageHeader } from '../components/PageHeader'
import { SegmentedControl } from '../components/SegmentedControl'
import { useNow } from '../hooks/useNow'
import { madridDate } from '../lib/dates'
import { formatNumber } from '../lib/format'
import { publicEndpoints, requestPath, type Endpoint, type OpenApiSpec, type Parameter } from '../lib/openapi'
import styles from './Desarrolladores.module.css'

const ENDPOINTS = publicEndpoints(spec as unknown as OpenApiSpec)
const STATUS_TEXT: Record<number, string> = {
  200: 'OK',
  404: 'Not Found',
  422: 'Unprocessable Content',
  500: 'Internal Server Error',
  503: 'Service Unavailable',
}

/** Valores de ejemplo para empezar: el día de hoy y una duración de 2 horas. */
function exampleValues(endpoint: Endpoint, today: string): Record<string, string> {
  const values: Record<string, string> = {}
  for (const p of endpoint.parameters) {
    if (p.name === 'date' && endpoint.path !== '/v1/forecast') values[p.name] = today
    if (p.name === 'hours') values[p.name] = '2'
  }
  return values
}

export default function Desarrolladores() {
  const today = madridDate(useNow())
  const [path, setPath] = useState(ENDPOINTS[0]?.path ?? '/health')
  const endpoint = ENDPOINTS.find((e) => e.path === path) ?? ENDPOINTS[0]

  return (
    <>
      <PageHeader
        eyebrow="Para desarrolladores"
        title="API pública de luzPreddict"
        aside={
          <span className={styles.badges}>
            <span className={styles.badge} data-kind="ok">
              Sin clave de API
            </span>
            <span className={styles.badge}>Solo lectura · JSON</span>
            <span className={styles.badge}>v{spec.info.version}</span>
          </span>
        }
      >
        Precios, previsiones, mejores horas y mix de generación en JSON, para tu domótica o tus scripts. Sin registro. Las respuestas de
        esta página son reales: se piden a la API al pulsar «Enviar».
      </PageHeader>
      <div className={styles.columns}>
        <nav aria-label="Endpoints" className={styles.nav}>
          <ul>
            {ENDPOINTS.map((e) => (
              <li key={e.path}>
                <button type="button" aria-pressed={e.path === endpoint.path} onClick={() => setPath(e.path)}>
                  <span className={styles.method}>GET</span>
                  <span className={styles.navText}>
                    <span className="num">{e.path}</span>
                    <span className={styles.navSummary}>{e.summary}</span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </nav>
        {/* key: al cambiar de endpoint, los parámetros y la respuesta empiezan de cero */}
        <Console key={endpoint.path} endpoint={endpoint} today={today} />
      </div>
      <Details />
    </>
  )
}

function Console({ endpoint, today }: { endpoint: Endpoint; today: string }) {
  const [values, setValues] = useState(() => exampleValues(endpoint, today))
  const [result, setResult] = useState<RawResponse | null>(null)
  const [sending, setSending] = useState(false)
  const [copied, setCopied] = useState(false)
  const path = requestPath(endpoint, values)
  const curl = `curl -s "${window.location.origin}${path}"`

  const send = async () => {
    setSending(true)
    try {
      setResult(await inspect(path))
    } catch {
      setResult({ status: 0, headers: {}, body: 'No se ha podido conectar con la API.', ms: 0 })
    } finally {
      setSending(false)
    }
  }

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(curl)
      setCopied(true)
    } catch {
      setCopied(false)
    }
  }

  return (
    <section aria-labelledby="endpoint" className={`section ${styles.console}`}>
      <div>
        <div className={styles.title}>
          <span className={styles.method}>GET</span>
          <h2 id="endpoint" className="num">
            {endpoint.path}
          </h2>
        </div>
        <p className="muted">{endpoint.description || endpoint.summary}</p>
      </div>

      <div className={styles.block}>
        <h3>Parámetros</h3>
        {endpoint.parameters.length ? (
          <div className={styles.params}>
            {endpoint.parameters.map((p) => (
              <ParameterField
                key={p.name}
                parameter={p}
                value={values[p.name] ?? ''}
                onChange={(value) => {
                  setValues({ ...values, [p.name]: value })
                  setCopied(false)
                }}
              />
            ))}
          </div>
        ) : (
          <p className="muted">Sin parámetros.</p>
        )}
      </div>

      <div className={styles.block}>
        <div className={styles.blockHead}>
          <h3>Petición</h3>
          <div className={styles.actions}>
            <button type="button" className={styles.secondary} onClick={copy}>
              {copied ? 'Copiado' : 'Copiar curl'}
            </button>
            <button type="button" className={styles.primary} onClick={send} disabled={sending}>
              {sending ? 'Enviando…' : 'Enviar'}
            </button>
          </div>
        </div>
        <pre className={styles.code}>{curl}</pre>
      </div>

      <div className={styles.block} aria-live="polite">
        <h3>Respuesta</h3>
        {!result && <p className="muted">Pulsa «Enviar» para ver la respuesta.</p>}
        {result && (
          <>
            <p className={styles.status} data-ok={result.status >= 200 && result.status < 300 ? true : undefined}>
              {result.status ? `${result.status} ${STATUS_TEXT[result.status] ?? ''}`.trim() : 'Sin conexión'}
              <span className="muted"> · {formatNumber(result.ms)} ms</span>
            </p>
            {Object.keys(result.headers).length > 0 && (
              <pre className={styles.headers} aria-label="Cabeceras de la respuesta">
                {Object.entries(result.headers)
                  .map(([name, value]) => `${name}: ${value}`)
                  .join('\n')}
              </pre>
            )}
            <pre className={styles.code} tabIndex={0} aria-label="Cuerpo de la respuesta">
              {typeof result.body === 'string' ? result.body : JSON.stringify(result.body, null, 2)}
            </pre>
          </>
        )}
      </div>
    </section>
  )
}

function ParameterField({ parameter, value, onChange }: { parameter: Parameter; value: string; onChange: (value: string) => void }) {
  const id = `param-${parameter.name}`
  const range = parameter.minimum !== undefined && parameter.maximum !== undefined ? ` (${parameter.minimum}–${parameter.maximum})` : ''
  const defaultText = parameter.default !== undefined && parameter.default !== null ? `Por defecto, ${String(parameter.default)}.` : ''

  return (
    <div className={styles.param}>
      <label htmlFor={id} className="num">
        {parameter.name}
        {parameter.required && <span aria-hidden="true"> *</span>}
      </label>
      <input
        id={id}
        type={parameter.kind === 'date' ? 'date' : parameter.kind === 'integer' ? 'number' : 'text'}
        value={value}
        min={parameter.minimum}
        max={parameter.maximum}
        required={parameter.required}
        aria-describedby={`${id}-ayuda`}
        onChange={(event) => onChange(event.target.value)}
      />
      <span id={`${id}-ayuda`} className={styles.paramHelp}>
        {parameter.description}
        {range} {defaultText}
      </span>
    </div>
  )
}

const ERROR_EXAMPLE = `{
  "error": {
    "code": "validation_error",
    "message": "Parámetros no válidos",
    "request_id": "8f1c2a…",
    "details": [{ "field": "query.end", "message": "El rango no puede superar 31 días", "type": "value_error" }]
  }
}`

function Details() {
  const [topic, setTopic] = useState<'cache' | 'errors'>('cache')
  return (
    <section aria-label="Detalles" className={styles.details}>
      <div>
        <strong>Unidades y horas</strong>
        <span>
          Precios en €/MWh (divide entre 1000 para €/kWh). Horas en hora local de Madrid, ISO 8601 con desfase: los días de cambio de hora
          tienen 23 o 25 horas.
        </span>
      </div>
      <div>
        <strong>Fuente</strong>
        <span>
          Cada respuesta lleva <code>source</code> con la serie de Red Eléctrica (REE) de la que salen los datos. La previsión añade un{' '}
          <code>disclaimer</code>: es orientativa.
        </span>
      </div>
      <div className={styles.wide}>
        <SegmentedControl
          label="Tema"
          value={topic}
          onChange={setTopic}
          segments={[
            { value: 'cache', label: 'Caché' },
            { value: 'errors', label: 'Errores' },
          ]}
        />
        {topic === 'cache' ? (
          <span>
            Los datos cambian una vez al día, cuando se importan los precios que REE publica hacia las 20:15. Las respuestas de{' '}
            <code>/v1</code> llevan <code>Cache-Control</code> válido hasta esa actualización: no hace falta pedirlas más a menudo.
          </span>
        ) : (
          <>
            <span>
              Todos los errores tienen la misma forma, con el id de la petición (también en la cabecera <code>X-Request-ID</code>). Un{' '}
              <code>503</code> con <code>Retry-After</code> indica que la base de datos está arrancando: reintenta en unos segundos.
            </span>
            <pre className={styles.code}>{ERROR_EXAMPLE}</pre>
          </>
        )}
      </div>
      <div>
        <strong>Referencia completa</strong>
        <span>
          Todos los esquemas y respuestas, en la documentación interactiva OpenAPI: <a href="/docs">/docs</a> (o el JSON en{' '}
          <a href="/openapi.json">/openapi.json</a>).
        </span>
      </div>
    </section>
  )
}
