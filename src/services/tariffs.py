"""Factura de energía con PVPC por tramos 2.0TD y comparación con un precio fijo.

Solo el término de energía: no incluye término de potencia, alquiler del
contador ni impuestos. Python puro (sin pandas): lo usan la API y el pipeline.

El consumo del periodo se reparte por igual entre los días y, dentro de cada
día, según un perfil horario aproximado (por hora local). En los días de 23 y
25 horas el perfil se reajusta para que el día sume lo mismo.
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from src.utils.calendar import TariffPeriod, market_timezone, tariff_period

# Horas más baratas de cada día a las que se mueve el consumo desplazable
SHIFT_TO_CHEAPEST_HOURS = 4


@dataclass(frozen=True)
class Profile:
    id: str
    name: str
    description: str
    weights: tuple[float, ...]  # 24 pesos relativos, uno por hora local


# Perfiles aproximados (no son perfiles oficiales de REE)
PROFILES: dict[str, Profile] = {
    p.id: p
    for p in [
        Profile(
            "tipico",
            "Hogar típico",
            "Más consumo por la mañana y, sobre todo, por la noche",
            (2, 1.5, 1.2, 1.2, 1.2, 1.5, 3, 5, 5, 4, 3.5, 3.5, 4, 4.5, 4, 3.5, 3.5, 4, 5, 6.5, 7.5, 7.5, 6, 4),
        ),
        Profile(
            "teletrabajo",
            "Teletrabajo",
            "Consumo repartido durante el día",
            (2, 1.5, 1.2, 1.2, 1.2, 1.5, 2.5, 4, 5.5, 6, 6, 6, 6.5, 6.5, 5.5, 5.5, 5.5, 5, 5, 5.5, 6, 5.5, 4.5, 3),
        ),
        Profile(
            "coche_noche",
            "Coche de noche",
            "Carga del coche eléctrico de 1 a 6 h",
            (6, 9, 9, 9, 9, 6, 3, 4, 4, 3, 3, 3, 3.5, 4, 3.5, 3, 3, 3.5, 4.5, 5.5, 6.5, 6.5, 5, 4),
        ),
        Profile("constante", "Constante", "El mismo consumo todas las horas", (1,) * 24),
    ]
}


@dataclass(frozen=True)
class PeriodSummary:
    kwh: float
    cost: float  # €

    @property
    def avg_price(self) -> float | None:
        """€/kWh medio pagado en el tramo."""
        return self.cost / self.kwh if self.kwh else None


@dataclass(frozen=True)
class DayCost:
    day: date  # día local
    kwh: float
    pvpc_cost: float  # €
    fixed_cost: float | None  # €


@dataclass(frozen=True)
class BillComparison:
    total_kwh: float
    pvpc_cost: float  # €
    pvpc_shifted_cost: float  # € moviendo `shift_fraction` del consumo a las horas más baratas
    fixed_cost: float | None  # € con el precio fijo (None si no se indicó)
    shift_fraction: float
    periods: dict[TariffPeriod, PeriodSummary]
    days: list[DayCost] = field(repr=False)

    @property
    def effective_price(self) -> float:
        """€/kWh medio pagado con PVPC."""
        return self.pvpc_cost / self.total_kwh

    @property
    def break_even_price(self) -> float:
        """Precio fijo (€/kWh) por debajo del cual el fijo sale más barato que el PVPC (moviendo consumo)."""
        return self.pvpc_shifted_cost / self.total_kwh

    @property
    def fixed_saving(self) -> float | None:
        """€ que se ahorran con PVPC (moviendo consumo) frente al fijo; negativo si el fijo es mejor."""
        return None if self.fixed_cost is None else self.fixed_cost - self.pvpc_shifted_cost

    @property
    def days_fixed_was_cheaper(self) -> int | None:
        """Días en que el fijo habría salido más barato que el PVPC, sin mover consumo."""
        if self.fixed_cost is None:
            return None
        return sum(1 for d in self.days if d.fixed_cost is not None and d.fixed_cost < d.pvpc_cost)


def compare_bill(
    prices: Iterable[tuple[datetime, float]],
    total_kwh: float,
    profile: str | Profile = "tipico",
    fixed_price: float | None = None,
    shift_fraction: float = 0.0,
) -> BillComparison:
    """Coste de la energía de un periodo con PVPC (€/MWh por hora) y con un precio fijo (€/kWh)."""
    if total_kwh <= 0:
        raise ValueError(f"El consumo debe ser positivo (es {total_kwh})")
    if not 0 <= shift_fraction <= 1:
        raise ValueError(f"La parte desplazable debe estar entre 0 y 1 (es {shift_fraction})")
    if fixed_price is not None and fixed_price <= 0:
        raise ValueError(f"El precio fijo debe ser positivo (es {fixed_price})")
    profile = PROFILES[profile] if isinstance(profile, str) else profile

    tz = market_timezone()
    by_day: dict[date, list[tuple[datetime, float]]] = defaultdict(list)
    for ts, price in prices:
        if ts.tzinfo is None or ts.utcoffset() is None:
            raise ValueError(f"Hora sin zona horaria: {ts!r}")
        by_day[ts.astimezone(tz).date()].append((ts.astimezone(UTC), price / 1000))  # €/kWh
    if not by_day:
        raise ValueError("No hay precios en el periodo")

    kwh_per_day = total_kwh / len(by_day)
    periods: dict[TariffPeriod, list[float]] = {p: [0.0, 0.0] for p in TariffPeriod}
    days, pvpc_cost, saving = [], 0.0, 0.0

    for day in sorted(by_day):
        hours = sorted(by_day[day])
        weights = [profile.weights[ts.astimezone(tz).hour] for ts, _ in hours]
        scale = kwh_per_day / sum(weights)
        day_cost = 0.0
        for (ts, price), weight in zip(hours, weights, strict=True):
            kwh = weight * scale
            day_cost += kwh * price
            summary = periods[tariff_period(ts)]
            summary[0] += kwh
            summary[1] += kwh * price
        pvpc_cost += day_cost

        # Mover parte del consumo del día a sus horas más baratas
        cheapest = sorted(price for _, price in hours)[:SHIFT_TO_CHEAPEST_HOURS]
        moved_kwh = shift_fraction * kwh_per_day
        saving += max(moved_kwh * (day_cost / kwh_per_day - sum(cheapest) / len(cheapest)), 0.0)

        fixed_day = kwh_per_day * fixed_price if fixed_price is not None else None
        days.append(DayCost(day, kwh_per_day, day_cost, fixed_day))

    return BillComparison(
        total_kwh=total_kwh,
        pvpc_cost=pvpc_cost,
        pvpc_shifted_cost=pvpc_cost - saving,
        fixed_cost=total_kwh * fixed_price if fixed_price is not None else None,
        shift_fraction=shift_fraction,
        periods={p: PeriodSummary(kwh, cost) for p, (kwh, cost) in periods.items()},
        days=days,
    )
