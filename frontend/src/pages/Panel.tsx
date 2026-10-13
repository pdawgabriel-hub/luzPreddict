import { useState } from 'react'
import { Link } from 'react-router'
import { ApiError, getJson } from '../api/client'
import type { Forecast, Prices } from '../api/types'
import { HourlyBars } from '../components/charts/HourlyBars'
import { LineChart } from '../components/charts/LineChart'
import { KpiCard } from '../components/KpiCard'
import { PageHeader } from '../components/PageHeader'
import { SegmentedControl } from '../components/SegmentedControl'
import { ErrorState, LoadingState } from '../components/States'
import { useApi } from '../hooks/useApi'
import { useNow } from '../hooks/useNow'
import { addDays } from '../lib/dates'
import { formatDay, formatHourRange, formatKwh, formatMwh, formatPercent, formatShortDay, formatTime, madridHour } from '../lib/format'
import {
  TIER_LABELS,
  changePct,
  cheapestHours,
  cheaperHours,
  currentHourIndex,
  mean,
  priciestWindow,
  tierCuts,
  tierOf,
  type HourPrice,
  type Tier,
} from '../lib/prices'
import styles from './Panel.module.css'

// --- Datos ---

type Day = {
  day: string
  kind: 'published' | 'forecast'
  hours: HourPrice[]
  generatedAt?: string
  disclaimer?: string
}

type PanelData = { today: Day; tomorrow: Day | null }

const isNotFound = (error: unknown) => error instanceof ApiError && error.status === 404

/** Mañana: el precio publicado si REE ya lo dio entero; si no, la previsión; si tampoco, nada. */
async function loadTomorrow(day: string, signal: AbortSignal): Promise<Day | null> {
  try {
    const prices = await getJson<Prices>('/v1/prices', { date: day }, signal)
    if (!prices.missing_days.length) return { day, kind: 'published', hours: prices.hours }
  } catch (error) {
    if (!isNotFound(error)) throw error
  }
  try {
    const forecast = await getJson<Forecast>('/v1/forecast', { date: day }, signal)
    return { day, kind: 'forecast', hours: forecast.hours, generatedAt: forecast.generated_at, disclaimer: forecast.disclaimer }
  } catch (error) {
    if (isNotFound(error)) return null
    throw error
  }
}

async function loadPanel(signal: AbortSignal): Promise<PanelData> {
  const today = await getJson<Prices>('/v1/prices', undefined, signal)
  const tomorrow = await loadTomorrow(addDays(today.start, 1), signal)
  return { today: { day: today.start, kind: 'published', hours: today.hours }, tomorrow }
}

// --- Colores de barata / media / cara ---

const TIER_COLORS: Record<Day['kind'], Record<Tier, string>> = {
  published: { cheap: 'var(--color-tier-cheap)', mid: 'var(--color-tier-mid)', high: 'var(--color-tier-high)' },
  forecast: { cheap: 'var(--color-forecast-1)', mid: 'var(--color-forecast-2)', high: 'var(--color-forecast-3)' },
}

const kwh = (price: number) => `${formatKwh(price)} €/kWh`

// --- Página ---

export default function Panel() {
  const panel = useApi(loadPanel, [])
  const now = useNow() // la tarjeta "Ahora" cambia sola al empezar cada hora
  const title = panel.status === 'success' ? `Precio de la luz, ${formatDay(panel.data.today.day)}` : 'Precio de la luz hoy y mañana'

  return (
    <>
      <PageHeader eyebrow="PVPC · Península" title={title} aside="Fuente: Red Eléctrica (REE)" />
      {panel.status === 'loading' && <LoadingState label="Cargando los precios…" />}
      {panel.status === 'error' && <ErrorState error={panel.error} onRetry={panel.reload} />}
      {panel.status === 'success' && <PanelContent data={panel.data} now={now} />}
      <MoreTools />
    </>
  )
}

