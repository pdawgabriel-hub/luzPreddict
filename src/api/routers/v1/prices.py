"""/v1/prices: PVPC publicado por REE."""

from collections import Counter

from fastapi import APIRouter

from src.api.deps import NowDep, PriceRangeDep, SessionDep
from src.api.errors import error_responses
from src.api.queries import no_prices, range_prices
from src.api.schemas.prices import PriceHour, Prices
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
    rows = range_prices(session, days)
    if not rows:
        raise no_prices(days, now)

    tz = market_timezone()
    per_day = Counter(local_date(ts, tz) for ts, _ in rows)
    return Prices(
        start=days.start,
        end=days.end,
        missing_days=[d for d in days.days if per_day[d] < hours_in_day(d, tz)],
        hours=[PriceHour(datetime=ts.astimezone(tz), price=price, period=tariff_period(ts, tz)) for ts, price in rows],
    )
