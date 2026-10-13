// Datos de ejemplo con la misma forma que la API (tipos generados de su OpenAPI).
// Son inventados pero verosímiles: precios con la curva típica del PVPC (picos de
// mañana y noche, valle solar al mediodía), siempre relativos al día de hoy.

import type {
  ApplianceOut,
  BestHours,
  Bill,
  BillRequest,
  Catalog,
  DaySummary,
  Forecast,
  Health,
  History,
  Market,
  ModelReport,
  Plan,
  PlanRequest,
  PriceHour,
  Prices,
  SimulateRequest,
  Simulation,
  Source,
  TariffPeriod,
} from '../api/types'
import { seeded } from './random'
import { addDays, dayHours, daysBetween, madridDate, madridHour, toMadridIso, weekday } from '../lib/dates'

const HOUR_MS = 3_600_000
const PUBLISH_MINUTES = 20 * 60 + 15 // REE publica mañana hacia las 20:15

const REE = { name: 'Red Eléctrica (REE)', url: 'https://www.ree.es/es/apidatos' }
export const PVPC_SOURCE: Source = { ...REE, series: 'PVPC 2.0TD' }
export const GENERATION_SOURCE: Source = { ...REE, series: 'Estructura de la generación' }
export const FORECAST_DISCLAIMER =
  'Previsión orientativa calculada por luzPreddict con datos de REE: no es un precio oficial ni garantiza el precio final.'

const round = (value: number, decimals = 2) => Math.round(value * 10 ** decimals) / 10 ** decimals
const mean = (values: number[]) => values.reduce((a, b) => a + b, 0) / values.length

// --- Precios ---

// €/MWh típicos por hora de reloj
const CURVE = [105, 98, 94, 92, 93, 100, 118, 142, 155, 132, 98, 72, 58, 50, 48, 55, 74, 112, 168, 205, 218, 196, 160, 128]

export type HourPrice = { instant: Date; price: number }

export function today(now: Date): string {
  return madridDate(now)
}

/** Último día con precios publicados: mañana desde las 20:15, si no, hoy. */
export function lastPublishedDay(now: Date): string {
  const minutes = madridHour(now) * 60 + now.getUTCMinutes()
  return minutes >= PUBLISH_MINUTES ? addDays(today(now), 1) : today(now)
}

/** Precio de cada hora de un día; siempre el mismo para el mismo día. */
export function dayPrices(day: string): HourPrice[] {
  const random = seeded(`precios-${day}`)
  const level = 0.75 + random() * 0.5
  const weekend = weekday(day) >= 5 ? 0.85 : 1
  return dayHours(day).map((instant) => ({
    instant,
    price: round(CURVE[madridHour(instant)] * level * weekend * (0.92 + random() * 0.16)),
  }))
}

export function tariffPeriod(instant: Date): TariffPeriod {
  const hour = madridHour(instant)
  if (weekday(madridDate(instant)) >= 5 || hour < 8) return 'valle'
  if ((hour >= 10 && hour < 14) || (hour >= 18 && hour < 22)) return 'punta'
  return 'llano'
}

function priceHour({ instant, price }: HourPrice): PriceHour {
  return { datetime: toMadridIso(instant), price, period: tariffPeriod(instant) }
}

export function prices(start: string, end: string, lastDay: string): Prices {
  const days = daysBetween(start, end)
  const published = days.filter((day) => day <= lastDay)
  return {
    start,
    end,
    unit: '€/MWh',
    missing_days: days.filter((day) => day > lastDay),
    hours: published.flatMap(dayPrices).map(priceHour),
    source: PVPC_SOURCE,
  }
}

// --- Previsión ---

function forecastPrices(day: string): number[] {
  const random = seeded(`prevision-${day}`)
  return dayPrices(day).map(({ price }) => round(price * (0.88 + random() * 0.24)))
}

function dailyMae(day: string): number {
  const actual = dayPrices(day)
  return round(mean(forecastPrices(day).map((p, i) => Math.abs(p - actual[i].price))))
}

