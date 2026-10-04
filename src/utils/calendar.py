"""Calendario del mercado eléctrico peninsular.

Utilidades sin dependencias externas (solo librería estándar), porque las
usan tanto el pipeline como la API:

- Días locales de 23, 24 o 25 horas por los cambios de hora.
- Festivos nacionales (variable del modelo) y festivos de la tarifa 2.0TD.
- Periodos punta, llano y valle de la tarifa 2.0TD.

Todas las funciones que reciben un instante exigen datetimes con zona horaria.
"""

from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from functools import lru_cache
from zoneinfo import ZoneInfo

from src.utils.config import get_settings

# Festivos nacionales de fecha fija, como (mes, día)
_FIXED_NATIONAL_HOLIDAYS = ((1, 1), (1, 6), (5, 1), (8, 15), (10, 12), (11, 1), (12, 6), (12, 8), (12, 25))


class TariffPeriod(StrEnum):
    PUNTA = "punta"
    LLANO = "llano"
    VALLE = "valle"


def market_timezone() -> ZoneInfo:
    return ZoneInfo(get_settings().timezone)


def _require_aware(ts: datetime) -> None:
    if ts.tzinfo is None or ts.utcoffset() is None:
        raise ValueError("Se necesita un datetime con zona horaria")


def local_date(ts: datetime, tz: ZoneInfo | None = None) -> date:
    """Día local al que pertenece un instante."""
    _require_aware(ts)
    return ts.astimezone(tz or market_timezone()).date()


def local_day_hours(day: date, tz: ZoneInfo | None = None) -> list[datetime]:
    """Inicio (en UTC) de cada hora del día local `day`.

    Devuelve 23 horas el día del cambio a horario de verano y 25 el del
    cambio a horario de invierno.
    """
    tz = tz or market_timezone()
    start = datetime.combine(day, time(0), tzinfo=tz).astimezone(UTC)
    end = datetime.combine(day + timedelta(days=1), time(0), tzinfo=tz).astimezone(UTC)
    n_hours = (end - start) // timedelta(hours=1)
    return [start + timedelta(hours=i) for i in range(n_hours)]


def hours_in_day(day: date, tz: ZoneInfo | None = None) -> int:
    return len(local_day_hours(day, tz))


def is_weekend(day: date) -> bool:
    return day.weekday() >= 5


def easter_sunday(year: int) -> date:
    """Domingo de Pascua (algoritmo anónimo gregoriano)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    month, day = divmod(h + l_ - 7 * m + 114, 31)
    return date(year, month, day + 1)


@lru_cache
def national_holidays(year: int) -> frozenset[date]:
    """Festivos comunes a toda España: los de fecha fija más Viernes Santo.

    No incluye festivos autonómicos ni locales.
    """
    fixed = {date(year, m, d) for m, d in _FIXED_NATIONAL_HOLIDAYS}
    return frozenset(fixed | {easter_sunday(year) - timedelta(days=2)})


@lru_cache
def tariff_holidays(year: int) -> frozenset[date]:
    """Festivos que cuentan como valle en la tarifa 2.0TD.

    La CNMC solo considera los nacionales de fecha fija, así que Viernes
    Santo no está incluido.
    """
    return frozenset(date(year, m, d) for m, d in _FIXED_NATIONAL_HOLIDAYS)


def is_national_holiday(day: date) -> bool:
    return day in national_holidays(day.year)


def tariff_period(ts: datetime, tz: ZoneInfo | None = None) -> TariffPeriod:
    """Periodo 2.0TD (península) de la hora que empieza en `ts`.

    Laborables: punta 10-14 h y 18-22 h, llano 8-10 h, 14-18 h y 22-24 h,
    valle 0-8 h. Fines de semana y festivos de la tarifa: todo valle.
    """
    _require_aware(ts)
    local = ts.astimezone(tz or market_timezone())
    if is_weekend(local.date()) or local.date() in tariff_holidays(local.year):
        return TariffPeriod.VALLE
    hour = local.hour
    if hour < 8:
        return TariffPeriod.VALLE
    if 10 <= hour < 14 or 18 <= hour < 22:
        return TariffPeriod.PUNTA
    return TariffPeriod.LLANO
