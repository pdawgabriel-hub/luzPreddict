import { useState } from 'react'
import { getJson, postJson } from '../api/client'
import type { Catalog, Health, Plan, PlanRequest } from '../api/types'
import { HourlyBars } from '../components/charts/HourlyBars'
import { KpiCard } from '../components/KpiCard'
import { PageHeader } from '../components/PageHeader'
import { SegmentedControl } from '../components/SegmentedControl'
import { ErrorState, LoadingState } from '../components/States'
import { useApi } from '../hooks/useApi'
import { useNow } from '../hooks/useNow'
import { addDays, madridDate } from '../lib/dates'
import { formatDay, formatHourRange, formatKwh, formatNumber, formatPercent, madridHour } from '../lib/format'
import { TIER_LABELS, tierCuts, tierOf, type Tier } from '../lib/prices'
import styles from './Planificador.module.css'

type Task = { id: string; appliance: string; habitual: number; fixed: boolean }
type PlannedTask = Plan['tasks'][number]

// Hora a la que se suele usar cada aparato (se puede cambiar en cada tarea)
const HABITUAL: Record<string, number> = { lavadora: 20, lavavajillas: 22, secadora: 21, horno: 20, coche: 19 }
const INITIAL_TASKS: Task[] = [
  { id: 'coche-1', appliance: 'coche', habitual: 19, fixed: false },
  { id: 'lavadora-1', appliance: 'lavadora', habitual: 20, fixed: false },
  { id: 'lavavajillas-1', appliance: 'lavavajillas', habitual: 22, fixed: false },
  { id: 'horno-1', appliance: 'horno', habitual: 20, fixed: true },
]
const MAX_TASKS = 20
const DEFAULT_POWER = 4.6

const eur = (value: number, decimals = 2) => `${formatNumber(value, decimals)} €`
const kw = (value: number) => `${formatNumber(value, value % 1 ? 2 : 1).replace(/0$/, '')} kW`
const pad = (hour: number) => `${String(hour).padStart(2, '0')}:00`
// Los precios del plan vienen en €/kWh; los colores de barata/media/cara, del mismo día
const TIER_COLORS: Record<Tier, string> = { cheap: 'var(--color-tier-cheap)', mid: 'var(--color-tier-mid)', high: 'var(--color-tier-high)' }

function planRequest(date: string, power: number, tasks: Task[]): PlanRequest {
  return { date, power_kw: power, tasks: tasks.map((t) => ({ id: t.id, appliance: t.appliance, habitual_hour: t.habitual, fixed: t.fixed, from_hour: 0, to_hour: 24 })) }
}

// --- Página ---

export default function Planificador() {
  const today = madridDate(useNow())
  const tomorrow = addDays(today, 1)
  const catalog = useApi((signal) => getJson<Catalog>('/api/tools/catalog', undefined, signal), [])
  const health = useApi((signal) => getJson<Health>('/health', undefined, signal), [])
  const [power, setPower] = useState(DEFAULT_POWER)
  const [tasks, setTasks] = useState(INITIAL_TASKS)
  const [nextId, setNextId] = useState(2)

  // Se planifica mañana si REE ya publicó sus precios; si no, hoy
  const isTomorrow = health.status === 'success' && (health.data.prices.last_day ?? '') >= tomorrow
  const date = isTomorrow ? tomorrow : today
  const ready = catalog.status === 'success' && health.status !== 'loading'

  const add = (appliance: string) => {
    setTasks([...tasks, { id: `${appliance}-${nextId}`, appliance, habitual: HABITUAL[appliance] ?? 20, fixed: false }])
    setNextId(nextId + 1)
  }
  const change = (id: string, patch: Partial<Task>) => setTasks(tasks.map((t) => (t.id === id ? { ...t, ...patch } : t)))
  const remove = (id: string) => setTasks(tasks.filter((t) => t.id !== id))

  return (
    <>
      <PageHeader
        eyebrow={`Planificador · ${isTomorrow ? 'mañana' : 'hoy'}, ${formatDay(date)}`}
        title="Organiza tu día"
        aside={
          catalog.status === 'success' && (
            <div className={styles.power}>
              <span>Potencia contratada</span>
              <SegmentedControl
                label="Potencia contratada"
                value={String(power)}
                onChange={(value) => setPower(Number(value))}
                segments={catalog.data.contracted_powers_kw.map((p) => ({ value: String(p), label: kw(p) }))}
              />
            </div>
          )
        }
      >
        Añade lo que vas a poner y lo colocamos en las horas más baratas, sin superar tu potencia contratada.
        {!isTomorrow && ' Los precios de mañana se publican hacia las 20:15; hasta entonces se planifica hoy.'}
      </PageHeader>
      {catalog.status === 'error' && <ErrorState error={catalog.error} onRetry={catalog.reload} />}
      {!ready && catalog.status !== 'error' && <LoadingState label="Cargando los aparatos…" />}
      {ready && (
        <PlanBody
          catalog={catalog.data}
          date={date}
          power={power}
          tasks={tasks}
          onAdd={add}
          onChange={change}
          onRemove={remove}
        />
      )}
    </>
  )
}