function PanelContent({ data, now }: { data: PanelData; now: Date }) {
  const { today, tomorrow } = data
  const current = currentHourIndex(today.hours, now)
  return (
    <>
      <Summary today={today} tomorrow={tomorrow} current={current} />
      {current >= 0 && <NextHours today={today} tomorrow={tomorrow} current={current} />}
      <div className={styles.columns}>
        <HourlyPrices today={today} tomorrow={tomorrow} current={current} />
        <BestHours day={tomorrow ?? today} isTomorrow={tomorrow !== null} />
      </div>
    </>
  )
}

function TierBadge({ tier }: { tier: Tier }) {
  return (
    <span className={styles.badge} data-tier={tier}>
      Hora {TIER_LABELS[tier]}
    </span>
  )
}

function Summary({ today, tomorrow, current }: { today: Day; tomorrow: Day | null; current: number }) {
  const prices = today.hours.map((h) => h.price)
  const todayMean = mean(prices)
  const [cheapest] = cheapestHours(today.hours, 1)
  const now = current >= 0 ? today.hours[current] : null
  const tomorrowMean = tomorrow ? mean(tomorrow.hours.map((h) => h.price)) : null
  const change = tomorrowMean === null ? null : changePct(todayMean, tomorrowMean)

  return (
    <section aria-label="Resumen" className={styles.kpis}>
      {now ? (
        <KpiCard
          dark
          label={`Ahora · ${formatHourRange(now.datetime)}`}
          value={formatKwh(now.price)}
          unit="€/kWh"
          badge={<TierBadge tier={tierOf(now.price, tierCuts(prices))} />}
        />
      ) : (
        <KpiCard dark label="Ahora" value="—" detail="No hay precio para esta hora" />
      )}
      <KpiCard label="Media de hoy" value={formatKwh(todayMean)} unit="€/kWh" detail={`${formatMwh(todayMean)} €/MWh`} />
      <KpiCard label="Hora más barata hoy" value={formatHourRange(cheapest.datetime)} detail={kwh(cheapest.price)} />
      {tomorrow && tomorrowMean !== null && change !== null ? (
        <KpiCard
          label={`Mañana (${tomorrow.kind === 'published' ? 'publicado' : 'previsto'})`}
          value={formatKwh(tomorrowMean)}
          unit="€/kWh"
          detail={
            <span className={styles.change} data-up={change > 0 || undefined}>
              {change > 0 ? '▲' : '▼'} {formatPercent(Math.abs(change))} respecto a hoy
            </span>
          }
        />
      ) : (
        <KpiCard label="Mañana" value="—" detail="REE publica los precios hacia las 20:15" />
      )}
    </section>
  )
}

function NextHours({ today, tomorrow, current }: { today: Day; tomorrow: Day | null; current: number }) {
  const upcoming = [
    ...today.hours.slice(current).map((h) => ({ ...h, kind: today.kind })),
    ...(tomorrow?.hours ?? []).map((h) => ({ ...h, kind: tomorrow!.kind })),
  ].slice(0, 8)
  const cuts = tierCuts([...today.hours, ...(tomorrow?.hours ?? [])].map((h) => h.price))
  const forecastFrom = upcoming.find((h) => h.kind === 'forecast')

  return (
    <section aria-labelledby="proximas" className={`section ${styles.next}`}>
      <div className={styles.sectionHead}>
        <h2 id="proximas">Próximas horas</h2>
        <span className="muted">
          {forecastFrom
            ? `Hasta las ${formatTime(today.hours[today.hours.length - 1].datetime)}, precio publicado; desde las 00:00, previsión`
            : 'Precio publicado por REE'}
        </span>
      </div>
      <ol className={styles.nextList}>
        {upcoming.map((h, i) => {
          const tier = tierOf(h.price, cuts)
          return (
            <li key={h.datetime} className={styles.nextItem} data-tier={tier} data-now={i === 0 || undefined}>
              <span className="num">
                {i === 0 && 'Ahora · '}
                {formatTime(h.datetime)}
              </span>
              <span className={`num ${styles.nextPrice}`}>{formatKwh(h.price)}</span>
              <span className={styles.nextKind}>
                {h.kind === 'forecast' && 'previsión · '}
                {TIER_LABELS[tier]}
              </span>
            </li>
          )
        })}
      </ol>
    </section>
  )
}