export function forecast(day: string, lastDay: string, now: Date): Forecast {
  const predicted = forecastPrices(day)
  const actual = day <= lastDay ? dayPrices(day) : null
  return {
    date: day,
    generated_at: toMadridIso(new Date(now.getTime() - HOUR_MS / 2)),
    model: 'lightgbm',
    model_version: MODEL_VERSION,
    fallback_reason: null,
    unit: '€/MWh',
    mae: actual ? dailyMae(day) : null,
    hours: dayHours(day).map((instant, i) => ({
      datetime: toMadridIso(instant),
      price: predicted[i],
      period: tariffPeriod(instant),
      actual: actual ? actual[i].price : null,
    })),
    source: PVPC_SOURCE,
    disclaimer: FORECAST_DISCLAIMER,
  }
}

// --- Mejores horas ---

type Window = { start: number; hours: number; avg: number }

/** Las `hours` horas seguidas más baratas entre los índices [from, to). */
function bestWindow(values: number[], hours: number, from = 0, to = values.length): Window | null {
  let best: Window | null = null
  for (let start = from; start + hours <= to; start++) {
    const avg = mean(values.slice(start, start + hours))
    if (!best || avg < best.avg - 1e-9) best = { start, hours, avg }
  }
  return best
}

/** Índice de la primera hora del día que empieza en la hora de reloj `hour` o después (24: fin del día). */
function hourIndex(hours: Date[], hour: number): number {
  const index = hours.findIndex((instant) => madridHour(instant) >= hour)
  return hour >= 24 || index === -1 ? hours.length : index
}

export function bestHours(day: string, hours: number, fromHour: number, toHour: number): BestHours | null {
  const rows = dayPrices(day)
  const instants = rows.map((r) => r.instant)
  const from = hourIndex(instants, fromHour)
  const to = hourIndex(instants, toHour)
  const window = bestWindow(
    rows.map((r) => r.price),
    hours,
    from,
    to,
  )
  if (!window) return null
  const dayAvg = mean(rows.map((r) => r.price))
  const cheapest = rows
    .slice(from, to)
    .sort((a, b) => a.price - b.price || a.instant.getTime() - b.instant.getTime())
    .slice(0, hours)
  return {
    date: day,
    hours,
    from_hour: fromHour,
    to_hour: toHour,
    unit: '€/MWh',
    window: {
      start: toMadridIso(instants[window.start]),
      end: toMadridIso(new Date(instants[window.start + hours - 1].getTime() + HOUR_MS)),
      avg_price: round(window.avg),
    },
    cheapest: cheapest.map(priceHour),
    day_avg_price: round(dayAvg),
    saving_pct: round(((dayAvg - window.avg) / dayAvg) * 100, 1),
    source: PVPC_SOURCE,
  }
}

// --- Histórico ---

function daySummary(day: string): DaySummary {
  const rows = dayPrices(day)
  const byPrice = [...rows].sort((a, b) => a.price - b.price || a.instant.getTime() - b.instant.getTime())
  const dearest = [...rows].sort((a, b) => b.price - a.price || a.instant.getTime() - b.instant.getTime())[0]
  return {
    date: day,
    avg_price: round(mean(rows.map((r) => r.price))),
    min_price: byPrice[0].price,
    min_hour: toMadridIso(byPrice[0].instant),
    max_price: dearest.price,
    max_hour: toMadridIso(dearest.instant),
    complete: true,
    forecast: { model: 'lightgbm', mae: dailyMae(day) },
  }
}

export function history(start: string, end: string, lastDay: string): History {
  const days = daysBetween(start, end)
  return {
    start,
    end,
    unit: '€/MWh',
    missing_days: days.filter((day) => day > lastDay),
    days: days.filter((day) => day <= lastDay).map(daySummary),
    source: PVPC_SOURCE,
  }
}

// --- Mercado ---

const RENEWABLE = new Set(['Eólica', 'Solar fotovoltaica', 'Solar térmica', 'Hidráulica', 'Otras renovables', 'Residuos renovables'])

