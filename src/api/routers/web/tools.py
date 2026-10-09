"""/api/tools: simulador, planificador y factura (uso interno de la web).

No forma parte de la API pública /v1: la web las llama desde el mismo dominio.
Son POST porque reciben formularios (el planificador, una lista de tareas).
"""

from collections.abc import Callable
from datetime import date, datetime, timedelta

from fastapi import APIRouter, HTTPException, Response

from src.api.deps import DEFAULT_HISTORY_DAYS, MAX_HISTORY_DAYS, DayRange, NowDep, SessionDep, check_range, today
from src.api.errors import error_responses
from src.api.queries import day_prices, local_hour, no_prices, range_prices
from src.api.schemas.tools import (
    ApplianceOut,
    Bill,
    BillRequest,
    Catalog,
    CustomAppliance,
    DayCostOut,
    LoadHour,
    PeriodOut,
    Plan,
    PlannedTaskOut,
    PlanRequest,
    PriceWindow,
    ProfileOut,
    SimulateRequest,
    Simulation,
    SimulationOut,
)
from src.services.best_hours import HOUR
from src.services.best_hours import Window as BestWindow
from src.services.planner import BASE_LOAD_KW, CONTRACTED_POWERS_KW, Task, plan_day
from src.services.simulator import APPLIANCES, Appliance, simulate_all, total_yearly_saving
from src.services.tariffs import PROFILES, compare_bill
from src.utils.calendar import local_date, market_timezone

CUSTOM_ID = "personalizado"
EURO_DECIMALS = 4  # un uso de la lavadora cuesta céntimos
PRICE_DECIMALS = 5  # €/kWh

router = APIRouter(prefix="/api/tools", tags=["Herramientas"])


def _eur(value: float | None) -> float | None:
    return round(value, EURO_DECIMALS) if value is not None else None


def _appliance(value: str | CustomAppliance) -> Appliance:
    if isinstance(value, str):
        return APPLIANCES[value]
    return Appliance(CUSTOM_ID, value.name, value.power_kw, value.hours)


def _appliance_out(appliance: Appliance) -> ApplianceOut:
    return ApplianceOut(
        id=appliance.id, name=appliance.name, power_kw=appliance.power_kw, hours=appliance.hours, kwh=appliance.kwh
    )


def _local(ts: datetime | None) -> datetime | None:
    return ts.astimezone(market_timezone()) if ts is not None else None


def _window(window: BestWindow | None) -> PriceWindow | None:
    """El simulador calcula la ventana con precios en €/kWh."""
    if window is None:
        return None
    return PriceWindow(
        start=_local(window.start), end=_local(window.end), avg_price=round(window.avg_price, PRICE_DECIMALS)
    )


def _run[T](compute: Callable[[], T]) -> T:
    """Los servicios avisan con ValueError de lo que no se puede calcular (p. ej. tareas que no caben)."""
    try:
        return compute()
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/catalog", summary="Aparatos, perfiles y potencias para los formularios")
def get_catalog(response: Response) -> Catalog:
    response.headers["Cache-Control"] = "public, max-age=3600"  # solo cambia con una nueva versión
    return Catalog(
        appliances=[_appliance_out(a) for a in APPLIANCES.values()],
        profiles=[ProfileOut(id=p.id, name=p.name, description=p.description) for p in PROFILES.values()],
        contracted_powers_kw=list(CONTRACTED_POWERS_KW),
        base_load_kw=BASE_LOAD_KW,
    )


@router.post(
    "/simulate",
    summary="Coste de un aparato y ahorro moviéndolo a la mejor hora",
    responses=error_responses(404, 422),
)
def post_simulate(request: SimulateRequest, session: SessionDep, now: NowDep) -> Simulation:
    day, rows = day_prices(session, now, request.date, location="body")
    appliances = [_appliance(request.appliance)] if request.appliance is not None else None
    simulations = _run(
        lambda: simulate_all(
            rows,
            local_hour(day, request.start_hour),
            not_before=local_hour(day, request.from_hour),
            end_by=local_hour(day, request.to_hour),
            uses_per_week=request.uses_per_week,
            appliances=appliances,
        )
    )
    tz = market_timezone()
    return Simulation(
        date=day,
        uses_per_week=request.uses_per_week,
        simulations=[
            SimulationOut(
                appliance=_appliance_out(s.appliance),
                start=s.start.astimezone(tz),
                end=(s.start + s.appliance.hours * HOUR).astimezone(tz),
                cost=_eur(s.cost),
                best=_window(s.best),
                best_cost=_eur(s.best_cost),
                saving_per_use=_eur(s.saving_per_use),
                yearly_saving=_eur(s.yearly_saving),
            )
            for s in simulations
        ],
        total_yearly_saving=_eur(total_yearly_saving(simulations)),
    )


