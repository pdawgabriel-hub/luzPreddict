import { useId, useState } from 'react'
import { getJson } from '../api/client'
import { loadDay, type Day } from '../api/days'
import type { Prices } from '../api/types'
import { PageHeader } from '../components/PageHeader'
import { SegmentedControl } from '../components/SegmentedControl'
import { ErrorState, LoadingState } from '../components/States'
import { NTFY_TOPIC, NTFY_TOPIC_URL } from '../config'
import { useApi } from '../hooks/useApi'
import { useNow } from '../hooks/useNow'
import { addDays, madridDate } from '../lib/dates'
import { buildDigest } from '../lib/digest'
import { formatDay, formatKwh, madridHour } from '../lib/format'
import { MAX_ALERTS, history, loadAlerts, matchingHours, newAlertId, saveAlerts, type Alert, type Direction } from '../lib/localAlerts'
import type { HourPrice } from '../lib/prices'
import styles from './Alertas.module.css'

const MAX_THRESHOLD = 400 // €/MWh: 0,40 €/kWh
const STEP = 5
const DIRECTION_TEXT: Record<Direction, string> = { below: 'baje de', above: 'suba de' }

type AlertsData = { target: Day; isTomorrow: boolean; past: HourPrice[]; previous: HourPrice[] }

async function loadData(today: string, signal: AbortSignal): Promise<AlertsData | null> {
  const [tomorrow, past] = await Promise.all([
    loadDay(addDays(today, 1), signal),
    getJson<Prices>('/v1/prices', { start: addDays(today, -29), end: today }, signal),
  ])
  const todayHours = past.hours.filter((h) => h.datetime.startsWith(today))
  const target: Day | null = tomorrow ?? (todayHours.length ? { day: today, kind: 'published', hours: todayHours } : null)
  if (!target) return null
  return { target, isTomorrow: tomorrow !== null, past: past.hours, previous: tomorrow ? todayHours : [] }
}

const hourList = (hours: HourPrice[], max = 6) =>
  hours.length
    ? `${hours.length} ${hours.length === 1 ? 'hora' : 'horas'} (${hours
        .slice(0, max)
        .map((h) => `${madridHour(h.datetime)} h`)
        .join(', ')}${hours.length > max ? '…' : ''})`
    : 'ninguna hora'

function historyText(alert: Pick<Alert, 'direction' | 'threshold'>, past: HourPrice[]): string {
  const h = history(alert, past)
  return `Últimos ${h.total} días: habría saltado ${h.days} ${h.days === 1 ? 'día' : 'días'} (${h.hours} ${h.hours === 1 ? 'hora' : 'horas'}).`
}

// --- Página ---

export default function Alertas() {
  const today = madridDate(useNow())
  const data = useApi((signal) => loadData(today, signal), [today])
  const [alerts, setAlerts] = useState<Alert[]>(() => loadAlerts())
  const [storageFailed, setStorageFailed] = useState(false)

  const store = (next: Alert[]) => {
    setAlerts(next)
    setStorageFailed(!saveAlerts(next))
  }

  return (
    <>
      <PageHeader eyebrow="Alertas" title="Avísame cuando la luz…">
        Guarda un umbral y te decimos qué horas de mañana lo cumplen. Para recibir el aviso en el móvil, suscríbete al resumen diario
        por ntfy: sin cuentas, sin correo y sin dejar tus datos.
      </PageHeader>
      {data.status === 'loading' && <LoadingState label="Cargando los precios…" />}
      {data.status === 'error' && <ErrorState error={data.error} onRetry={data.reload} />}
      {data.status === 'success' && !data.data && <p className="card muted">Todavía no hay precios para comprobar las alertas.</p>}
      {data.status === 'success' && data.data && (
        <>
          {storageFailed && (
            <p role="alert" className={styles.warning}>
              Tu navegador no deja guardar datos (¿modo privado?): las alertas se perderán al cerrar la página.
            </p>
          )}
          <div className={styles.columns}>
            <NewAlert data={data.data} alerts={alerts} onCreate={(alert) => store([...alerts, alert])} />
            <MyAlerts
              data={data.data}
              alerts={alerts}
              onToggle={(id) => store(alerts.map((a) => (a.id === id ? { ...a, active: !a.active } : a)))}
              onRemove={(id) => store(alerts.filter((a) => a.id !== id))}
            />
          </div>
          <Ntfy data={data.data} />
        </>
      )}
    </>
  )
}