type Tab = 'today' | 'tomorrow' | 'compare'

function HourlyPrices({ today, tomorrow, current }: { today: Day; tomorrow: Day | null; current: number }) {
  const [tab, setTab] = useState<Tab>('today')
  const [hour, setHour] = useState<number | null>(null)
  const changeTab = (next: Tab) => {
    setTab(next)
    setHour(null)
  }
  const shown = tab === 'tomorrow' && tomorrow ? tomorrow : today

  return (
    <section aria-labelledby="por-horas" className={`section ${styles.hourly}`}>
      <div className={styles.sectionHead}>
        <h2 id="por-horas">Precio por horas</h2>
        <SegmentedControl
          label="Día"
          value={tab}
          onChange={changeTab}
          segments={[
            { value: 'today', label: `Hoy · ${formatShortDay(today.day)}` },
            { value: 'tomorrow', label: tomorrow ? `Mañana · ${formatShortDay(tomorrow.day)}` : 'Mañana', disabled: !tomorrow },
            { value: 'compare', label: 'Comparar', disabled: !tomorrow },
          ]}
        />
      </div>
      {tab === 'compare' && tomorrow ? (
        <Compare today={today} tomorrow={tomorrow} />
      ) : (
        <DayBars day={shown} selected={hour ?? defaultHour(shown, shown === today ? current : -1)} onSelect={setHour} current={shown === today ? current : -1} />
      )}
    </section>
  )
}

/** Hora seleccionada al abrir: la actual en hoy; la más barata en mañana. */
function defaultHour(day: Day, current: number): number {
  if (current >= 0) return current
  const [cheapest] = cheapestHours(day.hours, 1)
  return day.hours.indexOf(cheapest)
}

function DayBars({ day, selected, onSelect, current }: { day: Day; selected: number; onSelect: (i: number) => void; current: number }) {
  const cuts = tierCuts(day.hours.map((h) => h.price))
  const colors = TIER_COLORS[day.kind]
  const forecast = day.kind === 'forecast'
  const hour = day.hours[selected]
  const tier = tierOf(hour.price, cuts)

  return (
    <>
      <p className={styles.selected} aria-live="polite">
        <span className={`num ${styles.selectedHour}`}>{formatHourRange(hour.datetime)}</span>
        <span className="num">{kwh(hour.price)}</span>
        <span className="muted">
          {formatMwh(hour.price)} €/MWh · {forecast ? 'previsión, ' : ''}hora {TIER_LABELS[tier]}
        </span>
      </p>
      <HourlyBars
        ariaLabel={`${forecast ? 'Previsión del precio' : 'Precio'} por horas del ${formatDay(day.day)}, en €/kWh`}
        valueLabel="Precio"
        formatTick={(v) => formatKwh(v, 2)}
        height={260}
        selectedIndex={selected}
        onSelect={onSelect}
        bars={day.hours.map((h, i) => ({
          key: h.datetime,
          label: String(madridHour(h.datetime)).padStart(2, '0'),
          name: formatHourRange(h.datetime),
          value: h.price,
          display: kwh(h.price),
          color: colors[tierOf(h.price, cuts)],
          current: i === current,
        }))}
        legend={(['cheap', 'mid', 'high'] as Tier[]).map((t) => ({ label: TIER_LABELS[t].replace(/^./, (c) => c.toUpperCase()), color: colors[t] }))}
      />
      {forecast && day.disclaimer && <p className={`muted ${styles.note}`}>{day.disclaimer}</p>}
    </>
  )
}

