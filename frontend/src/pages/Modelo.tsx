import { useState } from 'react'
import { ApiError, getJson } from '../api/client'
import type { Forecast, ModelReport, Prices } from '../api/types'
import { HourlyBars } from '../components/charts/HourlyBars'
import { LineChart } from '../components/charts/LineChart'
import { KpiCard } from '../components/KpiCard'
import { PageHeader } from '../components/PageHeader'
import { SegmentedControl } from '../components/SegmentedControl'
import { ErrorState, LoadingState } from '../components/States'
import { useApi } from '../hooks/useApi'
import { useNow } from '../hooks/useNow'
import { addDays, daysBetween, madridDate } from '../lib/dates'
import { formatDay, formatMwh, formatNumber, formatPercent, formatPeriod, formatShortDay, madridHour, plural } from '../lib/format'
import { groupByDay } from '../lib/history'
import { BASELINES, MODEL_LABELS, evaluateBaseline, intervalCoverage, mae, maeByDay, maeByDayType, maeByHour, type EvaluatedDay } from '../lib/model'
import styles from './Modelo.module.css'

const EVAL_DAYS = 14 // días evaluados en las gráficas
const HISTORY_DAYS = 7 // días anteriores que necesita la media de 7 días
const MODELS = ['lightgbm', ...BASELINES] as const
type ModelName = (typeof MODELS)[number]

const mwh = (value: number) => `${formatMwh(value)} €/MWh`
const pad = (hour: number) => String(hour).padStart(2, '0')

// --- Datos ---

type ModelData = {
  report: ModelReport
  evaluated: Record<ModelName, EvaluatedDay[]>
  start: string
  end: string
  missingForecasts: number // días del periodo sin previsión guardada de LightGBM
}

async function loadForecast(day: string, signal: AbortSignal): Promise<Forecast | null> {
  try {
    return await getJson<Forecast>('/v1/forecast', { date: day }, signal)
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null
    throw error
  }
}

/** Días de LightGBM: lo que guardó el pipeline, solo las horas con precio real. */
function lightgbmDays(forecasts: (Forecast | null)[]): EvaluatedDay[] {
  return forecasts.flatMap((f) => {
    if (!f || f.model !== 'lightgbm') return []
    const points = f.hours.flatMap((h) =>
      h.actual === null ? [] : [{ hour: madridHour(h.datetime), actual: h.actual, predicted: h.price, lower: h.lower, upper: h.upper }],
    )
    return points.length ? [{ day: f.date, points }] : []
  })
}

async function loadModel(today: string, signal: AbortSignal): Promise<ModelData> {
  const start = addDays(today, -(EVAL_DAYS - 1))
  const evalDays = daysBetween(start, today)
  const [report, prices, ...forecasts] = await Promise.all([
    getJson<ModelReport>('/api/model', { days: 30 }, signal),
    getJson<Prices>('/v1/prices', { start: addDays(start, -HISTORY_DAYS), end: today }, signal),
    ...evalDays.map((day) => loadForecast(day, signal)),
  ])
  const days = groupByDay(prices.hours)
  const lightgbm = lightgbmDays(forecasts)
  return {
    report,
    evaluated: {
      lightgbm,
      media_7_dias: evaluateBaseline(days, 'media_7_dias', start),
      precio_ayer: evaluateBaseline(days, 'precio_ayer', start),
    },
    start,
    end: today,
    missingForecasts: evalDays.length - lightgbm.length,
  }
}

// --- Página ---

export default function Modelo() {
  const today = madridDate(useNow())
  const data = useApi((signal) => loadModel(today, signal), [today])
  const [model, setModel] = useState<ModelName>('lightgbm')

  return (
    <>
      <PageHeader eyebrow="Modelo" title="¿Cuánto acierta la previsión?">
        Comparamos cada día la previsión con el precio que publica REE, y la ponemos frente a dos referencias simples que cualquier
        modelo tiene que mejorar: el precio de ayer y la media de la misma hora en la última semana.
      </PageHeader>
      {data.status === 'loading' && <LoadingState label="Cargando la evaluación del modelo…" />}
      {data.status === 'error' && <ErrorState error={data.error} onRetry={data.reload} />}
      {data.status === 'success' && (
        <>
          <div className={styles.selector}>
            <span>Ver gráficas de:</span>
            <SegmentedControl
              label="Modelo"
              value={model}
              onChange={setModel}
              segments={MODELS.map((m) => ({ value: m, label: m === 'lightgbm' ? `${MODEL_LABELS[m]} (en uso)` : MODEL_LABELS[m] }))}
            />
          </div>
          <Metrics data={data.data} model={model} />
          <ModelCharts key={model} data={data.data} model={model} />
          <DayTypes data={data.data} />
          <Backtest report={data.data.report} />
          <HowItWorks />
        </>
      )}
    </>
  )
}