function dayMix(day: string): Record<string, number> {
  const random = seeded(`mix-${day}`)
  const wind = 90_000 + random() * 150_000
  const solar = 70_000 + random() * 110_000
  const hydro = 40_000 + random() * 60_000
  const mix: Record<string, number> = {
    Eólica: wind,
    'Solar fotovoltaica': solar,
    Nuclear: 140_000 + random() * 20_000,
    // El gas cubre lo que no dan las renovables
    'Ciclo combinado': Math.max(30_000, 360_000 - wind - solar - hydro + random() * 20_000),
    Hidráulica: hydro,
    Cogeneración: 42_000 + random() * 8_000,
    'Solar térmica': 6_000 + random() * 10_000,
    'Otras renovables': 10_000 + random() * 2_000,
    'Residuos renovables': 2_000 + random() * 400,
    'Residuos no renovables': 3_500 + random() * 800,
    Carbón: 2_000 + random() * 6_000,
  }
  const sorted = Object.entries(mix)
    .map(([tech, mwh]) => [tech, Math.round(mwh)] as const)
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
  return Object.fromEntries(sorted)
}

export function market(start: string, end: string, todayDay: string): Market {
  const days = daysBetween(start, end).filter((day) => day <= todayDay)
  const mixes = days.map((day) => ({ day, mix: dayMix(day) }))
  const totals: Record<string, number> = {}
  for (const { mix } of mixes) for (const [tech, mwh] of Object.entries(mix)) totals[tech] = (totals[tech] ?? 0) + mwh
  const total = Object.values(totals).reduce((a, b) => a + b, 0)
  const renewable = Object.entries(totals)
    .filter(([tech]) => RENEWABLE.has(tech))
    .reduce((a, [, mwh]) => a + mwh, 0)
  return {
    start,
    end,
    unit: 'MWh',
    renewable_pct: total ? round((renewable / total) * 100, 1) : null,
    technologies: Object.entries(totals)
      .sort((a, b) => b[1] - a[1])
      .map(([technology, mwh]) => ({ technology, mwh, pct: round((mwh / total) * 100), renewable: RENEWABLE.has(technology) })),
    missing_days: daysBetween(start, end).filter((day) => day > todayDay),
    days: mixes.map(({ day, mix }) => {
      const dayTotal = Object.values(mix).reduce((a, b) => a + b, 0)
      const dayRenewable = Object.entries(mix)
        .filter(([tech]) => RENEWABLE.has(tech))
        .reduce((a, [, mwh]) => a + mwh, 0)
      return {
        date: day,
        total_mwh: dayTotal,
        renewable_mwh: dayRenewable,
        renewable_pct: round((dayRenewable / dayTotal) * 100, 1),
        provisional: day === todayDay,
        mix,
      }
    }),
    source: GENERATION_SOURCE,
  }
}

// --- Estado y modelo ---

const MODEL_VERSION = 'ejemplo-lightgbm'

export function health(now: Date): Health {
  const lastDay = lastPublishedDay(now)
  const trainedAt = new Date(now.getTime() - 2 * 24 * HOUR_MS)
  const lastHours = dayHours(lastDay)
  return {
    status: 'ok',
    checked_at: toMadridIso(now),
    warnings: [],
    prices: {
      last_hour: toMadridIso(lastHours[lastHours.length - 1]),
      last_day: lastDay,
      has_tomorrow: lastDay > today(now),
    },
    forecast: {
      target_day: addDays(lastDay, 1),
      generated_at: toMadridIso(new Date(now.getTime() - HOUR_MS / 2)),
      model: 'lightgbm',
      model_version: MODEL_VERSION,
      fallback_reason: null,
    },
    model: {
      version: MODEL_VERSION,
      trained_at: toMadridIso(trainedAt),
      train_end: toMadridIso(new Date(trainedAt.getTime() - 3 * HOUR_MS)),
      training_rows: 17_520,
      age_days: 2,
    },
  }
}

