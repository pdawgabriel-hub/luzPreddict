"""Simulador: cuánto cuesta usar un aparato a una hora y cuánto se ahorra moviéndolo.

Python puro (sin pandas): lo usan la API y el pipeline. Los precios llegan en
€/MWh por hora y los costes se dan en €. Los consumos del catálogo son valores
típicos aproximados: cada aparato real consume distinto.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

from src.services.best_hours import HOUR, Window, best_window

WEEKS_PER_YEAR = 52


@dataclass(frozen=True)
class Appliance:
    id: str
    name: str
    power_kw: float  # potencia media durante el uso
    hours: int  # duración de un uso

    def __post_init__(self) -> None:
        if self.power_kw <= 0 or self.hours < 1:
            raise ValueError(f"Aparato no válido: {self.power_kw} kW durante {self.hours} h")

    @property
    def kwh(self) -> float:
        return self.power_kw * self.hours


# Consumos típicos aproximados
APPLIANCES: dict[str, Appliance] = {
    a.id: a
    for a in [
        Appliance("lavadora", "Lavadora", 0.5, 2),
        Appliance("lavavajillas", "Lavavajillas", 0.6, 2),
        Appliance("secadora", "Secadora", 1.2, 2),
        Appliance("horno", "Horno", 1.5, 1),
        Appliance("coche", "Coche eléctrico (cargador de 3,7 kW)", 3.7, 6),
    ]
}


@dataclass(frozen=True)
class Simulation:
    appliance: Appliance
    start: datetime  # inicio elegido (UTC)
    cost: float  # € a la hora elegida
    best: Window | None  # mejor ventana dentro de la franja (None si no cabe ninguna)
    best_cost: float | None  # € en la mejor ventana
    uses_per_week: float

    @property
    def saving_per_use(self) -> float | None:
        """€ que se ahorran cada vez moviéndolo a la mejor hora (0 si ya es la mejor)."""
        return None if self.best_cost is None else max(self.cost - self.best_cost, 0.0)

    @property
    def yearly_saving(self) -> float | None:
        """€ al año si se usa `uses_per_week` veces por semana con precios como estos."""
        saving = self.saving_per_use
        return None if saving is None else saving * self.uses_per_week * WEEKS_PER_YEAR


def _hourly_prices(prices: Iterable[tuple[datetime, float]]) -> dict[datetime, float]:
    by_hour = {}
    for ts, price in prices:
        if ts.tzinfo is None or ts.utcoffset() is None:
            raise ValueError(f"Hora sin zona horaria: {ts!r}")
        by_hour[ts.astimezone(UTC)] = price / 1000  # €/kWh
    return by_hour


def cost_at(prices: dict[datetime, float], appliance: Appliance, start: datetime) -> float:
    """€ de un uso que empieza en `start`. Falla si alguna hora no tiene precio."""
    hours = [start.astimezone(UTC) + i * HOUR for i in range(appliance.hours)]
    missing = [h for h in hours if h not in prices]
    if missing:
        raise ValueError(f"No hay precio para las {len(missing)} hora(s) desde {missing[0]:%Y-%m-%d %H:%M} UTC")
    return sum(appliance.power_kw * prices[h] for h in hours)


def simulate(
    prices: Iterable[tuple[datetime, float]],
    appliance: str | Appliance,
    start: datetime,
    not_before: datetime | None = None,
    end_by: datetime | None = None,
    uses_per_week: float = 1,
) -> Simulation:
    """Coste de usar `appliance` desde `start` y la mejor hora dentro de la franja [not_before, end_by]."""
    if uses_per_week < 0:
        raise ValueError(f"Los usos por semana no pueden ser negativos (son {uses_per_week})")
    appliance = APPLIANCES[appliance] if isinstance(appliance, str) else appliance
    by_hour = _hourly_prices(prices)

    best = best_window(by_hour.items(), appliance.hours, not_before=not_before, end_by=end_by)
    best_cost = appliance.power_kw * appliance.hours * best.avg_price if best else None
    return Simulation(
        appliance=appliance,
        start=start.astimezone(UTC),
        cost=cost_at(by_hour, appliance, start),
        best=best,
        best_cost=best_cost,
        uses_per_week=uses_per_week,
    )


def simulate_all(
    prices: Iterable[tuple[datetime, float]],
    start: datetime,
    not_before: datetime | None = None,
    end_by: datetime | None = None,
    uses_per_week: float = 1,
    appliances: Iterable[Appliance] | None = None,
) -> list[Simulation]:
    """La misma simulación para cada aparato del catálogo.

    Si un aparato no cabe empezando en `start` (por ejemplo, 6 horas a partir de
    las 21:00), se adelanta su inicio hasta que quepa en las horas con precio.
    """
    prices = list(prices)  # se recorre una vez por aparato
    last_hour = max(_hourly_prices(prices))
    results = []
    for appliance in appliances or APPLIANCES.values():
        latest_start = last_hour - (appliance.hours - 1) * HOUR
        appliance_start = min(start.astimezone(UTC), latest_start)
        results.append(simulate(prices, appliance, appliance_start, not_before, end_by, uses_per_week))
    return results


def total_yearly_saving(simulations: Iterable[Simulation]) -> float:
    """Ahorro anual sumando todos los aparatos que tienen una mejor hora."""
    return sum(s.yearly_saving for s in simulations if s.yearly_saving is not None)
