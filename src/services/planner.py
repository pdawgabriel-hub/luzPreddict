"""Planificador: reparte varios aparatos en las horas más baratas sin superar la potencia contratada.

Python puro (sin pandas). Algoritmo voraz, simple y predecible (no garantiza el
óptimo absoluto):

1. Hay un consumo base fijo todas las horas (nevera, router, aparatos en espera).
2. Las tareas fijas se quedan a su hora habitual y ocupan potencia primero,
   aunque la superen (eso se avisa en `Plan.habitual_overloads`).
3. Las tareas flexibles, de mayor a menor energía, van a la ventana más barata
   en la que ninguna hora supere la potencia contratada (dentro de su franja,
   si la tienen). Si no caben en ninguna, quedan sin colocar.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

from src.services.best_hours import HOUR
from src.services.simulator import Appliance, cost_at

BASE_LOAD_KW = 0.4  # consumo base estimado
CONTRACTED_POWERS_KW = (3.45, 4.6, 5.75)  # potencias contratadas habituales en hogares
_EPS = 1e-9


@dataclass(frozen=True)
class Task:
    id: str
    appliance: Appliance
    habitual_start: datetime  # cuándo se usaría sin planificar
    fixed: bool = False  # si es fija, no se mueve de su hora habitual
    not_before: datetime | None = None  # franja en la que se puede mover
    end_by: datetime | None = None


@dataclass(frozen=True)
class PlannedTask:
    task: Task
    start: datetime | None  # inicio en el plan (UTC); None si no cabe en ningún sitio
    cost: float | None  # € en el plan
    habitual_start: datetime  # inicio habitual ajustado para que quepa en el día (UTC)
    habitual_cost: float  # € a su hora habitual

    @property
    def placed(self) -> bool:
        return self.start is not None


@dataclass(frozen=True)
class Plan:
    tasks: list[PlannedTask]
    power_kw: float
    base_load_kw: float
    load: dict[datetime, float]  # kW por hora con el plan (UTC)
    habitual_load: dict[datetime, float]  # kW por hora a las horas habituales

    @property
    def unplaced(self) -> list[Task]:
        return [p.task for p in self.tasks if not p.placed]

    @property
    def plan_cost(self) -> float:
        """€ de las tareas colocadas con el plan."""
        return sum(p.cost for p in self.tasks if p.placed)

    @property
    def habitual_cost(self) -> float:
        """€ de todas las tareas a su hora habitual."""
        return sum(p.habitual_cost for p in self.tasks)

    @property
    def saving(self) -> float:
        """€ ahorrados con el plan, comparando solo las tareas que el plan ha podido colocar."""
        return sum(p.habitual_cost - p.cost for p in self.tasks if p.placed)

    @property
    def habitual_overloads(self) -> list[datetime]:
        """Horas en las que el horario habitual superaría la potencia contratada (saltaría el limitador)."""
        return [h for h, kw in sorted(self.habitual_load.items()) if kw > self.power_kw + _EPS]


def _window(start: datetime, hours: int) -> list[datetime]:
    return [start + i * HOUR for i in range(hours)]


def _clamp_to_day(start: datetime, hours: int, first_hour: datetime, last_hour: datetime) -> datetime:
    """Ajusta el inicio para que la tarea quede dentro de las horas con precio."""
    return max(first_hour, min(start.astimezone(UTC), last_hour - (hours - 1) * HOUR))


def plan_day(
    prices: Iterable[tuple[datetime, float]],
    tasks: Iterable[Task],
    power_kw: float = 4.6,
    base_load_kw: float = BASE_LOAD_KW,
) -> Plan:
    """Planifica las tareas sobre los precios dados (€/MWh por hora)."""
    if power_kw <= base_load_kw:
        raise ValueError(f"La potencia contratada ({power_kw} kW) debe superar el consumo base ({base_load_kw} kW)")
    by_hour: dict[datetime, float] = {}
    for ts, price in prices:
        if ts.tzinfo is None or ts.utcoffset() is None:
            raise ValueError(f"Hora sin zona horaria: {ts!r}")
        by_hour[ts.astimezone(UTC)] = price / 1000  # €/kWh
    if not by_hour:
        raise ValueError("No hay precios")
    tasks = list(tasks)
    if len({t.id for t in tasks}) != len(tasks):
        raise ValueError("Hay tareas con el mismo id")

    hours = sorted(by_hour)
    first_hour, last_hour = hours[0], hours[-1]
    too_long = [t.id for t in tasks if t.appliance.hours > len(hours)]
    if too_long:
        raise ValueError(f"Tareas más largas que el periodo con precios ({len(hours)} h): {', '.join(too_long)}")
    load = dict.fromkeys(hours, base_load_kw)
    habitual_load = dict.fromkeys(hours, base_load_kw)
    habitual = {t.id: _clamp_to_day(t.habitual_start, t.appliance.hours, first_hour, last_hour) for t in tasks}
    placed: dict[str, datetime | None] = {}

    for task in tasks:
        for hour in _window(habitual[task.id], task.appliance.hours):
            habitual_load[hour] += task.appliance.power_kw
        if task.fixed:
            for hour in _window(habitual[task.id], task.appliance.hours):
                load[hour] += task.appliance.power_kw
            placed[task.id] = habitual[task.id]

    flexible = sorted((t for t in tasks if not t.fixed), key=lambda t: (-t.appliance.kwh, t.id))
    for task in flexible:
        best_start, best_cost = None, None
        for start in hours:
            window = _window(start, task.appliance.hours)
            if window[-1] > last_hour or any(h not in by_hour for h in window):
                continue
            if task.not_before is not None and start < task.not_before:
                continue
            if task.end_by is not None and window[-1] + HOUR > task.end_by:
                continue
            if any(load[h] + task.appliance.power_kw > power_kw + _EPS for h in window):
                continue
            cost = cost_at(by_hour, task.appliance, start)
            if best_cost is None or cost < best_cost - _EPS:
                best_start, best_cost = start, cost
        if best_start is not None:
            for hour in _window(best_start, task.appliance.hours):
                load[hour] += task.appliance.power_kw
        placed[task.id] = best_start

    planned = [
        PlannedTask(
            task=t,
            start=placed[t.id],
            cost=cost_at(by_hour, t.appliance, placed[t.id]) if placed[t.id] is not None else None,
            habitual_start=habitual[t.id],
            habitual_cost=cost_at(by_hour, t.appliance, habitual[t.id]),
        )
        for t in tasks
    ]
    return Plan(tasks=planned, power_kw=power_kw, base_load_kw=base_load_kw, load=load, habitual_load=habitual_load)