export function modelReport(now: Date, days: number): ModelReport {
  const lastDay = lastPublishedDay(now)
  const trainedAt = new Date(now.getTime() - 2 * 24 * HOUR_MS)
  const end = addDays(today(now), 1)
  const start = addDays(end, -(days - 1))
  const live = daysBetween(start, end)
    .filter((day) => day <= lastDay)
    .map((day) => ({ date: day, model: 'lightgbm', mae: dailyMae(day), rmse: round(dailyMae(day) * 1.35), bias: -1.2 }))
  return {
    model: {
      version: MODEL_VERSION,
      trained_at: toMadridIso(trainedAt),
      train_start: toMadridIso(new Date(trainedAt.getTime() - 730 * 24 * HOUR_MS)),
      train_end: toMadridIso(new Date(trainedAt.getTime() - 3 * HOUR_MS)),
      training_rows: 17_520,
      features: ['hour', 'dayofweek', 'month', 'is_holiday', 'tariff_period', 'price_lag_1d', 'price_lag_7d', 'prev_day_mean'],
      params: { objective: 'l1', n_estimators: 500, learning_rate: 0.03 },
      library_versions: { lightgbm: '4.7.0' },
    },
    backtest: {
      start: addDays(today(now), -91),
      end: addDays(today(now), -2),
      days: 90,
      method: 'Walk-forward: cada día se predice solo con los días anteriores, como en producción, y se compara con el precio publicado por REE.',
      models: [
        { model: 'lightgbm', label: 'LightGBM', is_baseline: false, mae: 21.93, rmse: 29.61, bias: -4.8 },
        { model: 'media_7_dias', label: 'Media 7 días', is_baseline: true, mae: 32.45, rmse: 44.23, bias: -2.3 },
        { model: 'precio_ayer', label: 'Precio de ayer', is_baseline: true, mae: 33.54, rmse: 52.7, bias: -0.49 },
      ],
      improvement_pct: 32.4,
    },
    live: {
      start,
      end,
      days: live,
      mae: live.length ? round(mean(live.map((d) => d.mae))) : null,
      fallback_days: 0,
    },
  }
}

// --- Herramientas ---

export const CATALOG: Catalog = {
  appliances: [
    { id: 'lavadora', name: 'Lavadora', power_kw: 0.5, hours: 2, kwh: 1 },
    { id: 'lavavajillas', name: 'Lavavajillas', power_kw: 0.6, hours: 2, kwh: 1.2 },
    { id: 'secadora', name: 'Secadora', power_kw: 1.2, hours: 2, kwh: 2.4 },
    { id: 'horno', name: 'Horno', power_kw: 1.5, hours: 1, kwh: 1.5 },
    { id: 'coche', name: 'Coche eléctrico (cargador de 3,7 kW)', power_kw: 3.7, hours: 6, kwh: 22.2 },
  ],
  profiles: [
    { id: 'tipico', name: 'Hogar típico', description: 'Más consumo por la mañana y, sobre todo, por la noche' },
    { id: 'teletrabajo', name: 'Teletrabajo', description: 'Consumo repartido durante el día' },
    { id: 'coche_noche', name: 'Coche de noche', description: 'Carga del coche eléctrico de 1 a 6 h' },
    { id: 'constante', name: 'Constante', description: 'El mismo consumo todas las horas' },
  ],
  contracted_powers_kw: [3.45, 4.6, 5.75],
  base_load_kw: 0.4,
}

type ApplianceInput = SimulateRequest['appliance']

function appliance(input: ApplianceInput): ApplianceOut {
  if (typeof input === 'string') {
    const found = CATALOG.appliances.find((a) => a.id === input)
    if (!found) throw new Error(`Aparato desconocido: ${input}`)
    return found
  }
  if (!input) throw new Error('Falta el aparato')
  return { id: 'personalizado', name: input.name, power_kw: input.power_kw, hours: input.hours, kwh: input.power_kw * input.hours }
}

const kwhPrices = (day: string) => dayPrices(day).map((r) => r.price / 1000)
const endOf = (instants: Date[], index: number) =>
  toMadridIso(index < instants.length ? instants[index] : new Date(instants[instants.length - 1].getTime() + HOUR_MS))

