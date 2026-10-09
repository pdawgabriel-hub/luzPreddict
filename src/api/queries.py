"""Consultas de precios compartidas por las rutas públicas y las herramientas."""

from datetime import date, datetime, time, timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from src.api.deps import DayRange, check_day, today
from src.db import repository
from src.utils.calendar import hours_in_day, market_timezone


def local_hour(day: date, hour: int) -> datetime:
    """Hora de reloj de un día en Madrid; 24 es la medianoche siguiente."""
    return datetime.combine(day + timedelta(days=hour // 24), time(hour % 24), tzinfo=market_timezone())


def no_prices(days: DayRange, now: datetime) -> HTTPException:
    """404 cuando no hay ningún precio en los días pedidos."""
    if days.start == days.end == today(now) + timedelta(days=1):
        message = f"REE aún no ha publicado los precios del {days.start.isoformat()} (lo hace hacia las 20:15)"
        return HTTPException(404, message)
    if days.start == days.end:
        return HTTPException(404, f"No hay precios del {days.start.isoformat()}")
    return HTTPException(404, f"No hay precios entre el {days.start.isoformat()} y el {days.end.isoformat()}")


def range_prices(session: Session, days: DayRange) -> list[tuple[datetime, float]]:
    return repository.get_prices(session, days.utc_start, days.utc_end)


def day_prices(
    session: Session, now: datetime, day: date | None, field: str = "date", location: str = "query"
) -> tuple[date, list[tuple[datetime, float]]]:
    """Precios de un día. Sin día, mañana si REE ya lo publicó entero y, si no, hoy.

    Valida el día (422 en `field`) y da 404 si no tiene ningún precio.
    """
    tomorrow = today(now) + timedelta(days=1)
    if day is None:
        rows = range_prices(session, DayRange(tomorrow, tomorrow))
        if len(rows) == hours_in_day(tomorrow):
            return tomorrow, rows
        day = today(now)
    else:
        check_day(field, day, tomorrow, location)
    rows = range_prices(session, DayRange(day, day))
    if not rows:
        raise no_prices(DayRange(day, day), now)
    return day, rows
