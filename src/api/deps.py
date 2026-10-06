"""Dependencias comunes de las rutas.

En los tests se sustituyen con `app.dependency_overrides` (sesión de la base de
pruebas, hora fija).
"""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, NoReturn

from fastapi import Depends, Query
from fastapi.exceptions import RequestValidationError
from sqlalchemy.orm import Session

from src.db.session import session_scope
from src.utils.calendar import local_date, local_day_hours
from src.utils.config import get_settings

# Máximo de días por petición en las consultas por rango
MAX_RANGE_DAYS = 31


def get_session() -> Iterator[Session]:
    """Una sesión por petición, con su propia conexión (NullPool)."""
    with session_scope() as session:
        yield session


def get_now() -> datetime:
    """Hora actual en UTC."""
    return datetime.now(UTC)


SessionDep = Annotated[Session, Depends(get_session)]
NowDep = Annotated[datetime, Depends(get_now)]


def today(now: datetime) -> date:
    """Día local de Madrid."""
    return local_date(now)


def invalid_query(field: str, message: str) -> NoReturn:
    """Error 422 con el mismo formato que la validación automática."""
    raise RequestValidationError([{"loc": ("query", field), "msg": message, "type": "value_error"}])


def check_day(field: str, day: date, last_allowed: date) -> None:
    first_allowed = get_settings().history_start
    if day < first_allowed:
        invalid_query(field, f"No hay datos antes del {first_allowed.isoformat()}")
    if day > last_allowed:
        invalid_query(field, f"La fecha no puede ser posterior al {last_allowed.isoformat()}")


@dataclass(frozen=True)
class DayRange:
    start: date
    end: date  # incluido

    @property
    def days(self) -> list[date]:
        return [self.start + timedelta(days=i) for i in range((self.end - self.start).days + 1)]

    @property
    def utc_start(self) -> datetime:
        return local_day_hours(self.start)[0]

    @property
    def utc_end(self) -> datetime:
        """Fin del último día (excluido)."""
        return local_day_hours(self.end)[-1] + timedelta(hours=1)


def price_range(
    now: NowDep,
    day: Annotated[date | None, Query(alias="date", description="Un día (por defecto, hoy)")] = None,
    start: Annotated[date | None, Query(description="Primer día del rango")] = None,
    end: Annotated[date | None, Query(description=f"Último día, incluido (máximo {MAX_RANGE_DAYS} días)")] = None,
) -> DayRange:
    """Días pedidos con `date` o con `start` y `end`, hasta mañana (lo último que publica REE)."""
    tomorrow = today(now) + timedelta(days=1)
    if day is not None:
        if start is not None or end is not None:
            invalid_query("date", "Usa date o start/end, no ambos")
        check_day("date", day, tomorrow)
        return DayRange(day, day)
    if start is None and end is None:
        return DayRange(today(now), today(now))
    if start is None or end is None:
        invalid_query("start" if start is None else "end", "Hay que indicar start y end")
    check_day("start", start, tomorrow)
    check_day("end", end, tomorrow)
    if end < start:
        invalid_query("end", "end no puede ser anterior a start")
    if (end - start).days + 1 > MAX_RANGE_DAYS:
        invalid_query("end", f"El rango no puede superar {MAX_RANGE_DAYS} días")
    return DayRange(start, end)


PriceRangeDep = Annotated[DayRange, Depends(price_range)]