function Strip({ hours, alert }: { hours: HourPrice[]; alert: Pick<Alert, 'direction' | 'threshold'> }) {
  const hits = new Set(matchingHours(alert, hours).map((h) => h.datetime))
  return (
    <div className={styles.stripWrap} aria-hidden="true">
      <div className={styles.strip} style={{ gridTemplateColumns: `repeat(${hours.length}, 1fr)` }}>
        {hours.map((h) => (
          <span key={h.datetime} data-hit={hits.has(h.datetime) ? alert.direction : undefined} />
        ))}
      </div>
      <div className={styles.stripHours} style={{ gridTemplateColumns: `repeat(${hours.length}, 1fr)` }}>
        {hours.map((h, i) => (
          <span key={h.datetime}>{madridHour(h.datetime) % 3 === 0 && (i === 0 || madridHour(hours[i - 1].datetime) !== madridHour(h.datetime)) ? String(madridHour(h.datetime)).padStart(2, '0') : ''}</span>
        ))}
      </div>
    </div>
  )
}

function NewAlert({ data, alerts, onCreate }: { data: AlertsData; alerts: Alert[]; onCreate: (alert: Alert) => void }) {
  const [direction, setDirection] = useState<Direction>('below')
  const [threshold, setThreshold] = useState(100)
  const sliderId = useId()
  const draft = { direction, threshold }
  const hits = matchingHours(draft, data.target.hours)
  const duplicate = alerts.some((a) => a.direction === direction && a.threshold === threshold)
  const full = alerts.length >= MAX_ALERTS
  const source = data.target.kind === 'forecast' ? 'la previsión de mañana' : data.isTomorrow ? 'los precios de mañana' : 'los precios de hoy'

  return (
    <section aria-labelledby="nueva" className={`section ${styles.form}`}>
      <h2 id="nueva">Nueva alerta</h2>
      <div className={styles.field}>
        <span className={styles.label}>Condición</span>
        <SegmentedControl
          label="Condición"
          value={direction}
          onChange={setDirection}
          segments={[
            { value: 'below', label: 'Baje de' },
            { value: 'above', label: 'Suba de' },
          ]}
        />
      </div>
      <div className={styles.field}>
        <div className={styles.rangeHead}>
          <label htmlFor={sliderId}>Umbral</label>
          <output htmlFor={sliderId} className="num">
            {formatKwh(threshold)} €/kWh
          </output>
        </div>
        <input
          id={sliderId}
          type="range"
          min={0}
          max={MAX_THRESHOLD}
          step={STEP}
          value={threshold}
          aria-valuetext={`${formatKwh(threshold)} euros por kilovatio hora`}
          onChange={(event) => setThreshold(Number(event.target.value))}
          className={styles.range}
        />
      </div>
      <div className={styles.preview}>
        <p aria-live="polite">
          <strong>Con {source}:</strong> saltaría en {hourList(hits)}.
        </p>
        <Strip hours={data.target.hours} alert={draft} />
        <p className="muted">{historyText(draft, data.past)}</p>
      </div>
      {(duplicate || full) && (
        <p className={styles.hint}>{full ? `Has llegado al máximo de ${MAX_ALERTS} alertas.` : 'Ya tienes una alerta igual.'}</p>
      )}
      <button type="button" className={styles.primary} disabled={duplicate || full} onClick={() => onCreate({ id: newAlertId(), direction, threshold, active: true })}>
        Guardar alerta
      </button>
    </section>
  )
}