type BodyProps = {
  catalog: Catalog
  date: string
  power: number
  tasks: Task[]
  onAdd: (appliance: string) => void
  onChange: (id: string, patch: Partial<Task>) => void
  onRemove: (id: string) => void
}

function PlanBody({ catalog, date, power, tasks, onAdd, onChange, onRemove }: BodyProps) {
  const plan = useApi(
    (signal) => (tasks.length ? postJson<Plan>('/api/tools/plan', planRequest(date, power, tasks), signal) : Promise.resolve(null)),
    [date, power, tasks],
  )
  const data = plan.status === 'success' ? plan.data : plan.status === 'loading' ? plan.previous : undefined
  const busy = plan.status === 'loading'

  return (
    <>
      {plan.status === 'error' && <ErrorState error={plan.error} onRetry={plan.reload} />}
      {data && <Summary plan={data} />}
      <section aria-labelledby="plan" className={`section ${styles.section}`} aria-busy={busy}>
        <div className={styles.head}>
          <h2 id="plan">Plan del día</h2>
          <div role="group" aria-label="Añadir tarea" className={styles.add}>
            {catalog.appliances.map((a) => (
              <button key={a.id} type="button" onClick={() => onAdd(a.id)} disabled={tasks.length >= MAX_TASKS}>
                + {a.name.replace(/ \(.*\)$/, '')}
              </button>
            ))}
          </div>
        </div>
        {!tasks.length && <p className="muted">Añade una tarea con los botones de arriba.</p>}
        {!data && tasks.length > 0 && <LoadingState label="Calculando el plan…" />}
        {data && tasks.length > 0 && (
          <Grid plan={data} tasks={tasks} catalog={catalog} busy={busy} onChange={onChange} onRemove={onRemove} />
        )}
        <ul className={styles.legend}>
          <li>
            <span className={styles.key} data-kind="plan" aria-hidden="true" />
            Horario del plan
          </li>
          <li>
            <span className={styles.key} data-kind="habitual" aria-hidden="true" />
            Tu hora habitual
          </li>
          <li>
            <span className={styles.key} data-kind="fixed" aria-hidden="true" />
            Tarea fija
          </li>
          <li className="muted">«Fija» = no se mueve de su hora habitual (por ejemplo, el horno a la hora de cenar).</li>
        </ul>
      </section>
      {data && <Load plan={data} power={power} />}
      <p className="muted">Precios publicados por REE. Consumos típicos orientativos. Solo término de energía.</p>
    </>
  )
}

function Summary({ plan }: { plan: Plan }) {
  const placed = plan.tasks.filter((t) => t.placed)
  const habitualPlaced = placed.reduce((a, t) => a + t.habitual_cost, 0)
  const kwh = placed.reduce((a, t) => a + t.appliance.kwh, 0)
  const overloads = plan.habitual_overloads.map((h) => `${madridHour(h)} h`)

  return (
    <section aria-label="Resumen" className={styles.kpis}>
      <KpiCard
        label="A tu hora habitual"
        value={eur(plan.habitual_cost)}
        detail={
          overloads.length ? (
            <span className={styles.danger}>Superarías la potencia a las {overloads.slice(0, 3).join(', ')}: saltaría el limitador</span>
          ) : (
            'Sin pasarte de potencia'
          )
        }
      />
      <KpiCard dark label="Con el plan" value={eur(plan.plan_cost)} detail={`${formatNumber(kwh, 1)} kWh en ${placed.length} de ${plan.tasks.length} tareas`} />
      <KpiCard
        label="Ahorro"
        value={eur(plan.saving)}
        detail={`${formatPercent(habitualPlaced > 0 ? (plan.saving / habitualPlaced) * 100 : 0)} menos · ${eur(plan.saving * 30, 0)} al mes si lo repites`}
      />
    </section>
  )
}

type GridProps = {
  plan: Plan
  tasks: Task[]
  catalog: Catalog
  busy: boolean
  onChange: (id: string, patch: Partial<Task>) => void
  onRemove: (id: string) => void
}