function Metrics({ data, model }: { data: ModelData; model: ModelName }) {
  const evaluated = data.evaluated[model]
  const error = mae(evaluated)
  const { backtest, live } = data.report
  const lightgbm = backtest?.models.find((m) => m.model === 'lightgbm')

  return (
    <section aria-label="Métricas" className={styles.kpis}>
      <KpiCard
        label={`Error medio por hora · ${MODEL_LABELS[model]}`}
        value={error === null ? '—' : formatMwh(error)}
        unit={error === null ? undefined : '€/MWh'}
        detail={evaluated.length ? `${plural(evaluated.length, 'día evaluado', 'días evaluados')} (${formatPeriod(evaluated[0].day, evaluated[evaluated.length - 1].day)})` : 'Sin días evaluados todavía'}
      />
      <KpiCard
        label="Error en producción, últimos 30 días"
        value={live.mae === null ? '—' : formatMwh(live.mae)}
        unit={live.mae === null ? undefined : '€/MWh'}
        detail={live.days.length ? `${plural(live.days.length, 'día con previsión publicada', 'días con previsión publicada')}${live.fallback_days ? `, ${live.fallback_days} con respaldo` : ''}` : 'El pipeline aún no ha evaluado ningún día'}
      />
      <KpiCard
        label="Mejora frente a la mejor referencia"
        value={backtest?.improvement_pct == null ? '—' : formatPercent(backtest.improvement_pct, 1)}
        detail={backtest ? `Backtest de ${backtest.days} días` : 'Modelo sin métricas de entrenamiento'}
      />
      <KpiCard
        dark
        label="Modelo en uso"
        value={lightgbm ? formatMwh(lightgbm.mae) : 'LightGBM'}
        unit={lightgbm ? '€/MWh' : undefined}
        detail={`Entrenado el ${formatDay(data.report.model.trained_at.slice(0, 10))} con ${formatNumber(data.report.model.training_rows)} horas`}
      />
    </section>
  )
}

