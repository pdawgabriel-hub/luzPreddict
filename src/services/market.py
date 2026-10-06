"""Mix de generación y peso renovable a partir de la generación diaria de REE.

Python puro (sin pandas): lo usan la API y la ingesta. Las filas llegan como
(día local, tecnología, MWh).
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

# Comprobado contra el indicador "Renovable" de REE: la suma coincide exactamente
RENEWABLE_TECHNOLOGIES = frozenset(
    {
        "Eólica",
        "Solar fotovoltaica",
        "Solar térmica",
        "Hidráulica",
        "Hidroeólica",
        "Otras renovables",
        "Residuos renovables",
    }
)


def is_renewable(technology: str) -> bool:
    return technology in RENEWABLE_TECHNOLOGIES


def _pct(part: float, total: float) -> float | None:
    return part / total * 100 if total > 0 else None


@dataclass(frozen=True)
class TechnologyShare:
    technology: str
    mwh: float
    pct: float | None  # % del total
    renewable: bool


@dataclass(frozen=True)
class DayMix:
    day: date
    total_mwh: float
    renewable_mwh: float
    mix: dict[str, float]  # MWh por tecnología, de mayor a menor

    @property
    def renewable_pct(self) -> float | None:
        return _pct(self.renewable_mwh, self.total_mwh)


def daily_mix(rows: Iterable[tuple[date, str, float]]) -> list[DayMix]:
    """Mix de cada día, ordenado por día. Si una tecnología llega dos veces el mismo día, gana el último valor."""
    by_day: dict[date, dict[str, float]] = defaultdict(dict)
    for day, technology, mwh in rows:
        by_day[day][technology] = float(mwh)
    result = []
    for day, mix in sorted(by_day.items()):
        result.append(
            DayMix(
                day=day,
                total_mwh=sum(mix.values()),
                renewable_mwh=sum(mwh for tech, mwh in mix.items() if is_renewable(tech)),
                mix=dict(sorted(mix.items(), key=lambda item: (-item[1], item[0]))),
            )
        )
    return result


def period_mix(days: Iterable[DayMix]) -> list[TechnologyShare]:
    """Mix acumulado de varios días, de la tecnología que más generó a la que menos."""
    totals: dict[str, float] = defaultdict(float)
    for day in days:
        for technology, mwh in day.mix.items():
            totals[technology] += mwh
    total = sum(totals.values())
    return [
        TechnologyShare(technology=tech, mwh=mwh, pct=_pct(mwh, total), renewable=is_renewable(tech))
        for tech, mwh in sorted(totals.items(), key=lambda item: (-item[1], item[0]))
    ]
