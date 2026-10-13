import { useState } from 'react'
import { getJson } from '../api/client'
import type { History, Market } from '../api/types'
import { HourlyBars } from '../components/charts/HourlyBars'
import { LineChart } from '../components/charts/LineChart'
import { KpiCard } from '../components/KpiCard'
import { PageHeader } from '../components/PageHeader'
import { SegmentedControl } from '../components/SegmentedControl'
import { ErrorState, LoadingState } from '../components/States'
import { useApi } from '../hooks/useApi'
import { formatDay, formatKwh, formatMwh, formatNumber, formatPercent, formatShortDay } from '../lib/format'
import { GROUPS, groupShares, pearson, quartileComparison, strength } from '../lib/market'
import { changePct } from '../lib/prices'
import styles from './Mercado.module.css'

// --- Datos ---

type MarketDay = { day: string; renewable: number; shares: Record<string, number>; price: number }

type MarketData = {
  days: MarketDay[] // días completos con mix y precio
  lastMix: { day: string; shares: Record<string, number> }
  periodShares: Record<string, number>
  periodRenewable: number
}

async function loadMarket(signal: AbortSignal): Promise<MarketData | null> {
  const [market, history] = await Promise.all([getJson<Market>('/v1/market', undefined, signal), getJson<History>('/v1/history', undefined, signal)])
  const prices = new Map(history.days.map((d) => [d.date, d.avg_price]))
  // El día en curso (provisional) no entra: REE aún lo está actualizando
  const complete = market.days.filter((d) => !d.provisional && d.renewable_pct !== null)
  const days = complete
    .filter((d) => prices.has(d.date))
    .map((d) => ({ day: d.date, renewable: d.renewable_pct as number, shares: groupShares(d.mix), price: prices.get(d.date) as number }))
  const last = complete[complete.length - 1]
  if (!last) return null

  const totals: Record<string, number> = {}
  for (const d of complete) for (const [tech, mwh] of Object.entries(d.mix)) totals[tech] = (totals[tech] ?? 0) + mwh
  const periodShares = groupShares(totals)
  return {
    days,
    lastMix: { day: last.date, shares: groupShares(last.mix) },
    periodShares,
    periodRenewable: GROUPS.filter((g) => g.renewable).reduce((a, g) => a + periodShares[g.name], 0),
  }
}

const RENEWABLES = 'Renovables'
const kwh = (price: number) => `${formatKwh(price)} €/kWh`
const pct = (value: number) => formatPercent(value, 1)
const signed = (r: number) => formatNumber(r, 2).replace('-', '−')

function seriesFor(tech: string, days: MarketDay[]): number[] {
  return days.map((d) => (tech === RENEWABLES ? d.renewable : d.shares[tech]))
}

function colorFor(tech: string): string {
  return tech === RENEWABLES ? 'var(--color-tech-solar)' : (GROUPS.find((g) => g.name === tech)?.color ?? 'var(--color-tech-other)')
}

// --- Página ---

export default function Mercado() {
  const market = useApi(loadMarket, [])

  return (
    <>
      <PageHeader eyebrow="Mercado · Sistema eléctrico nacional" title="¿De dónde viene la luz?">
        Generación por tecnología según REE y su relación con el precio. Cuanta más eólica y solar, menos falta el gas, que es lo que
        suele marcar los precios altos.
      </PageHeader>
      {market.status === 'loading' && <LoadingState label="Cargando el mix de generación…" />}
      {market.status === 'error' && <ErrorState error={market.error} onRetry={market.reload} />}
      {market.status === 'success' &&
        (market.data && market.data.days.length >= 4 ? (
          <MarketContent data={market.data} />
        ) : (
          <p className="card muted">Todavía no hay suficientes días con mix y precio para comparar.</p>
        ))}
    </>
  )
}

function MarketContent({ data }: { data: MarketData }) {
  return (
    <>
      <Summary data={data} />
      <Mix data={data} />
      <TechAndPrice days={data.days} />
      <Correlations days={data.days} />
      <Quartiles days={data.days} />
    </>
  )
}

