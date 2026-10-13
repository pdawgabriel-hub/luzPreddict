import { useState } from 'react'
import { getJson, postJson } from '../api/client'
import type { Catalog, Health, Prices, SimulateRequest, Simulation } from '../api/types'
import { HourlyBars } from '../components/charts/HourlyBars'
import { KpiCard } from '../components/KpiCard'
import { NumberInput } from '../components/NumberInput'
import { PageHeader } from '../components/PageHeader'
import { SegmentedControl } from '../components/SegmentedControl'
import { ErrorState, LoadingState } from '../components/States'
import { Stepper } from '../components/Stepper'
import { useApi } from '../hooks/useApi'
import { useNow } from '../hooks/useNow'
import { addDays, madridDate } from '../lib/dates'
import { formatDay, formatHourRange, formatKwh, formatNumber, formatPercent, formatShortDay, madridHour } from '../lib/format'
import styles from './Simulador.module.css'

const CUSTOM = 'personalizado'
type Custom = { name: string; power_kw: number; hours: number }
type SimulationOut = Simulation['simulations'][number]

type Settings = {
  appliance: string // id del catálogo o CUSTOM
  custom: Custom
  day: 'today' | 'tomorrow'
  start: number
  uses: number
  from: number
  until: number
}

const INITIAL: Settings = {
  appliance: 'lavadora',
  custom: { name: 'Mi aparato', power_kw: 2, hours: 2 },
  day: 'today',
  start: 20,
  uses: 4,
  from: 0,
  until: 24,
}

const pad = (hour: number) => `${String(hour).padStart(2, '0')}:00`
const eur = (value: number, decimals = 2) => `${formatNumber(value, decimals)} €`
const kwhPrice = (price: number) => `${formatKwh(price)} €/kWh`

// --- Datos ---

type Result = { prices: Prices; all: Simulation; custom: Simulation | null }

async function simulate(date: string, s: Settings, signal: AbortSignal): Promise<Result> {
  const body: SimulateRequest = { date, start_hour: s.start, from_hour: s.from, to_hour: s.until, uses_per_week: s.uses }
  const [prices, all, custom] = await Promise.all([
    getJson<Prices>('/v1/prices', { date }, signal),
    postJson<Simulation>('/api/tools/simulate', body, signal), // sin aparato: los 5 del catálogo
    s.appliance === CUSTOM ? postJson<Simulation>('/api/tools/simulate', { ...body, appliance: s.custom }, signal) : null,
  ])
  return { prices, all, custom }
}

// --- Página ---

export default function Simulador() {
  const today = madridDate(useNow())
  const tomorrow = addDays(today, 1)
  const catalog = useApi((signal) => getJson<Catalog>('/api/tools/catalog', undefined, signal), [])
  const health = useApi((signal) => getJson<Health>('/health', undefined, signal), [])
  const [settings, setSettings] = useState<Settings | null>(null)

  // Hasta saber si REE ya publicó mañana no se elige el día por defecto
  const tomorrowPublished = health.status === 'success' && (health.data.prices.last_day ?? '') >= tomorrow
  const ready = health.status !== 'loading'
  const current = settings ?? { ...INITIAL, day: tomorrowPublished ? 'tomorrow' : 'today' }
  const update = (change: Partial<Settings>) => setSettings({ ...current, ...change })
  const date = current.day === 'tomorrow' && tomorrowPublished ? tomorrow : today

  return (
    <>
      <PageHeader eyebrow="Simulador" title="¿Cuándo me sale más barato?">
        Elige un aparato y a qué hora piensas usarlo. Te decimos cuánto cuesta y cuánto ahorrarías moviéndolo a la mejor hora.
      </PageHeader>
      {catalog.status === 'error' && <ErrorState error={catalog.error} onRetry={catalog.reload} />}
      {(catalog.status === 'loading' || !ready) && <LoadingState label="Cargando los aparatos…" />}
      {catalog.status === 'success' && ready && (
        <SimulatorBody
          catalog={catalog.data}
          settings={current}
          update={update}
          date={date}
          today={today}
          tomorrow={tomorrow}
          tomorrowPublished={tomorrowPublished}
        />
      )}
    </>
  )
}

type BodyProps = {
  catalog: Catalog
  settings: Settings
  update: (change: Partial<Settings>) => void
  date: string
  today: string
  tomorrow: string
  tomorrowPublished: boolean
}

