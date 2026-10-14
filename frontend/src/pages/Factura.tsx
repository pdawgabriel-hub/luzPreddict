import { useId, useState } from 'react'
import { getJson, postJson } from '../api/client'
import type { Bill, BillRequest, Catalog } from '../api/types'
import { HourlyBars } from '../components/charts/HourlyBars'
import { KpiCard } from '../components/KpiCard'
import { NumberInput } from '../components/NumberInput'
import { PageHeader } from '../components/PageHeader'
import { ErrorState, LoadingState } from '../components/States'
import { Stepper } from '../components/Stepper'
import { useApi } from '../hooks/useApi'
import { formatDay, formatNumber, formatPercent, formatPeriod, formatShortDay, plural } from '../lib/format'
import styles from './Factura.module.css'

type Settings = { kwh: number; profile: string; fixed: number; shift: number }

const INITIAL: Settings = { kwh: 250, profile: 'tipico', fixed: 0.15, shift: 0 }
const KWH_STEP = 10
const PERIOD_NAMES = { punta: 'Punta', llano: 'Llano', valle: 'Valle' } as const
const PERIOD_COLORS = { punta: 'var(--color-period-punta)', llano: 'var(--color-period-llano)', valle: 'var(--color-period-valle)' } as const

const eur = (value: number, decimals = 2) => `${formatNumber(value, decimals)} €`
const perKwh = (value: number) => `${formatNumber(value, 3)} €/kWh`

function billRequest(s: Settings): BillRequest {
  return { total_kwh: s.kwh, profile: s.profile, fixed_price: s.fixed, shift_fraction: s.shift / 100 }
}

// --- Página ---

export default function Factura() {
  const catalog = useApi((signal) => getJson<Catalog>('/api/tools/catalog', undefined, signal), [])
  const [settings, setSettings] = useState(INITIAL)
  const update = (change: Partial<Settings>) => setSettings({ ...settings, ...change })

  return (
    <>
      <PageHeader eyebrow="Factura" title="¿Me compensa el PVPC o un precio fijo?">
        Calculamos lo que habrías pagado en energía durante los últimos 30 días con los precios reales del PVPC y lo comparamos con
        el precio fijo de tu contrato.
      </PageHeader>
      {catalog.status === 'loading' && <LoadingState label="Cargando los perfiles de consumo…" />}
      {catalog.status === 'error' && <ErrorState error={catalog.error} onRetry={catalog.reload} />}
      {catalog.status === 'success' && (
        <div className={styles.columns}>
          <Form catalog={catalog.data} settings={settings} update={update} />
          <Result settings={settings} />
        </div>
      )}
    </>
  )
}

function Form({ catalog, settings, update }: { catalog: Catalog; settings: Settings; update: (c: Partial<Settings>) => void }) {
  const shiftId = useId()
  return (
    <section aria-labelledby="datos" className={`section ${styles.form}`}>
      <h2 id="datos">Tus datos</h2>
      <div className={styles.field}>
        <Stepper
          label="Consumo al mes"
          value={settings.kwh / KWH_STEP}
          min={5}
          max={200}
          format={(v) => `${formatNumber(v * KWH_STEP)} kWh`}
          onChange={(v) => update({ kwh: v * KWH_STEP })}
          decrementLabel="Menos consumo"
          incrementLabel="Más consumo"
        />
        <span className={styles.hint}>Lo encontrarás en tu factura, en el apartado de consumo.</span>
      </div>

      <fieldset className={styles.fieldset}>
        <legend>¿Cuándo consumes?</legend>
        <div className={styles.profiles}>
          {catalog.profiles.map((p) => (
            <button key={p.id} type="button" className={styles.profile} aria-pressed={p.id === settings.profile} onClick={() => update({ profile: p.id })}>
              <span className={styles.profileName}>{p.name}</span>
              <span className={styles.profileDetail}>{p.description}</span>
            </button>
          ))}
        </div>
      </fieldset>

      <NumberInput
        label="Precio fijo de tu contrato (€/kWh)"
        unit="€/kWh"
        value={settings.fixed}
        min={0.01}
        max={1}
        decimals={3}
        hint="Solo el término de energía, sin potencia ni impuestos."
        onChange={(fixed) => update({ fixed })}
      />

      <div className={styles.field}>
        <div className={styles.rangeHead}>
          <label htmlFor={shiftId}>Consumo que puedo mover a horas baratas</label>
          <output htmlFor={shiftId} className="num">
            {formatPercent(settings.shift)}
          </output>
        </div>
        <input
          id={shiftId}
          type="range"
          min={0}
          max={40}
          step={5}
          value={settings.shift}
          onChange={(event) => update({ shift: Number(event.target.value) })}
          className={styles.range}
        />
        <span className={styles.hint}>Lavadora, lavavajillas, coche… lo que puedes programar.</span>
      </div>
    </section>
  )
}

function Result({ settings }: { settings: Settings }) {
  const bill = useApi((signal) => postJson<Bill>('/api/tools/bill', billRequest(settings), signal), [settings])
  const data = bill.status === 'success' ? bill.data : bill.status === 'loading' ? bill.previous : undefined

  return (
    <section aria-labelledby="resultado" className={`section ${styles.result}`} aria-busy={bill.status === 'loading'}>
      <h2 id="resultado">Resultado</h2>
      {bill.status === 'error' && <ErrorState error={bill.error} onRetry={bill.reload} />}
      {!data && bill.status === 'loading' && <LoadingState label="Calculando la factura…" />}
      {data && <Outcome bill={data} settings={settings} busy={bill.status === 'loading'} />}
    </section>
  )
}

