"""Resumen diario de los precios de un día, para la notificación de ntfy y la web.

Python puro (sin pandas). Texto corto en español, con €/kWh y coma decimal, que
se lea de un vistazo en una notificación del móvil.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal

from src.services.best_hours import Window, best_window, cheapest_hours
from src.utils.calendar import market_timezone

WINDOW_HOURS = 2
TOP_HOURS = 3
WEEKDAYS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MONTHS = [
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
]
MODEL_NAMES = {
    "lightgbm": "LightGBM",
    "precio_ayer": 'respaldo "precio de ayer"',
    "media_7_dias": 'respaldo "media 7 días"',
}


@dataclass(frozen=True)
class Digest:
    day: date
    mean_price: float  # €/MWh
    cheapest_window: Window
    priciest_window: Window
    cheapest_hours: list[datetime]  # UTC, de más barata a más cara
    priciest_hours: list[datetime]  # UTC, de más cara a más barata
    change_vs_previous: float | None  # fracción (0,12 = un 12 % más cara); None si no hay día anterior
    title: str
    body: str

    @property
    def text(self) -> str:
        return f"{self.title}\n{self.body}"


def kwh(price_mwh: float) -> str:
    """€/MWh -> texto en €/kWh con coma decimal y redondeo comercial: 72.5 -> '0,073'.

    Se usa Decimal porque, en coma flotante, 0,0725 queda justo por debajo y se
    redondearía hacia abajo.
    """
    value = (Decimal(str(price_mwh)) / 1000).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    return f"{value:.3f}".replace(".", ",")


def _local_hour(ts: datetime) -> int:
    return ts.astimezone(market_timezone()).hour


def _hour_range(window: Window) -> str:
    return f"{_local_hour(window.start)}–{_local_hour(window.end)} h"


def _day_name(day: date) -> str:
    return f"{WEEKDAYS[day.weekday()]} {day.day} de {MONTHS[day.month - 1]}"


def build_digest(
    prices: Iterable[tuple[datetime, float]],
    day: date,
    source: str,
    model: str | None = None,
    previous_day_prices: Iterable[tuple[datetime, float]] | None = None,
) -> Digest:
    """Resumen de los precios (€/MWh por hora) de `day`.

    `source` es "published" (precios de REE) o "forecast" (previsión, con su `model`).
    Si se dan los precios del día anterior, se compara la media con la de ese día.
    """
    if source not in ("published", "forecast"):
        raise ValueError(f"Fuente desconocida: {source!r} (debe ser 'published' o 'forecast')")
    rows = sorted((ts.astimezone(UTC), float(p)) for ts, p in prices)
    if not rows:
        raise ValueError(f"No hay precios del {day}")

    mean = sum(p for _, p in rows) / len(rows)
    cheapest = best_window(rows, WINDOW_HOURS)
    priciest = best_window([(ts, -p) for ts, p in rows], WINDOW_HOURS)
    priciest = Window(priciest.start, priciest.end, priciest.hours, -priciest.avg_price)
    cheap_hours = [ts for ts, _ in cheapest_hours(rows, TOP_HOURS)]
    pricy_hours = [ts for ts, _ in cheapest_hours([(ts, -p) for ts, p in rows], TOP_HOURS)]

    change = None
    if previous_day_prices is not None:
        previous = [float(p) for _, p in previous_day_prices]
        if previous and sum(previous) > 0:
            change = mean / (sum(previous) / len(previous)) - 1

    title = f"Luz el {_day_name(day)}: media {kwh(mean)} €/kWh"
    lines = [
        f"Más barata: {_hour_range(cheapest)} ({kwh(cheapest.avg_price)} €/kWh)",
        f"Más cara: {_hour_range(priciest)} ({kwh(priciest.avg_price)} €/kWh)",
        f"Mejores horas: {', '.join(f'{_local_hour(h)} h' for h in cheap_hours)}"
        f" · Evita: {', '.join(f'{_local_hour(h)} h' for h in pricy_hours)}",
    ]
    if change is not None and abs(change) >= 0.005:
        direction = "cara" if change > 0 else "barata"
        lines.append(f"Un {abs(change) * 100:.0f} % más {direction} que el día anterior.")
    elif change is not None:
        lines.append("Similar al día anterior.")
    if source == "published":
        lines.append("Precios publicados por REE.")
    else:
        lines.append(f"Previsión de luzPreddict ({MODEL_NAMES.get(model, model or 'modelo desconocido')}).")

    return Digest(
        day=day,
        mean_price=mean,
        cheapest_window=cheapest,
        priciest_window=priciest,
        cheapest_hours=cheap_hours,
        priciest_hours=pricy_hours,
        change_vs_previous=change,
        title=title,
        body="\n".join(lines),
    )
