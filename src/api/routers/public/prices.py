"""/v1/prices: PVPC publicado por REE."""

from collections import Counter
from datetime import timedelta

from fastapi import APIRouter, HTTPException

from src.api.deps import NowDep, PriceRangeDep, SessionDep, today
from src.api.errors import error_responses
from src.api.schemas.prices import PriceHour, Prices
from src.db import repository
from src.utils.calendar import hours_in_day, local_date, market_timezone, tariff_period

router = APIRouter(tags=["Precios"])


@router.get(
    "/prices",
    summary="Precios por día o rango",
    description=(
        "PVPC hora a hora de un día (`date`) o de un rango (`start` y `end`), hasta mañana si REE ya lo publicó."
    ),
    responses=error_responses(404, 422),
)
def get_prices(days: PriceRangeDep, session: SessionDep, now: NowDep) -> Prices:
    rows = repository.get_prices(session, days.utc_start, days.utc_end)
    if not rows:
        if days.start == days.end == today(now) + timedelta(days=1):
            message = f"REE aún no ha publicado los precios del {days.start.isoformat()} (lo hace hacia las 20:15)"
            raise HTTPException(404, message)
        raise HTTPException(404, f"No hay precios entre el {days.start.isoformat()} y el {days.end.isoformat()}")

    tz = market_timezone()
    per_day = Counter(local_date(ts, tz) for ts, _ in rows)
    return Prices(
        start=days.start,
        end=days.end,
        missing_days=[d for d in days.days if per_day[d] < hours_in_day(d, tz)],
        hours=[PriceHour(datetime=ts.astimezone(tz), price=price, period=tariff_period(ts, tz)) for ts, price in rows],
    )