function Outcome({ bill, settings, busy }: { bill: Bill; settings: Settings; busy: boolean }) {
  const days = bill.days.length
  const fixedCost = bill.fixed_cost ?? 0
  const pvpcBest = Math.min(bill.pvpc_cost, bill.pvpc_shifted_cost)
  const pvpcWins = (bill.fixed_saving ?? 0) > 0
  const difference = Math.abs(fixedCost - pvpcBest)
  const options = [
    { name: 'PVPC', sub: `${perKwh(bill.effective_price)} efectivo`, cost: bill.pvpc_cost, color: 'var(--color-accent)' },
    { name: 'PVPC moviendo consumo', sub: `${formatPercent(settings.shift)} a las 4 horas más baratas`, cost: bill.pvpc_shifted_cost, color: 'var(--color-chart-positive)' },
    { name: 'Tu precio fijo', sub: perKwh(settings.fixed), cost: fixedCost, color: 'var(--color-chart-neutral)' },
  ]
  const top = Math.max(...options.map((o) => o.cost))
  const best = Math.min(...options.map((o) => o.cost))
  const priciest = [...bill.days].sort((a, b) => b.pvpc_cost - a.pvpc_cost)[0]
  const fixedDay = bill.days[0]?.fixed_cost ?? 0

  return (
    <div className={styles.outcome} data-busy={busy || undefined}>
      <div className={styles.verdict} data-pvpc={pvpcWins || undefined} role="status">
        <span className={styles.kicker}>En los últimos {days} días</span>
        <span className={styles.verdictTitle}>{pvpcWins ? 'Te compensa el PVPC' : 'Te compensa el precio fijo'}</span>
        <span>
          Con el PVPC{settings.shift > 0 ? ' y moviendo consumo' : ''} habrías pagado {eur(difference)} {pvpcWins ? 'menos' : 'más'} que con tu
          precio fijo de {perKwh(settings.fixed)}.
        </span>
      </div>

      <div>
        <h3>Coste de la energía, últimos {days} días</h3>
        <dl className={styles.options}>
          {options.map((o) => (
            <div key={o.name} data-best={o.cost === best || undefined}>
              <dt>
                {o.name}
                <span className={styles.sub}>{o.sub}</span>
              </dt>
              <dd className={styles.track} aria-hidden="true">
                <span style={{ width: `${(o.cost / top) * 100}%`, background: o.color }} />
              </dd>
              <dd className="num">{eur(o.cost)}</dd>
            </div>
          ))}
        </dl>
      </div>

      <div className={styles.kpis}>
        <KpiCard label="Precio de equilibrio" value={formatNumber(bill.break_even_price, 3)} unit="€/kWh" detail="Un precio fijo solo te compensa por debajo de esta cifra." />
        <KpiCard label="Día más caro con PVPC" value={eur(priciest.pvpc_cost)} detail={`El ${formatDay(priciest.date)}`} />
        <KpiCard label="Días en que el fijo salió mejor" value={formatNumber(bill.days_fixed_was_cheaper ?? 0)} unit={`de ${days}`} detail="Sin mover consumo" />
      </div>

      <div className={styles.block}>
        <h3>Coste de cada día</h3>
        <HourlyBars
          ariaLabel="Coste de cada día con PVPC frente a tu precio fijo"
          categoryLabel="Día"
          valueLabel="Coste con PVPC"
          formatTick={(v) => formatNumber(v, 2)}
          height={180}
          threshold={{ value: fixedDay, label: `Tu fijo: ${eur(fixedDay)}/día` }}
          bars={bill.days.map((d) => ({
            key: d.date,
            label: formatShortDay(d.date),
            name: formatDay(d.date),
            value: d.pvpc_cost,
            display: `${eur(d.pvpc_cost)} con PVPC, ${eur(d.fixed_cost ?? 0)} con tu fijo`,
            color: d.pvpc_cost <= fixedDay ? 'var(--color-accent)' : 'var(--color-period-punta)',
          }))}
          legend={[
            { label: 'PVPC más barato que tu fijo', color: 'var(--color-accent)' },
            { label: 'PVPC más caro', color: 'var(--color-period-punta)' },
          ]}
        />
      </div>

      <div className={styles.block}>
        <div>
          <h3>Por tramos de la tarifa 2.0TD</h3>
          <p className={styles.hint}>Punta: 10–14 h y 18–22 h. Llano: 8–10 h, 14–18 h y 22–24 h. Valle: 0–8 h, fines de semana y festivos.</p>
        </div>
        <div className={styles.tableScroll}>
          <table className={styles.table} aria-label="Coste por tramos de la tarifa 2.0TD">
            <thead>
              <tr>
                <th scope="col">Tramo</th>
                <th scope="col">Consumo</th>
                <th scope="col">Precio medio</th>
                <th scope="col">Coste</th>
              </tr>
            </thead>
            <tbody>
              {bill.periods.map((p) => (
                <tr key={p.period}>
                  <th scope="row">
                    <span className={styles.swatch} style={{ background: PERIOD_COLORS[p.period] }} aria-hidden="true" />
                    {PERIOD_NAMES[p.period]}
                  </th>
                  <td className="num">
                    {formatNumber(p.kwh)} kWh · {formatPercent((p.kwh / bill.total_kwh) * 100)}
                  </td>
                  <td className="num">{p.avg_price === null ? '—' : perKwh(p.avg_price)}</td>
                  <td className="num">{eur(p.cost)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <p className={styles.hint}>
        Perfiles de consumo aproximados. Precios PVPC reales {formatPeriod(bill.start, bill.end)}
        {bill.missing_days.length > 0 &&
          ` (${bill.missing_days.length === 1 ? 'falta' : 'faltan'} ${plural(bill.missing_days.length, 'día')}, el consumo se reparte entre el resto)`}. {bill.note}
      </p>
    </div>
  )
}