@router.post(
    "/plan",
    summary="Reparto de aparatos en las horas baratas sin superar la potencia contratada",
    responses=error_responses(404, 422),
)
def post_plan(request: PlanRequest, session: SessionDep, now: NowDep) -> Plan:
    day, rows = day_prices(session, now, request.date, location="body")
    tasks = [
        Task(
            id=t.id,
            appliance=_appliance(t.appliance),
            habitual_start=local_hour(day, t.habitual_hour),
            fixed=t.fixed,
            not_before=local_hour(day, t.from_hour),
            end_by=local_hour(day, t.to_hour),
        )
        for t in request.tasks
    ]
    plan = _run(lambda: plan_day(rows, tasks, power_kw=request.power_kw))

    prices = dict(rows)
    return Plan(
        date=day,
        power_kw=plan.power_kw,
        base_load_kw=plan.base_load_kw,
        tasks=[
            PlannedTaskOut(
                id=p.task.id,
                appliance=_appliance_out(p.task.appliance),
                fixed=p.task.fixed,
                placed=p.placed,
                start=_local(p.start),
                end=_local(p.start + p.task.appliance.hours * HOUR) if p.placed else None,
                cost=_eur(p.cost),
                habitual_start=_local(p.habitual_start),
                habitual_cost=_eur(p.habitual_cost),
                saving=_eur(p.habitual_cost - p.cost) if p.placed else None,
            )
            for p in plan.tasks
        ],
        plan_cost=_eur(plan.plan_cost),
        habitual_cost=_eur(plan.habitual_cost),
        saving=_eur(plan.saving),
        unplaced=[t.id for t in plan.unplaced],
        habitual_overloads=[_local(h) for h in plan.habitual_overloads],
        hours=[
            LoadHour(
                datetime=_local(h),
                price=round(prices[h] / 1000, PRICE_DECIMALS),
                kw=round(plan.load[h], 3),
                habitual_kw=round(plan.habitual_load[h], 3),
            )
            for h in sorted(plan.load)
        ],
    )


@router.post(
    "/bill",
    summary="Factura de energía con PVPC frente a un precio fijo",
    responses=error_responses(404, 422),
)
def post_bill(request: BillRequest, session: SessionDep, now: NowDep) -> Bill:
    if request.start is None and request.end is None:
        days = DayRange(today(now) - timedelta(days=DEFAULT_HISTORY_DAYS - 1), today(now))
    else:
        days = check_range(request.start, request.end, today(now) + timedelta(days=1), MAX_HISTORY_DAYS, "body")
    rows = range_prices(session, days)
    if not rows:
        raise no_prices(days, now)

    bill = _run(
        lambda: compare_bill(
            rows,
            request.total_kwh,
            profile=request.profile,
            fixed_price=request.fixed_price,
            shift_fraction=request.shift_fraction,
        )
    )
    present: set[date] = {local_date(ts) for ts, _ in rows}
    return Bill(
        start=days.start,
        end=days.end,
        profile=request.profile,
        total_kwh=bill.total_kwh,
        shift_fraction=bill.shift_fraction,
        pvpc_cost=_eur(bill.pvpc_cost),
        pvpc_shifted_cost=_eur(bill.pvpc_shifted_cost),
        fixed_cost=_eur(bill.fixed_cost),
        effective_price=_eur(bill.effective_price),
        break_even_price=_eur(bill.break_even_price),
        fixed_saving=_eur(bill.fixed_saving),
        days_fixed_was_cheaper=bill.days_fixed_was_cheaper,
        periods=[
            PeriodOut(period=period, kwh=round(s.kwh, 3), cost=_eur(s.cost), avg_price=_eur(s.avg_price))
            for period, s in bill.periods.items()
        ],
        days=[
            DayCostOut(date=d.day, kwh=round(d.kwh, 3), pvpc_cost=_eur(d.pvpc_cost), fixed_cost=_eur(d.fixed_cost))
            for d in bill.days
        ],
        missing_days=[d for d in days.days if d not in present],
    )