function Grid({ plan, tasks, busy, onChange, onRemove }: GridProps) {
  const hours = plan.hours
  const cuts = tierCuts(hours.map((h) => h.price))
  const byId = new Map(plan.tasks.map((t) => [t.id, t]))
  const columns = { gridTemplateColumns: `minmax(15rem, 18rem) repeat(${hours.length}, minmax(14px, 1fr)) minmax(9rem, 11rem)` }

  return (
    <div className={styles.gridScroll} data-busy={busy || undefined}>
      <div className={styles.grid} style={columns}>
        <span className={styles.rowLabel}>Precio</span>
        {hours.map((h) => {
          const tier = tierOf(h.price, cuts)
          return <span key={h.datetime} className={styles.price} style={{ background: TIER_COLORS[tier] }} title={`${pad(madridHour(h.datetime))}: ${formatKwh(h.price * 1000)} €/kWh, hora ${TIER_LABELS[tier]}`} />
        })}
        <span />
        <span />
        {hours.map((h, i) => (
          <span key={h.datetime} className={styles.hour} aria-hidden="true">
            {madridHour(h.datetime) % 3 === 0 && (i === 0 || madridHour(hours[i - 1].datetime) !== madridHour(h.datetime)) ? String(madridHour(h.datetime)).padStart(2, '0') : ''}
          </span>
        ))}
        <span />
        {tasks.map((task) => {
          const planned = byId.get(task.id)
          return planned ? <TaskRow key={task.id} task={task} planned={planned} hours={hours} onChange={onChange} onRemove={onRemove} /> : null
        })}
      </div>
    </div>
  )
}

function TaskRow({ task, planned, hours, onChange, onRemove }: { task: Task; planned: PlannedTask; hours: Plan['hours']; onChange: GridProps['onChange']; onRemove: GridProps['onRemove'] }) {
  const name = planned.appliance.name.replace(/ \(.*\)$/, '')
  const length = planned.appliance.hours * 3_600_000
  const inside = (iso: string, start: string | null) => start !== null && Date.parse(iso) >= Date.parse(start) && Date.parse(iso) < Date.parse(start) + length

  return (
    <>
      <div className={styles.task}>
        <button type="button" className={styles.remove} aria-label={`Quitar ${name}`} onClick={() => onRemove(task.id)}>
          ×
        </button>
        <span className={styles.taskName}>
          <span>{name}</span>
          <span className={styles.taskDetail}>
            {kw(planned.appliance.power_kw)} · {planned.appliance.hours} h
          </span>
        </span>
        <label className={styles.habitual}>
          <span className="visually-hidden">Hora habitual de {name}</span>
          <select value={task.habitual} onChange={(event) => onChange(task.id, { habitual: Number(event.target.value) })}>
            {Array.from({ length: 24 }, (_, h) => (
              <option key={h} value={h}>
                {pad(h)}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className={styles.pin}
          aria-pressed={task.fixed}
          aria-label={`${name}: ${task.fixed ? 'fija a su hora habitual' : 'flexible, el plan la mueve'}`}
          onClick={() => onChange(task.id, { fixed: !task.fixed })}
        >
          {task.fixed ? 'Fija' : 'Flexible'}
        </button>
      </div>
      {hours.map((h) => (
        <span
          key={h.datetime}
          className={styles.cell}
          aria-hidden="true"
          data-plan={inside(h.datetime, planned.start) ? (task.fixed ? 'fixed' : 'plan') : undefined}
          data-habitual={!task.fixed && inside(h.datetime, planned.habitual_start) ? true : undefined}
        />
      ))}
      <span className={styles.outcome}>
        {planned.placed && planned.start ? (
          <>
            <span className="num">{formatHourRange(planned.start, planned.appliance.hours)}</span>
            <span className={styles.taskDetail}>
              {eur(planned.cost ?? 0)} {task.fixed ? '· a su hora' : `(antes ${eur(planned.habitual_cost)})`}
            </span>
          </>
        ) : (
          <>
            <span className={styles.danger}>No cabe</span>
            <span className={styles.taskDetail}>sube la potencia o quita tareas</span>
          </>
        )}
      </span>
    </>
  )
}

function Load({ plan, power }: { plan: Plan; power: number }) {
  return (
    <section aria-labelledby="carga" className={`section ${styles.section}`}>
      <div>
        <h2 id="carga">Potencia usada cada hora</h2>
        <p className="muted">
          Incluye un consumo base estimado de {kw(plan.base_load_kw)} (nevera, router, aparatos en espera). La línea marca tu potencia
          contratada.
        </p>
      </div>
      <HourlyBars
        ariaLabel="Potencia usada cada hora con el plan, en kW"
        valueLabel="Potencia"
        formatTick={(v) => formatNumber(v, v % 1 ? 1 : 0)}
        height={200}
        threshold={{ value: power, label: `Contratada: ${kw(power)}` }}
        bars={plan.hours.map((h) => ({
          key: h.datetime,
          label: String(madridHour(h.datetime)).padStart(2, '0'),
          name: formatHourRange(h.datetime),
          value: h.kw,
          display: `${formatNumber(h.kw, 1)} kW`,
          color: h.kw > power + 1e-9 ? 'var(--color-danger-text)' : h.kw > plan.base_load_kw + 1e-9 ? 'var(--color-accent)' : 'var(--color-text-inverse-muted)',
        }))}
        legend={[
          { label: 'Con aparatos', color: 'var(--color-accent)' },
          { label: 'Solo consumo base', color: 'var(--color-text-inverse-muted)' },
        ]}
      />
    </section>
  )
}