export function simulate(request: SimulateRequest, day: string): Simulation {
  const instants = dayHours(day)
  const values = kwhPrices(day)
  const appliances = request.appliance ? [appliance(request.appliance)] : CATALOG.appliances
  const usesPerWeek = request.uses_per_week ?? 1
  const simulations = appliances.map((a) => {
    // Si no cabe desde la hora habitual, se adelanta hasta que quepa en el día
    const start = Math.min(hourIndex(instants, request.start_hour ?? 20), instants.length - a.hours)
    const cost = a.power_kw * values.slice(start, start + a.hours).reduce((x, y) => x + y, 0)
    const best = bestWindow(values, a.hours, hourIndex(instants, request.from_hour ?? 0), hourIndex(instants, request.to_hour ?? 24))
    const bestCost = best ? a.power_kw * a.hours * best.avg : null
    const saving = bestCost === null ? null : Math.max(cost - bestCost, 0)
    return {
      appliance: a,
      start: toMadridIso(instants[start]),
      end: endOf(instants, start + a.hours),
      cost: round(cost, 4),
      best: best
        ? { start: toMadridIso(instants[best.start]), end: endOf(instants, best.start + a.hours), avg_price: round(best.avg, 5) }
        : null,
      best_cost: bestCost === null ? null : round(bestCost, 4),
      saving_per_use: saving === null ? null : round(saving, 4),
      yearly_saving: saving === null ? null : round(saving * usesPerWeek * 52, 4),
    }
  })
  return {
    date: day,
    uses_per_week: usesPerWeek,
    simulations,
    total_yearly_saving: round(simulations.reduce((a, s) => a + (s.yearly_saving ?? 0), 0), 4),
    source: PVPC_SOURCE,
  }
}

export function plan(request: PlanRequest, day: string): Plan {
  const instants = dayHours(day)
  const values = kwhPrices(day)
  const powerKw = request.power_kw ?? 4.6
  const base = CATALOG.base_load_kw
  const load = instants.map(() => base)
  const habitualLoad = instants.map(() => base)
  const costAt = (a: ApplianceOut, start: number) => a.power_kw * values.slice(start, start + a.hours).reduce((x, y) => x + y, 0)

  const tasks = request.tasks.map((t) => {
    const a = appliance(t.appliance)
    const habitual = Math.min(hourIndex(instants, t.habitual_hour), instants.length - a.hours)
    for (let i = habitual; i < habitual + a.hours; i++) habitualLoad[i] += a.power_kw
    return { input: t, appliance: a, habitual, start: null as number | null }
  })
  for (const task of tasks.filter((t) => t.input.fixed)) {
    task.start = task.habitual
    for (let i = task.habitual; i < task.habitual + task.appliance.hours; i++) load[i] += task.appliance.power_kw
  }
  // Las flexibles, de mayor a menor consumo, a la ventana más barata que no supere la potencia
  const flexible = tasks.filter((t) => !t.input.fixed).sort((a, b) => b.appliance.kwh - a.appliance.kwh)
  for (const task of flexible) {
    const from = hourIndex(instants, task.input.from_hour ?? 0)
    const to = hourIndex(instants, task.input.to_hour ?? 24)
    let best: { start: number; cost: number } | null = null
    for (let start = from; start + task.appliance.hours <= to; start++) {
      const fits = load.slice(start, start + task.appliance.hours).every((kw) => kw + task.appliance.power_kw <= powerKw + 1e-9)
      const cost = costAt(task.appliance, start)
      if (fits && (!best || cost < best.cost - 1e-9)) best = { start, cost }
    }
    if (best) {
      task.start = best.start
      for (let i = best.start; i < best.start + task.appliance.hours; i++) load[i] += task.appliance.power_kw
    }
  }

  const planned = tasks.map((t) => {
    const habitualCost = costAt(t.appliance, t.habitual)
    const cost = t.start === null ? null : costAt(t.appliance, t.start)
    return {
      id: t.input.id,
      appliance: t.appliance,
      fixed: t.input.fixed ?? false,
      placed: t.start !== null,
      start: t.start === null ? null : toMadridIso(instants[t.start]),
      end: t.start === null ? null : endOf(instants, t.start + t.appliance.hours),
      cost: cost === null ? null : round(cost, 4),
      habitual_start: toMadridIso(instants[t.habitual]),
      habitual_cost: round(habitualCost, 4),
      saving: cost === null ? null : round(habitualCost - cost, 4),
    }
  })
  const placed = planned.filter((p) => p.placed)
  return {
    date: day,
    power_kw: powerKw,
    base_load_kw: base,
    tasks: planned,
    plan_cost: round(placed.reduce((a, p) => a + (p.cost ?? 0), 0), 4),
    habitual_cost: round(planned.reduce((a, p) => a + p.habitual_cost, 0), 4),
    saving: round(placed.reduce((a, p) => a + (p.saving ?? 0), 0), 4),
    unplaced: planned.filter((p) => !p.placed).map((p) => p.id),
    habitual_overloads: instants.filter((_, i) => habitualLoad[i] > powerKw + 1e-9).map(toMadridIso),
    hours: instants.map((instant, i) => ({
      datetime: toMadridIso(instant),
      price: round(values[i], 5),
      kw: round(load[i], 3),
      habitual_kw: round(habitualLoad[i], 3),
    })),
    source: PVPC_SOURCE,
  }
}

