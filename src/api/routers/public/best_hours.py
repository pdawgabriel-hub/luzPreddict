"""/v1/best-hours: cuándo consumir para pagar menos."""

from datetime import date, datetime, time, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from src.api.deps import DayRange, NowDep, SessionDep, check_day, invalid_query, today
from src.api.errors import error_responses
from src.api.routers.public.prices import no_prices
from src.api.schemas.prices import BestHours, PriceHour, Window
from src.db import repository
from src.services.best_hours import best_window, cheapest_hours
from src.utils.calendar import hours_in_day, market_timezone, tariff_period

router = APIRouter(tags=["Precios"])


def _local_hour(day: date, hour: int) -> datetime:
    """Hora de reloj de un día; 24 es la medianoche siguiente."""
    tz = market_timezone()
    return datetime.combine(day + timedelta(days=hour // 24), time(hour % 24), tzinfo=tz)


def _prices_of(session: SessionDep, day: date) -> list[tuple[datetime, float]]:
    days = DayRange(day, day)
    return repository.get_prices(session, days.utc_start, days.utc_end)


@router.get(
    "/best-hours",
    summary="Mejores horas para consumir",
    description=(
        "Las `hours` horas seguidas más baratas de un día, opcionalmente dentro de una franja "
        "(`from_hour` a `to_hour`, en hora de Madrid), y las horas más baratas sueltas. "
        "Sin `date`, usa mañana si REE ya lo publicó y, si no, hoy."
    ),
    responses=error_responses(404, 422),
)
def get_best_hours(
    session: SessionDep,
    now: NowDep,
    hours: Annotated[int, Query(ge=1, le=24, description="Duración del consumo, en horas")] = 1,
    day: Annotated[date | None, Query(alias="date", description="Día (por defecto, el último publicado)")] = None,
    from_hour: Annotated[int, Query(ge=0, le=23, description="Primera hora de la franja")] = 0,
    to_hour: Annotated[int, Query(ge=1, le=24, description="Hora a la que debe haber terminado")] = 24,
) -> BestHours:
    if to_hour <= from_hour:
        invalid_query("to_hour", "to_hour debe ser posterior a from_hour")
    if hours > to_hour - from_hour:
        invalid_query("hours", f"No caben {hours} horas entre las {from_hour}:00 y las {to_hour}:00")

    tomorrow = today(now) + timedelta(days=1)
    if day is None:
        rows = _prices_of(session, tomorrow)
        day = tomorrow if len(rows) == hours_in_day(tomorrow) else today(now)
        if day != tomorrow:
            rows = _prices_of(session, day)
    else:
        check_day("date", day, tomorrow)
        rows = _prices_of(session, day)
    if not rows:
        raise no_prices(DayRange(day, day), now)

    not_before, end_by = _local_hour(day, from_hour), _local_hour(day, to_hour)
    window = best_window(rows, hours, not_before=not_before, end_by=end_by)
    if window is None:
        raise HTTPException(404, f"No hay {hours} horas seguidas con precio publicado en esa franja")

    tz = market_timezone()
    in_range = [(ts, p) for ts, p in rows if not_before <= ts < end_by]
    day_avg = sum(p for _, p in rows) / len(rows)
    return BestHours(
        date=day,
        hours=hours,
        from_hour=from_hour,
        to_hour=to_hour,
        window=Window(
            start=window.start.astimezone(tz), end=window.end.astimezone(tz), avg_price=round(window.avg_price, 2)
        ),
        cheapest=[
            PriceHour(datetime=ts.astimezone(tz), price=p, period=tariff_period(ts, tz))
            for ts, p in cheapest_hours(in_range, hours)
        ],
        day_avg_price=round(day_avg, 2),
        saving_pct=round((day_avg - window.avg_price) / day_avg * 100, 1) if day_avg > 0 else None,
    )