function MyAlerts({ data, alerts, onToggle, onRemove }: { data: AlertsData; alerts: Alert[]; onToggle: (id: string) => void; onRemove: (id: string) => void }) {
  const active = alerts.filter((a) => a.active).length
  const when = data.isTomorrow ? 'mañana' : 'hoy'

  return (
    <section aria-labelledby="mis-alertas" className={`section ${styles.list}`}>
      <div className={styles.head}>
        <h2 id="mis-alertas">Mis alertas</h2>
        <span className="muted">
          {active} {active === 1 ? 'activa' : 'activas'}
        </span>
      </div>
      {!alerts.length && <p className="muted">No tienes alertas. Crea la primera desde el formulario.</p>}
      <ul className={styles.alerts}>
        {alerts.map((alert) => {
          const hits = matchingHours(alert, data.target.hours)
          const title = `Cuando ${DIRECTION_TEXT[alert.direction]} ${formatKwh(alert.threshold)} €/kWh`
          return (
            <li key={alert.id} className={styles.alert} data-paused={!alert.active || undefined}>
              <span className={styles.arrow} data-direction={alert.direction} aria-hidden="true">
                {alert.direction === 'below' ? '↓' : '↑'}
              </span>
              <div className={styles.alertText}>
                <span className={styles.alertTitle}>{title}</span>
                <span>
                  {hits.length ? (
                    <strong className={styles.hit}>
                      Salta {when}: {hourList(hits)}
                    </strong>
                  ) : (
                    `${when === 'mañana' ? 'Mañana' : 'Hoy'} no salta`
                  )}
                </span>
                <span className="muted">{historyText(alert, data.past)}</span>
              </div>
              <div className={styles.actions}>
                <button type="button" className={styles.toggle} aria-pressed={alert.active} onClick={() => onToggle(alert.id)}>
                  {alert.active ? 'Activa' : 'En pausa'}
                </button>
                <button type="button" className={styles.remove} aria-label={`Borrar la alerta: ${title.toLowerCase()}`} onClick={() => onRemove(alert.id)}>
                  ×
                </button>
              </div>
            </li>
          )
        })}
      </ul>
      <p className={styles.hint}>
        Se guardan solo en este navegador: no hay cuentas y no se envían a ningún servidor. La web las comprueba cada vez que entras.
      </p>
    </section>
  )
}

function Ntfy({ data }: { data: AlertsData }) {
  const [copied, setCopied] = useState(false)
  const digest = buildDigest(data.target.day, data.target.hours, { kind: data.target.kind, model: data.target.model }, data.previous)
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(NTFY_TOPIC)
      setCopied(true)
    } catch {
      setCopied(false)
    }
  }

  return (
    <section aria-labelledby="ntfy" className={`section ${styles.ntfy}`}>
      <div>
        <h2 id="ntfy">Resumen diario en el móvil</h2>
        <p className="muted">
          Cada tarde, cuando REE publica los precios de mañana, enviamos un resumen al tema público de{' '}
          <a href="https://ntfy.sh">ntfy</a>, una app gratuita y de código abierto para recibir notificaciones.
        </p>
      </div>
      <ol className={styles.steps}>
        <li>
          Instala ntfy en tu móvil (<a href="https://play.google.com/store/apps/details?id=io.heckel.ntfy">Android</a> o{' '}
          <a href="https://apps.apple.com/app/ntfy/id1625396347">iPhone</a>).
        </li>
        <li>
          Suscríbete al tema <code className={styles.topic}>{NTFY_TOPIC}</code>{' '}
          <button type="button" className={styles.copy} onClick={copy}>
            {copied ? 'Copiado' : 'Copiar'}
          </button>{' '}
          o ábrelo en <a href={NTFY_TOPIC_URL}>{NTFY_TOPIC_URL.replace('https://', '')}</a>.
        </li>
        <li>Listo: no hace falta cuenta y no guardamos ningún dato tuyo.</li>
      </ol>
      <div>
        <h3>Así te llegaría</h3>
        <p className="muted">Con {data.target.kind === 'forecast' ? 'la previsión' : 'los precios'} del {formatDay(data.target.day)}.</p>
      </div>
      <article className={styles.notification} aria-label="Ejemplo de notificación">
        <header>
          <span>ntfy · {NTFY_TOPIC}</span>
          <span>20:30</span>
        </header>
        <p className={styles.notificationTitle}>{digest.title}</p>
        {digest.lines.map((line) => (
          <p key={line}>{line}</p>
        ))}
      </article>
      <p className={styles.hint}>
        El resumen es el mismo para todo el mundo. Tus alertas con umbral se comprueban aquí, en la web, cada vez que entras.
      </p>
    </section>
  )
}
