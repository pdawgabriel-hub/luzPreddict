"""Horas más baratas a partir de precios horarios.

Python puro (sin pandas): lo usan la API y el pipeline. Los precios llegan como
pares (inicio de la hora con zona horaria, €/MWh); se trabaja en UTC, así que
los días de 23 y 25 horas no rompen la continuidad.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

HOUR = timedelta(hours=1)


@dataclass(frozen=True)
class Window:
    start: datetime  # inicio de la primera hora (UTC)
    end: datetime  # fin de la última hora (UTC)
    hours: int
    avg_price: float  # €/MWh


def normalize_prices(prices: Iterable[tuple[datetime, float]]) -> list[tuple[datetime, float]]:
    """Precios en UTC, ordenados y sin horas repetidas (si una hora llega dos veces, gana el último valor).

    Rechaza las fechas sin zona horaria. Lo usan todos los servicios que reciben precios.
    """
    by_hour: dict[datetime, float] = {}
    for ts, price in prices:
        if ts.tzinfo is None or ts.utcoffset() is None:
            raise ValueError(f"Hora sin zona horaria: {ts!r}")
        by_hour[ts.astimezone(UTC)] = float(price)
    return sorted(by_hour.items())


def best_window(
    prices: Iterable[tuple[datetime, float]],
    hours: int,
    not_before: datetime | None = None,
    end_by: datetime | None = None,
) -> Window | None:
    """Las `hours` horas seguidas con el precio medio más bajo.

    Opcionalmente, la ventana debe empezar en `not_before` o después y terminar
    en `end_by` o antes. Si hay empate gana la más temprana. Devuelve None si no
    cabe ninguna ventana (pocas horas, huecos en los datos o franja demasiado corta).
    """
    if hours < 1:
        raise ValueError(f"La ventana debe tener al menos 1 hora (se pidieron {hours})")

    rows = normalize_prices(prices)
    if not_before is not None:
        rows = [r for r in rows if r[0] >= not_before]
    if end_by is not None:
        rows = [r for r in rows if r[0] + HOUR <= end_by]

    best: Window | None = None
    run_start = 0  # inicio del tramo de horas seguidas actual
    total = 0.0
    for i, (ts, price) in enumerate(rows):
        if i > 0 and ts - rows[i - 1][0] != HOUR:
            run_start, total = i, 0.0  # hueco: empieza un tramo nuevo
        total += price
        if i - run_start + 1 > hours:
            total -= rows[i - hours][1]
        if i - run_start + 1 >= hours:
            avg = total / hours
            if best is None or avg < best.avg_price - 1e-9:
                first = rows[i - hours + 1][0]
                best = Window(start=first, end=ts + HOUR, hours=hours, avg_price=avg)
    return best


def cheapest_hours(prices: Iterable[tuple[datetime, float]], n: int) -> list[tuple[datetime, float]]:
    """Las `n` horas más baratas (no tienen por qué ser seguidas), de más barata a más cara.

    Con el mismo precio, primero la más temprana.
    """
    if n < 1:
        raise ValueError(f"Hay que pedir al menos 1 hora (se pidieron {n})")
    return sorted(normalize_prices(prices), key=lambda r: (r[1], r[0]))[:n]