function SimulatorBody({ catalog, settings, update, date, today, tomorrow, tomorrowPublished }: BodyProps) {
  const result = useApi((signal) => simulate(date, settings, signal), [date, settings])
  const data = result.status === 'success' ? result.data : result.status === 'loading' ? result.previous : undefined

  return (
    <>
      <div className={styles.columns}>
        <Form catalog={catalog} settings={settings} update={update} today={today} tomorrow={tomorrow} tomorrowPublished={tomorrowPublished} />
        <section aria-labelledby="resultado" className={`section ${styles.result}`} aria-busy={result.status === 'loading'}>
          <h2 id="resultado">Resultado</h2>
          {result.status === 'error' && <ErrorState error={result.error} onRetry={result.reload} />}
          {!data && result.status === 'loading' && <LoadingState label="Calculando…" />}
          {data && <Outcome data={data} settings={settings} update={update} date={date} busy={result.status === 'loading'} />}
        </section>
      </div>
      {data && <Comparison data={data} settings={settings} date={date} isTomorrow={date === tomorrow} />}
    </>
  )
}

function Form({ catalog, settings, update, today, tomorrow, tomorrowPublished }: Omit<BodyProps, 'date'>) {
  const appliances = [...catalog.appliances, { id: CUSTOM, name: 'Otro aparato', power_kw: settings.custom.power_kw, hours: settings.custom.hours, kwh: settings.custom.power_kw * settings.custom.hours }]
  const program = settings.appliance === CUSTOM ? settings.custom.hours : (catalog.appliances.find((a) => a.id === settings.appliance)?.hours ?? 1)

  return (
    <section aria-labelledby="consumo" className={`section ${styles.form}`}>
      <h2 id="consumo">Tu consumo</h2>
      <fieldset className={styles.fieldset}>
        <legend>Aparato</legend>
        <div className={styles.appliances}>
          {appliances.map((a) => (
            <button key={a.id} type="button" className={styles.appliance} aria-pressed={a.id === settings.appliance} onClick={() => update({ appliance: a.id })}>
              <span className={styles.applianceName}>{a.name}</span>
              <span className={styles.applianceDetail}>
                {formatNumber(a.kwh, 1)} kWh · {a.hours} h
              </span>
            </button>
          ))}
        </div>
      </fieldset>

      {settings.appliance === CUSTOM && (
        <div className={styles.custom}>
          <NumberInput label="Potencia (kW)" unit="kW" value={settings.custom.power_kw} min={0.1} max={15} onChange={(power_kw) => update({ custom: { ...settings.custom, power_kw } })} />
          <Stepper label="Duración (h)" value={settings.custom.hours} min={1} max={12} onChange={(hours) => update({ custom: { ...settings.custom, hours } })} />
        </div>
      )}

      <div className={styles.field}>
        <span className={styles.label}>Día</span>
        <SegmentedControl
          label="Día"
          value={settings.day}
          onChange={(day) => update({ day })}
          segments={[
            { value: 'today', label: `Hoy · ${formatShortDay(today)}` },
            { value: 'tomorrow', label: tomorrowPublished ? `Mañana · ${formatShortDay(tomorrow)}` : 'Mañana', disabled: !tomorrowPublished },
          ]}
        />
        {!tomorrowPublished && <p className={styles.hint}>Mañana se podrá simular cuando REE publique sus precios, hacia las 20:15.</p>}
      </div>

      <div className={styles.pair}>
        <Stepper label="Hora de inicio" value={settings.start} min={0} max={23} format={pad} onChange={(start) => update({ start })} decrementLabel="Una hora antes" incrementLabel="Una hora después" />
        <Stepper label="Usos por semana" value={settings.uses} min={1} max={14} onChange={(uses) => update({ uses })} />
      </div>
      <div className={styles.pair}>
        <Stepper label="Disponible desde" value={settings.from} min={0} max={settings.until - 1} format={pad} onChange={(from) => update({ from })} decrementLabel="Una hora antes" incrementLabel="Una hora después" />
        <Stepper label="Tiene que acabar antes de" value={settings.until} min={settings.from + 1} max={24} format={pad} onChange={(until) => update({ until })} decrementLabel="Una hora antes" incrementLabel="Una hora después" />
      </div>
      {settings.until - settings.from < program && (
        <p role="alert" className={styles.alert}>
          La franja es más corta que el programa ({program} h). Amplíala para buscar la mejor hora.
        </p>
      )}
      <p className={styles.hint}>Consumos típicos orientativos: cada aparato real consume distinto.</p>
    </section>
  )
}

function selectedSimulation(data: Result, settings: Settings): SimulationOut | undefined {
  if (settings.appliance === CUSTOM) return data.custom?.simulations[0]
  return data.all.simulations.find((s) => s.appliance.id === settings.appliance)
}