function ModelCharts({ data, model }: { data: ModelData; model: ModelName }) {
  const evaluated = data.evaluated[model]
  const [day, setDay] = useState<string>('all')

  if (!evaluated.length) {
    return (
      <p className="card muted">
        {model === 'lightgbm'
          ? 'Todavía no hay previsiones de LightGBM con su precio real en este periodo: el pipeline las guarda cada día y se evalúan cuando REE publica el precio.'
          : 'No hay suficientes días de precios para calcular esta referencia.'}
      </p>
    )
  }

  const shown = day === 'all' ? evaluated : evaluated.filter((d) => d.day === day)
  const points = shown.flatMap((d) => d.points.map((p) => ({ ...p, day: d.day })))
  const labels = points.map((p) => (shown.length > 1 ? (p.hour === 0 ? formatShortDay(p.day) : '') : pad(p.hour)))
  const byHour = maeByHour(evaluated)
  const ranked = byHour.map((v, h) => ({ v, h })).filter((x): x is { v: number; h: number } => x.v !== null).sort((a, b) => b.v - a.v)
  const worst = new Set(ranked.slice(0, 3).map((x) => x.h))
  const byDay = maeByDay(evaluated)
  const best = [...byDay].sort((a, b) => a.mae - b.mae)[0]
  const worstDay = [...byDay].sort((a, b) => b.mae - a.mae)[0]
  const shownMae = mae(shown)
  const covered = model === 'lightgbm' ? intervalCoverage(evaluated) : null

  return (
    <>
      <section aria-labelledby="frente" className={`section ${styles.section}`}>
        <div className={styles.head}>
          <div>
            <h2 id="frente">Previsión frente a precio real</h2>
            <p className="muted">
              {MODEL_LABELS[model]} · {day === 'all' ? (evaluated.length === 1 ? 'último día' : `últimos ${evaluated.length} días`) : formatDay(day)} · error medio{' '}
              {shownMae === null ? '—' : mwh(shownMae)}
            </p>
          </div>
          <SegmentedControl
            label="Periodo"
            value={day}
            onChange={setDay}
            segments={[{ value: 'all', label: 'Todos' }, ...evaluated.slice(-7).map((d) => ({ value: d.day, label: formatShortDay(d.day) }))]}
          />
        </div>
        {data.missingForecasts > 0 && model === 'lightgbm' && (
          <p className={styles.hint}>
            {data.missingForecasts} de los últimos {EVAL_DAYS} días no tienen previsión guardada con su precio real: no se cuentan.
          </p>
        )}
        <LineChart
          ariaLabel={`Precio real y previsión de ${MODEL_LABELS[model]}, en €/MWh`}
          xLabel={shown.length > 1 ? 'Día y hora' : 'Hora'}
          labels={labels}
          tableLabels={points.map((p) => (shown.length > 1 ? `${formatShortDay(p.day)}, ${p.hour} h` : `${p.hour} h`))}
          series={[
            { key: 'real', label: 'Precio real', color: 'var(--color-chart-line)', values: points.map((p) => p.actual) },
            { key: 'prevision', label: 'Previsión', color: 'var(--color-forecast-2)', values: points.map((p) => p.predicted), dashed: true },
          ]}
          band={{
            label: 'Diferencia',
            color: 'var(--color-chart-error)',
            lower: points.map((p) => Math.min(p.actual, p.predicted)),
            upper: points.map((p) => Math.max(p.actual, p.predicted)),
          }}
          formatTick={(v) => formatNumber(v)}
          formatValue={mwh}
          height={260}
          zeroBased
        />
        {covered && (
          <p className={styles.hint}>
            Rango probable: el precio real cayó dentro en el {formatPercent(covered.coverage * 100)} de las {covered.hours} horas evaluadas que lo
            tienen.
          </p>
        )}
      </section>

      <div className={styles.pair}>
        <section aria-labelledby="por-hora" className={`section ${styles.section}`}>
          <div>
            <h2 id="por-hora">Error por hora del día</h2>
            {ranked.length >= 2 && (
              <p className="muted">
                Falla más a las {ranked[0].h} h ({mwh(ranked[0].v)}) y a las {ranked[1].h} h; acierta más a las {ranked[ranked.length - 1].h} h (
                {mwh(ranked[ranked.length - 1].v)}).
              </p>
            )}
          </div>
          <HourlyBars
            ariaLabel={`Error medio de ${MODEL_LABELS[model]} por hora del día, en €/MWh`}
            valueLabel="Error"
            formatTick={(v) => formatNumber(v)}
            height={200}
            bars={byHour.map((v, h) => ({
              key: String(h),
              label: pad(h),
              name: `${h}–${h + 1} h`,
              value: v ?? 0,
              display: v === null ? 'sin datos' : mwh(v),
              color: worst.has(h) ? 'var(--color-period-punta)' : 'var(--color-price-3)',
            }))}
            legend={[
              { label: 'Las 3 horas con más error', color: 'var(--color-period-punta)' },
              { label: 'Resto', color: 'var(--color-price-3)' },
            ]}
          />
        </section>
        <section aria-labelledby="por-dia" className={`section ${styles.section}`}>
          <div>
            <h2 id="por-dia">Error de cada día</h2>
            <p className="muted">
              Mejor día: {formatShortDay(best.day)} ({mwh(best.mae)}). Peor día: {formatShortDay(worstDay.day)} ({mwh(worstDay.mae)}).
            </p>
          </div>
          <HourlyBars
            ariaLabel={`Error medio de ${MODEL_LABELS[model]} cada día, en €/MWh`}
            categoryLabel="Día"
            valueLabel="Error"
            formatTick={(v) => formatNumber(v)}
            height={200}
            bars={byDay.map((d) => ({
              key: d.day,
              label: formatShortDay(d.day),
              name: formatDay(d.day),
              value: d.mae,
              display: mwh(d.mae),
              color: d.day === worstDay.day ? 'var(--color-period-punta)' : 'var(--color-price-3)',
            }))}
          />
        </section>
      </div>
    </>
  )
}