// Pesos horarios de los perfiles de consumo (los mismos que src/services/tariffs.py)
const PROFILE_WEIGHTS: Record<string, number[]> = {
  tipico: [2, 1.5, 1.2, 1.2, 1.2, 1.5, 3, 5, 5, 4, 3.5, 3.5, 4, 4.5, 4, 3.5, 3.5, 4, 5, 6.5, 7.5, 7.5, 6, 4],
  teletrabajo: [2, 1.5, 1.2, 1.2, 1.2, 1.5, 2.5, 4, 5.5, 6, 6, 6, 6.5, 6.5, 5.5, 5.5, 5.5, 5, 5, 5.5, 6, 5.5, 4.5, 3],
  coche_noche: [6, 9, 9, 9, 9, 6, 3, 4, 4, 3, 3, 3, 3.5, 4, 3.5, 3, 3, 3.5, 4.5, 5.5, 6.5, 6.5, 5, 4],
  constante: Array(24).fill(1),
}

export function bill(request: BillRequest, start: string, end: string, lastDay: string): Bill {
  const profile = request.profile ?? 'tipico'
  const weights = PROFILE_WEIGHTS[profile]
  const shift = request.shift_fraction ?? 0
  const fixed = request.fixed_price ?? null
  const days = daysBetween(start, end).filter((day) => day <= lastDay)
  const kwhPerDay = request.total_kwh / days.length
  const periods: Record<TariffPeriod, { kwh: number; cost: number }> = {
    punta: { kwh: 0, cost: 0 },
    llano: { kwh: 0, cost: 0 },
    valle: { kwh: 0, cost: 0 },
  }
  let pvpc = 0
  let saving = 0
  const dayCosts = days.map((day) => {
    const rows = dayPrices(day)
    const dayWeights = rows.map((r) => weights[madridHour(r.instant)])
    const scale = kwhPerDay / dayWeights.reduce((a, b) => a + b, 0)
    let dayCost = 0
    rows.forEach((r, i) => {
      const kwh = dayWeights[i] * scale
      const cost = (kwh * r.price) / 1000
      dayCost += cost
      periods[tariffPeriod(r.instant)].kwh += kwh
      periods[tariffPeriod(r.instant)].cost += cost
    })
    const cheapest = mean(rows.map((r) => r.price / 1000).sort((a, b) => a - b).slice(0, 4))
    saving += Math.max(shift * kwhPerDay * (dayCost / kwhPerDay - cheapest), 0)
    pvpc += dayCost
    return { date: day, kwh: round(kwhPerDay, 3), pvpc_cost: round(dayCost, 4), fixed_cost: fixed === null ? null : round(kwhPerDay * fixed, 4) }
  })
  const shifted = pvpc - saving
  return {
    start,
    end,
    profile,
    total_kwh: request.total_kwh,
    shift_fraction: shift,
    pvpc_cost: round(pvpc, 4),
    pvpc_shifted_cost: round(shifted, 4),
    fixed_cost: fixed === null ? null : round(request.total_kwh * fixed, 4),
    effective_price: round(pvpc / request.total_kwh, 4),
    break_even_price: round(shifted / request.total_kwh, 4),
    fixed_saving: fixed === null ? null : round(request.total_kwh * fixed - shifted, 4),
    days_fixed_was_cheaper: fixed === null ? null : dayCosts.filter((d) => (d.fixed_cost ?? 0) < d.pvpc_cost).length,
    periods: (Object.keys(periods) as TariffPeriod[]).map((period) => ({
      period,
      kwh: round(periods[period].kwh, 3),
      cost: round(periods[period].cost, 4),
      avg_price: periods[period].kwh ? round(periods[period].cost / periods[period].kwh, 4) : null,
    })),
    days: dayCosts,
    missing_days: daysBetween(start, end).filter((day) => day > lastDay),
    note: 'Solo el término de energía: sin término de potencia, alquiler del contador ni impuestos.',
    source: PVPC_SOURCE,
  }
}
