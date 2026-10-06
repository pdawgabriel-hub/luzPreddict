"""/v1/history: resumen diario del PVPC."""

from collections import defaultdict
from datetime import date, datetime

from fastapi import APIRouter

from src.api.deps import HistoryRangeDep, NowDep, SessionDep
from src.api.errors import error_responses
from src.api.routers.public.prices import no_prices
from src.api.schemas.prices import DaySummary, ForecastError, History
from src.db import repository
from src.utils.calendar import hours_in_day, local_date, market_timezone

router = APIRouter(tags=["Precios"])


@router.get(
    "/history",
    summary="Resumen diario",
    description=(
        "Media, mínimo y máximo de cada día, con el error de la previsión de ese día. "
        "Por defecto, los últimos 30 días; hasta un año por petición."
    ),
    responses=error_responses(404, 422),
)
def get_history(days: HistoryRangeDep, session: SessionDep, now: NowDep) -> History:
    rows = repository.get_prices(session, days.utc_start, days.utc_end)
    if not rows:
        raise no_prices(days, now)

    tz = market_timezone()
    by_day: dict[date, list[tuple[datetime, float]]] = defaultdict(list)
    for ts, price in rows:
        by_day[local_date(ts, tz)].append((ts, price))
    errors = {e.day: e for e in repository.get_daily_errors(session, days.start, days.end)}

    summaries = []
    for day, hours in sorted(by_day.items()):
        cheapest = min(hours, key=lambda r: (r[1], r[0]))
        dearest = max(hours, key=lambda r: (r[1], -r[0].timestamp()))  # con empate, la más temprana
        error = errors.get(day)
        summaries.append(
            DaySummary(
                date=day,
                avg_price=round(sum(p for _, p in hours) / len(hours), 2),
                min_price=cheapest[1],
                min_hour=cheapest[0].astimezone(tz),
                max_price=dearest[1],
                max_hour=dearest[0].astimezone(tz),
                complete=len(hours) == hours_in_day(day, tz),
                forecast=ForecastError(model=error.model, mae=round(error.mae, 2)) if error else None,
            )
        )
    return History(
        start=days.start,
        end=days.end,
        missing_days=[d for d in days.days if d not in by_day or len(by_day[d]) < hours_in_day(d, tz)],
        days=summaries,
    )
