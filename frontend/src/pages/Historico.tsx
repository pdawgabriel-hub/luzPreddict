import { useSearchParams } from 'react-router'
import { getJson } from '../api/client'
import type { History, Prices } from '../api/types'
import { Heatmap } from '../components/charts/Heatmap'
import { LineChart } from '../components/charts/LineChart'
import { KpiCard } from '../components/KpiCard'
import { PageHeader } from '../components/PageHeader'
import { SegmentedControl } from '../components/SegmentedControl'
import { ErrorState, LoadingState } from '../components/States'
import { useApi } from '../hooks/useApi'
import { useNow } from '../hooks/useNow'
import type { Step } from '../lib/chart'
import { addDays, madridDate } from '../lib/dates'
import { argExtremes, groupByDay, hourlyProfile, isWeekend, periodStats, weekdayMeans, type DayPrices } from '../lib/history'
import { formatKwh, formatNumber, formatPercent, formatPeriod, formatShortDay, formatWeekdayDay, madridHour } from '../lib/format'
import { changePct, mean, type HourPrice } from '../lib/prices'
import styles from './Historico.module.css'

const RANGES = [7, 14, 30] as const
type Range = (typeof RANGES)[number]
const DEFAULT_RANGE: Range = 30

const CHEAP_THRESHOLD = 100 // €/MWh: 0,10 €/kWh
const WEEKDAYS = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']

// Tramos del mapa de calor, en €/MWh (la leyenda, en €/kWh)
const STEPS: Step[] = [
  { max: 60, color: 'var(--color-price-1)', label: '< 0,06' },
  { max: 120, color: 'var(--color-price-2)', label: '0,06–0,12' },
  { max: 180, color: 'var(--color-price-3)', label: '0,12–0,18' },
  { max: 240, color: 'var(--color-price-4)', label: '0,18–0,24' },
  { max: Infinity, color: 'var(--color-price-5)', label: '> 0,24' },
]

const kwh = (price: number) => `${formatKwh(price)} €/kWh`
const pad = (hour: number) => String(hour).padStart(2, '0')
const HOURS = Array.from({ length: 24 }, (_, h) => pad(h))

type HistoryData = { start: string; end: string; hours: HourPrice[]; missing: string[]; previousMean: number | null }

async function loadHistory(start: string, end: string, signal: AbortSignal): Promise<HistoryData> {
  const range = (Date.parse(end) - Date.parse(start)) / 86_400_000 + 1
  const [prices, previous] = await Promise.all([
    getJson<Prices>('/v1/prices', { start, end }, signal),
    // El periodo anterior, solo para comparar la media; si no hay datos, no se compara
    getJson<History>('/v1/history', { start: addDays(start, -range), end: addDays(start, -1) }, signal).catch(() => null),
  ])
  return {
    start,
    end,
    hours: prices.hours,
    missing: prices.missing_days,
    previousMean: previous?.days.length ? mean(previous.days.map((d) => d.avg_price)) : null,
  }
}

function parseRange(value: string | null): Range {
  const range = Number(value)
  return (RANGES as readonly number[]).includes(range) ? (range as Range) : DEFAULT_RANGE
}

export default function Historico() {
  const [params, setParams] = useSearchParams()
  const range = parseRange(params.get('dias'))
  const today = madridDate(useNow())
  const start = addDays(today, -(range - 1))
  const history = useApi((signal) => loadHistory(start, today, signal), [start, today])

  const changeRange = (next: Range) => setParams(next === DEFAULT_RANGE ? {} : { dias: String(next) }, { replace: true })

  return (
    <>
      <PageHeader
        eyebrow="PVPC · Península"
        title="Histórico de precios"
        aside={
          <SegmentedControl
            label="Periodo"
            value={String(range) as `${Range}`}
            onChange={(value) => changeRange(Number(value) as Range)}
            segments={RANGES.map((r) => ({ value: String(r) as `${Range}`, label: `${r} días` }))}
          />
        }
      />
      {history.status === 'loading' && <LoadingState label="Cargando el histórico…" />}
      {history.status === 'error' && <ErrorState error={history.error} onRetry={history.reload} />}
      {history.status === 'success' && <HistoryContent data={history.data} range={range} />}
    </>
  )
}

function HistoryContent({ data, range }: { data: HistoryData; range: Range }) {
  const days = groupByDay(data.hours)
  if (!days.length) return <p className="card muted">No hay precios en este periodo.</p>
  return (
    <>
      <Summary data={data} range={range} />
      {data.missing.length > 0 && (
        <p className="muted">
          Faltan los precios de {data.missing.length === 1 ? '1 día' : `${data.missing.length} días`} del periodo.
        </p>
      )}
      <DailyChart days={days} />
      <Profile days={days} />
      <section aria-labelledby="mapa" className={`section ${styles.section}`}>
        <div>
          <h2 id="mapa">Mapa de calor: hora × día</h2>
          <p className="muted">Pasa el ratón por una celda para ver el precio exacto.</p>
        </div>
        <Heatmap
          caption={`Precio por día y hora, ${formatPeriod(data.start, data.end)}, en €/kWh`}
          columns={HOURS}
          rows={days.map((d) => ({ key: d.day, label: formatWeekdayDay(d.day), values: d.byHour }))}
          steps={STEPS}
          formatValue={kwh}
        />
      </section>
      <Weekdays days={days} />
    </>
  )
}