function Summary({ data }: { data: MarketData }) {
  const byRenewable = [...data.days].sort((a, b) => b.renewable - a.renewable)
  const most = byRenewable[0]
  const least = byRenewable[byRenewable.length - 1]
  const { high, low } = quartileComparison(data.days)
  const difference = changePct(low, high)

  return (
    <section aria-label="Resumen" className={styles.kpis}>
      <KpiCard label={`Renovables, últimos ${data.days.length} días`} value={pct(data.periodRenewable)} detail="de toda la generación" />
      <KpiCard label="Día más renovable" value={pct(most.renewable)} detail={formatDay(most.day)} />
      <KpiCard label="Día menos renovable" value={pct(least.renewable)} detail={formatDay(least.day)} />
      <KpiCard
        label="Precio con más renovables"
        value={`${difference < 0 ? '−' : '+'}${formatPercent(Math.abs(difference))}`}
        detail={`${formatMwh(high, 0)} frente a ${formatMwh(low, 0)} €/MWh de media`}
      />
    </section>
  )
}

function Mix({ data }: { data: MarketData }) {
  const [period, setPeriod] = useState<'last' | 'period'>('last')
  const shares = period === 'last' ? data.lastMix.shares : data.periodShares
  const description = GROUPS.map((g) => `${g.name} ${pct(shares[g.name])}`).join(', ')

  return (
    <section aria-labelledby="mix" className={`section ${styles.section}`}>
      <div className={styles.head}>
        <h2 id="mix">Mix de generación</h2>
        <SegmentedControl
          label="Periodo"
          value={period}
          onChange={setPeriod}
          segments={[
            { value: 'last', label: formatShortDay(data.lastMix.day) },
            { value: 'period', label: `Últimos ${data.days.length} días` },
          ]}
        />
      </div>
      <div role="img" aria-label={`Mix de generación: ${description}`} className={styles.stack}>
        {GROUPS.map((g) => (
          <span key={g.name} style={{ flexGrow: shares[g.name], background: g.color }} />
        ))}
      </div>
      <ul className={styles.mixList}>
        {GROUPS.map((g) => (
          <li key={g.name}>
            <span className={styles.swatch} style={{ background: g.color }} aria-hidden="true" />
            {g.name}
            <span className="num">{pct(shares[g.name])}</span>
          </li>
        ))}
      </ul>
      <p className="muted">Tonos verdes y azules: renovables. Grises y ámbar: no renovables.</p>
    </section>
  )
}

function TechAndPrice({ days }: { days: MarketDay[] }) {
  const [tech, setTech] = useState(RENEWABLES)
  const [selected, setSelected] = useState(days.length - 1)
  const series = seriesFor(tech, days)
  const r = pearson(series, days.map((d) => d.price))
  const subject = tech === RENEWABLES ? 'hay más renovable' : `pesa más ${tech.toLowerCase()}`
  const name = tech === RENEWABLES ? 'renovables' : tech.toLowerCase()
  const day = days[selected]
  const labels = days.map((d) => formatShortDay(d.day))

  return (
    <section aria-labelledby="tecnologia" className={`section ${styles.section}`}>
      <div>
        <h2 id="tecnologia">{tech} y precio, día a día</h2>
        {r !== null && (
          <p className="muted">
            Correlación {signed(r)} ({strength(r)}): cuando {subject}, el precio tiende a {r < 0 ? 'bajar' : 'subir'}.
          </p>
        )}
      </div>
      <div role="group" aria-label="Tecnología" className={styles.chips}>
        {[RENEWABLES, ...GROUPS.map((g) => g.name)].map((name) => (
          <button key={name} type="button" className={styles.chip} aria-pressed={name === tech} onClick={() => setTech(name)}>
            <span className={styles.dot} style={{ background: colorFor(name) }} aria-hidden="true" />
            {name}
          </button>
        ))}
      </div>
      <p className={styles.dayDetail} aria-live="polite">
        {formatDay(day.day)} · {pct(series[selected])} {name} · {kwh(day.price)}
      </p>
      <HourlyBars
        ariaLabel={`% de ${name} en el mix cada día`}
        categoryLabel="Día"
        valueLabel={`% de ${name}`}
        formatTick={(v) => formatPercent(v)}
        height={180}
        selectedIndex={selected}
        onSelect={setSelected}
        bars={days.map((d, i) => ({
          key: d.day,
          label: labels[i],
          name: formatDay(d.day),
          value: series[i],
          display: `${pct(series[i])}, ${kwh(d.price)}`,
          color: colorFor(tech),
        }))}
      />
      <LineChart
        ariaLabel="Precio medio de cada día, en €/kWh"
        xLabel="Día"
        labels={labels}
        series={[{ key: 'precio', label: 'Precio medio del día, €/kWh', color: 'var(--color-chart-line)', values: days.map((d) => d.price) }]}
        formatTick={(v) => formatKwh(v, 2)}
        formatValue={kwh}
        height={160}
        zeroBased
      />
    </section>
  )
}