function DayTypes({ data }: { data: ModelData }) {
  const rows = MODELS.map((m) => ({ model: m, ...maeByDayType(data.evaluated[m]) }))
  const bestOf = (key: 'workdays' | 'weekend') => Math.min(...rows.map((r) => r[key].mae ?? Infinity))
  const best = { workdays: bestOf('workdays'), weekend: bestOf('weekend') }
  const cell = (value: number | null, column: 'workdays' | 'weekend') => (
    <td className="num" data-best={value !== null && value === best[column] ? true : undefined}>
      {value === null ? '—' : formatMwh(value)}
    </td>
  )

  return (
    <section aria-labelledby="tipo-dia" className={`section ${styles.section}`}>
      <div>
        <h2 id="tipo-dia">Laborables frente a fin de semana</h2>
        <p className="muted">
          Error medio en €/MWh {formatPeriod(data.start, data.end)}. Resaltado, el mejor de cada columna. Con pocos días de fin de semana,
          tómalo como una pista, no como una conclusión.
        </p>
      </div>
      <div className={styles.tableScroll}>
        <table className={styles.table} aria-labelledby="tipo-dia">
          <thead>
            <tr>
              <th scope="col">Modelo</th>
              <th scope="col">Laborables</th>
              <th scope="col">Fin de semana</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.model}>
                <th scope="row">
                  {MODEL_LABELS[r.model]}{' '}
                  <span className={styles.days}>
                    ({r.workdays.days} + {r.weekend.days} días)
                  </span>
                </th>
                {cell(r.workdays.mae, 'workdays')}
                {cell(r.weekend.mae, 'weekend')}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function Backtest({ report }: { report: ModelReport }) {
  const { backtest } = report
  if (!backtest) return null
  const top = Math.max(...backtest.models.map((m) => m.mae))

  return (
    <section aria-labelledby="comparativa" className={`section ${styles.section}`}>
      <div>
        <h2 id="comparativa">Comparativa de modelos</h2>
        <p className="muted">
          Backtest {formatPeriod(backtest.start, backtest.end)}. {backtest.method}
        </p>
      </div>
      <div className={styles.tableScroll}>
        <table className={styles.table} aria-labelledby="comparativa">
          <thead>
            <tr>
              <th scope="col">Modelo</th>
              <th scope="col">Error medio (€/MWh)</th>
              <th scope="col">RMSE</th>
              <th scope="col">Sesgo</th>
              <th scope="col">
                <span className="visually-hidden">Comparativa</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {backtest.models.map((m) => (
              <tr key={m.model}>
                <th scope="row">
                  {m.label} {!m.is_baseline && <span className={styles.badge}>En uso</span>}
                </th>
                <td className="num">{formatMwh(m.mae)}</td>
                <td className="num">{formatMwh(m.rmse)}</td>
                <td className="num">{formatMwh(m.bias).replace('-', '−')}</td>
                <td className={styles.barCell} aria-hidden="true">
                  <span style={{ width: `${(m.mae / top) * 100}%` }} data-model={m.is_baseline ? 'baseline' : 'model'} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className={styles.hint}>Sesgo negativo: la previsión se queda corta de media. RMSE castiga más los errores grandes.</p>
      {backtest.interval && (
        <p className={styles.hint}>
          Además de la previsión, LightGBM da un rango probable para cada hora. En el backtest, el precio real cayó dentro en el{' '}
          {formatPercent(backtest.interval.coverage * 100, 1)} de las horas (se busca el {formatPercent(backtest.interval.level * 100)}), con un rango
          medio de {mwh(backtest.interval.width)}.
        </p>
      )}
    </section>
  )
}

const STEPS = [
  { title: 'Ingesta', text: 'Descarga diaria del PVPC y del mix de generación desde la API pública de REE, tras su publicación hacia las 20:15.' },
  { title: 'Limpieza', text: 'Serie horaria continua en UTC: cambios de hora, duplicados y huecos cortos.' },
  { title: 'Variables', text: 'Calendario, festivos, tramo 2.0TD y precios de días anteriores (nunca del día que se predice).' },
  { title: 'Modelo', text: 'LightGBM entrenado con dos años de datos y validado día a día, siempre frente a las referencias simples.' },
  { title: 'Previsión', text: 'Las horas del día siguiente, publicadas en el panel, en la API y en el resumen diario de ntfy.' },
]

function HowItWorks() {
  return (
    <section aria-labelledby="como" className={`section ${styles.section}`}>
      <h2 id="como">Cómo funciona</h2>
      <ol className={styles.steps}>
        {STEPS.map((step, i) => (
          <li key={step.title}>
            <span className={styles.stepNumber}>{pad(i + 1)}</span>
            <strong>{step.title}</strong>
            <span className="muted">{step.text}</span>
          </li>
        ))}
      </ol>
      <p className={styles.hint}>Error = media del valor absoluto de (previsión − real), hora a hora.</p>
    </section>
  )
}