function Summary({ data, range }: { data: HistoryData; range: Range }) {
  const stats = periodStats(data.hours, CHEAP_THRESHOLD)
  const when = (h: HourPrice) => `${formatWeekdayDay(h.datetime.slice(0, 10))}, ${madridHour(h.datetime)} h`
  const change = data.previousMean === null ? null : changePct(data.previousMean, stats.mean)

  return (
    <section aria-label="Resumen del periodo" className={styles.kpis}>
      <KpiCard
        label="Precio medio"
        value={formatKwh(stats.mean)}
        unit="€/kWh"
        detail={
          <>
            <span className={styles.block}>{formatPeriod(data.start, data.end)}</span>
            {change === null ? (
              <span className={styles.block}>Sin datos del periodo anterior</span>
            ) : (
              <span className={styles.change} data-up={change > 0 || undefined}>
                {change > 0 ? '▲' : '▼'} {formatPercent(Math.abs(change))} frente a los {range} días anteriores
              </span>
            )}
          </>
        }
      />
      <KpiCard label="Hora más barata" value={formatKwh(stats.min.price)} unit="€/kWh" detail={when(stats.min)} />
      <KpiCard label="Hora más cara" value={formatKwh(stats.max.price)} unit="€/kWh" detail={when(stats.max)} />
      <KpiCard
        label="Horas por debajo de 0,10 €/kWh"
        value={formatNumber(stats.below)}
        detail={`${formatPercent((stats.below / stats.total) * 100)} del periodo`}
      />
    </section>
  )
}

function DailyChart({ days }: { days: DayPrices[] }) {
  return (
    <section aria-labelledby="diario" className={`section ${styles.section}`}>
      <h2 id="diario">Precio diario</h2>
      <LineChart
        ariaLabel="Precio medio de cada día, con el mínimo y el máximo, en €/kWh"
        xLabel="Día"
        labels={days.map((d) => formatShortDay(d.day))}
        series={[{ key: 'media', label: 'Media diaria', color: 'var(--color-chart-line)', values: days.map((d) => d.mean) }]}
        band={{ label: 'Mínimo – máximo', color: 'var(--color-chart-band)', lower: days.map((d) => d.min.price), upper: days.map((d) => d.max.price) }}
        formatTick={(v) => formatKwh(v, 2)}
        formatValue={kwh}
        zeroBased
      />
    </section>
  )
}

function Profile({ days }: { days: DayPrices[] }) {
  const workdays = hourlyProfile(days.filter((d) => !isWeekend(d.day)))
  const weekend = hourlyProfile(days.filter((d) => isWeekend(d.day)))
  const { min, max } = argExtremes(workdays)
  const note =
    min >= 0
      ? `Laborables: lo más barato a las ${pad(min)} h (${kwh(workdays[min] as number)}) y lo más caro a las ${pad(max)} h (${kwh(workdays[max] as number)}).`
      : 'No hay días laborables en el periodo.'

  return (
    <section aria-labelledby="perfil" className={`section ${styles.section}`}>
      <div>
        <h2 id="perfil">Precio medio por hora del día</h2>
        <p className="muted">{note}</p>
      </div>
      <LineChart
        ariaLabel="Precio medio por hora del día en laborables y en fin de semana, en €/kWh"
        labels={HOURS}
        series={[
          { key: 'laborables', label: 'Laborables', color: 'var(--color-chart-line)', values: workdays },
          { key: 'finde', label: 'Fin de semana', color: 'var(--color-forecast-2)', values: weekend, dashed: true },
        ]}
        formatTick={(v) => formatKwh(v, 2)}
        formatValue={kwh}
        zeroBased
      />
    </section>
  )
}

function Weekdays({ days }: { days: DayPrices[] }) {
  const means = weekdayMeans(days)
  const top = Math.max(...means.map((v) => v ?? 0))
  const workdays = means.slice(0, 5).filter((v): v is number => v !== null)
  const weekend = means.slice(5).filter((v): v is number => v !== null)
  const difference = workdays.length && weekend.length ? changePct(mean(workdays), mean(weekend)) : null

  return (
    <section aria-labelledby="semana" className={`section ${styles.section}`}>
      <div>
        <h2 id="semana">Precio medio por día de la semana</h2>
        {difference !== null && (
          <p className="muted">
            El fin de semana la luz sale un {formatPercent(Math.abs(difference))} {difference < 0 ? 'más barata' : 'más cara'} que entre semana.
          </p>
        )}
      </div>
      <dl className={styles.weekdays}>
        {WEEKDAYS.map((name, i) => (
          <div key={name} className={styles.weekday}>
            <dt>{name}</dt>
            <dd className={styles.track} aria-hidden="true">
              {means[i] !== null && (
                <span className={styles.fill} data-weekend={i >= 5 || undefined} style={{ width: `${((means[i] as number) / top) * 100}%` }} />
              )}
            </dd>
            <dd className="num">{means[i] === null ? '—' : kwh(means[i] as number)}</dd>
          </div>
        ))}
      </dl>
    </section>
  )
}