function Outcome({ data, settings, update, date, busy }: { data: Result; settings: Settings; update: (c: Partial<Settings>) => void; date: string; busy: boolean }) {
  const sim = selectedSimulation(data, settings)
  if (!sim) return null
  const hours = sim.appliance.hours
  const saving = sim.saving_per_use ?? 0
  const chosenStart = Date.parse(sim.start)
  const bestStart = sim.best ? Date.parse(sim.best.start) : null
  const inWindow = (iso: string, start: number | null) => start !== null && Date.parse(iso) >= start && Date.parse(iso) < start + hours * 3_600_000
  const from = settings.from
  const until = settings.until

  return (
    <div className={styles.outcome} data-busy={busy || undefined}>
      <div className={styles.kpis}>
        <KpiCard dark label={`Tu elección · ${formatHourRange(sim.start, hours)}`} value={eur(sim.cost)} detail={`${formatNumber(sim.appliance.kwh, 1)} kWh`} />
        <KpiCard
          label={`Mejor hora · ${sim.best ? formatHourRange(sim.best.start, hours) : 'sin hueco en tu franja'}`}
          value={sim.best_cost === null ? '—' : eur(sim.best_cost)}
          detail={saving > 0.005 ? `Ahorras ${eur(saving)} esta vez` : 'Ya estás en la mejor hora'}
        />
        <KpiCard
          label="Ahorro estimado al año"
          value={eur(sim.yearly_saving ?? 0, 0)}
          detail={`${formatPercent(sim.cost > 0 ? (saving / sim.cost) * 100 : 0)} menos cada vez · ${settings.uses} usos por semana`}
        />
      </div>

      <div className={styles.chartHead}>
        <h3>
          Precios del {formatDay(date)}, {sim.appliance.name.toLowerCase()}
        </h3>
        {sim.best && bestStart !== chosenStart && (
          <button type="button" className={styles.useBest} onClick={() => update({ start: madridHour(sim.best!.start) })}>
            Usar la mejor hora
          </button>
        )}
      </div>
      <HourlyBars
        ariaLabel={`Precio por horas del ${formatDay(date)}, con tu horario y el mejor`}
        valueLabel="Precio"
        formatTick={(v) => formatKwh(v, 2)}
        height={200}
        selectedIndex={data.prices.hours.findIndex((h) => Date.parse(h.datetime) === chosenStart)}
        onSelect={(i) => update({ start: madridHour(data.prices.hours[i].datetime) })}
        bars={data.prices.hours.map((h) => {
          const hour = madridHour(h.datetime)
          const color = inWindow(h.datetime, chosenStart)
            ? 'var(--color-inverse)'
            : inWindow(h.datetime, bestStart)
              ? 'var(--color-forecast-2)'
              : hour >= from && hour < until
                ? 'var(--color-text-inverse-muted)'
                : 'var(--color-surface-sunken)'
          return {
            key: h.datetime,
            label: String(hour).padStart(2, '0'),
            name: `Empezar a las ${pad(hour)}`,
            value: h.price,
            display: kwhPrice(h.price) + (hour >= from && hour < until ? '' : ', fuera de tu franja'),
            color,
          }
        })}
        legend={[
          { label: 'Tu horario', color: 'var(--color-inverse)' },
          { label: 'Mejor horario', color: 'var(--color-forecast-2)' },
          { label: 'Resto de horas', color: 'var(--color-text-inverse-muted)' },
          { label: 'Fuera de tu franja', color: 'var(--color-surface-sunken)' },
        ]}
      />
      <p className={styles.hint}>Pulsa una barra para empezar a esa hora.</p>
    </div>
  )
}

function Comparison({ data, settings, date, isTomorrow }: { data: Result; settings: Settings; date: string; isTomorrow: boolean }) {
  return (
    <section aria-labelledby="todos" className={`section ${styles.comparison}`}>
      <div>
        <h2 id="todos">Todos tus aparatos</h2>
        <p className="muted">
          Empezando a las {pad(settings.start)}, {settings.uses} veces por semana, con los precios de {isTomorrow ? 'mañana' : 'hoy'} (
          {formatShortDay(date)}) y tu franja de {pad(settings.from)} a {pad(settings.until)}.
        </p>
      </div>
      <div className={styles.tableScroll}>
        <table className={styles.table} aria-labelledby="todos">
          <thead>
            <tr>
              <th scope="col">Aparato</th>
              <th scope="col">A tu hora</th>
              <th scope="col">Mejor hora</th>
              <th scope="col">Coste</th>
              <th scope="col">Ahorro al año</th>
            </tr>
          </thead>
          <tbody>
            {data.all.simulations.map((s) => (
              <tr key={s.appliance.id} data-selected={s.appliance.id === settings.appliance || undefined}>
                <th scope="row">{s.appliance.name}</th>
                <td className="num">{eur(s.cost)}</td>
                <td>{s.best ? formatHourRange(s.best.start, s.appliance.hours) : 'No cabe en tu franja'}</td>
                <td className="num">{eur(s.best_cost ?? s.cost)}</td>
                <td className="num">{eur(s.yearly_saving ?? 0, 0)}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <th scope="row" colSpan={4}>
                Total si los mueves todos
              </th>
              <td className="num">{eur(data.all.total_yearly_saving, 0)}</td>
            </tr>
          </tfoot>
        </table>
      </div>
      <p className={styles.hint}>El ahorro anual se estima con los precios del día elegido. Solo término de energía, sin potencia ni impuestos.</p>
    </section>
  )
}