function Compare({ today, tomorrow }: { today: Day; tomorrow: Day }) {
  const length = Math.min(today.hours.length, tomorrow.hours.length)
  const cheaper = cheaperHours(today.hours, tomorrow.hours)
  const label = tomorrow.kind === 'published' ? 'Mañana (publicado)' : 'Mañana (previsión)'

  return (
    <>
      <p className={styles.selected}>
        Mañana sale más barato en {cheaper} de {length} horas.
      </p>
      <LineChart
        ariaLabel={`Precio de hoy frente a ${tomorrow.kind === 'published' ? 'mañana' : 'la previsión de mañana'}, en €/kWh`}
        labels={today.hours.slice(0, length).map((h) => String(madridHour(h.datetime)).padStart(2, '0'))}
        series={[
          { key: 'hoy', label: 'Hoy (publicado)', color: 'var(--color-tier-mid)', values: today.hours.slice(0, length).map((h) => h.price) },
          {
            key: 'manana',
            label,
            color: tomorrow.kind === 'published' ? 'var(--color-tier-high)' : 'var(--color-forecast-2)',
            values: tomorrow.hours.slice(0, length).map((h) => h.price),
            dashed: true,
          },
        ]}
        formatTick={(v) => formatKwh(v, 2)}
        formatValue={kwh}
        height={260}
      />
    </>
  )
}

function BestHours({ day, isTomorrow }: { day: Day; isTomorrow: boolean }) {
  const best = cheapestHours(day.hours, 4)
  const worst = priciestWindow(day.hours, 3)
  const cheapest = best[0].price
  const forecast = day.kind === 'forecast'

  return (
    <aside aria-labelledby="mejores" className={`section ${styles.best}`}>
      <h2 id="mejores">Mejores horas {isTomorrow ? 'mañana' : 'hoy'}</h2>
      <p className="muted">Para la lavadora, el lavavajillas o cargar el coche.</p>
      <ol className={styles.bestList}>
        {best.map((h, i) => (
          <li key={h.datetime}>
            <span className={styles.rank}>{i + 1}</span>
            <span className="num">{formatHourRange(h.datetime)}</span>
            <span className={`num ${styles.bestPrice}`}>{kwh(h.price)}</span>
          </li>
        ))}
      </ol>
      {worst && (
        <p className={styles.avoid}>
          <strong>Evita {formatHourRange(day.hours[worst.start].datetime, 3)}:</strong> {forecast ? 'se prevén' : 'llega a'} hasta {kwh(worst.max)}
          {cheapest > 0 && worst.max / cheapest >= 2 && `, más de ${Math.floor(worst.max / cheapest)} veces la hora más barata`}.
        </p>
      )}
      <Link to="/simulador" className={styles.cta}>
        Calcular cuánto ahorro
      </Link>
    </aside>
  )
}

const TOOLS = [
  { to: '/historico', title: 'Histórico', text: 'Mapa de calor de los últimos 30 días y precio por día de la semana.' },
  { to: '/mercado', title: 'Mercado y renovables', text: 'Mix de generación y cómo influyen eólica y solar en el precio.' },
  { to: '/planificador', title: 'Planificador', text: 'Organiza varios aparatos mañana sin pasarte de potencia.' },
  { to: '/factura', title: '¿PVPC o precio fijo?', text: 'Compara lo que habrías pagado el último mes con cada tarifa.' },
  { to: '/alertas', title: 'Alertas de precio', text: 'Recibe un aviso cuando la luz baje o suba de un umbral.' },
  { to: '/modelo', title: 'Precisión del modelo', text: 'Previsión frente a precio real y error por hora del día.' },
]

function MoreTools() {
  return (
    <section aria-label="Más herramientas" className={styles.tools}>
      {TOOLS.map((tool) => (
        <Link key={tool.to} to={tool.to} className={styles.tool}>
          <strong>{tool.title}</strong>
          <span className="muted">{tool.text}</span>
        </Link>
      ))}
    </section>
  )
}