function Correlations({ days }: { days: MarketDay[] }) {
  const prices = days.map((d) => d.price)
  const rows = GROUPS.map((g) => ({ group: g, r: pearson(seriesFor(g.name, days), prices) }))
    .filter((row): row is { group: (typeof GROUPS)[number]; r: number } => row.r !== null)
    .sort((a, b) => a.r - b.r)
  if (rows.length < 2) return null
  const lowest = rows[0]
  const highest = rows[rows.length - 1]

  return (
    <section aria-labelledby="correlaciones" className={`section ${styles.section}`}>
      <div>
        <h2 id="correlaciones">¿Qué tecnología va con el precio?</h2>
        <p className="muted">
          Correlación entre el peso de cada tecnología en el mix y el precio medio del día, últimos {days.length} días. Indica qué se
          mueve a la vez, no qué causa qué.
        </p>
      </div>
      <div className={styles.corrAxis} aria-hidden="true">
        <span>← Días más baratos</span>
        <span>Días más caros →</span>
      </div>
      <ul className={styles.corrList}>
        {rows.map(({ group, r }) => (
          <li key={group.name}>
            <span className={styles.corrName}>
              <span className={styles.swatch} style={{ background: group.color }} aria-hidden="true" />
              {group.name}
            </span>
            <span className={styles.corrTrack} aria-hidden="true">
              <span className={styles.corrBar} data-sign={r < 0 ? 'neg' : 'pos'} style={{ width: `${Math.abs(r) * 50}%` }} />
            </span>
            <span className="num">{signed(r)}</span>
          </li>
        ))}
      </ul>
      <p>
        Los días caros coinciden con más {highest.group.name.toLowerCase()} ({signed(highest.r)}); los baratos, con más{' '}
        {lowest.group.name.toLowerCase()} ({signed(lowest.r)}).
      </p>
    </section>
  )
}

function Quartiles({ days }: { days: MarketDay[] }) {
  const { size, high, low } = quartileComparison(days)
  const top = Math.max(high, low)

  return (
    <section aria-labelledby="cuartiles" className={`section ${styles.section}`}>
      <h2 id="cuartiles">Días muy renovables frente a días poco renovables</h2>
      <dl className={styles.quartiles}>
        {[
          { label: `${size} días con más renovables`, value: high, color: 'var(--color-tech-wind)' },
          { label: `${size} días con menos renovables`, value: low, color: 'var(--color-tech-gas)' },
        ].map((row) => (
          <div key={row.label}>
            <dt>{row.label}</dt>
            <dd className={styles.track} aria-hidden="true">
              <span style={{ width: `${(row.value / top) * 100}%`, background: row.color }} />
            </dd>
            <dd className="num">{kwh(row.value)}</dd>
          </div>
        ))}
      </dl>
      <p className="muted">
        Precio medio diario. Cuarto de días con más % renovable frente al cuarto con menos, últimos {days.length} días.
      </p>
    </section>
  )
}
