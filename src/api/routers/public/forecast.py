"""/v1/forecast: previsión del PVPC guardada por el pipeline."""

from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from src.api.deps import NowDep, SessionDep, check_day, today
from src.api.errors import error_responses
from src.api.schemas.prices import Forecast, ForecastHour
from src.db import repository
from src.utils.calendar import market_timezone, tariff_period

# Los precios de REE vienen con 2 decimales: más precisión en la previsión sería ruido
DECIMALS = 2

router = APIRouter(tags=["Previsión"])


@router.get(
    "/forecast",
    summary="Previsión de un día",
    description=(
        "Última previsión generada para `date`; sin `date`, la más reciente. "
        "Si REE ya publicó ese día, cada hora incluye el precio real y el error medio."
    ),
    responses=error_responses(404, 422),
)
def get_forecast(
    session: SessionDep,
    now: NowDep,
    day: Annotated[date | None, Query(alias="date", description="Día previsto (por defecto, el más reciente)")] = None,
) -> Forecast:
    if day is None:
        latest = repository.latest_model_run(session)
        if latest is None:
            raise HTTPException(404, "Todavía no hay ninguna previsión")
        day = latest.target_day
    else:
        # El pipeline prevé el primer día sin precio publicado: como mucho, pasado mañana
        check_day("date", day, today(now) + timedelta(days=2))

    run = repository.latest_forecast(session, day)
    if run is None:
        raise HTTPException(404, f"No hay previsión para el {day.isoformat()}")

    hours = sorted(run.hours, key=lambda h: h.datetime)
    actual = dict(repository.get_prices(session, hours[0].datetime, hours[-1].datetime + timedelta(hours=1)))
    tz = market_timezone()
    errors = [abs(h.prediction - actual[h.datetime]) for h in hours if h.datetime in actual]
    return Forecast(
        date=run.target_day,
        generated_at=run.generated_at.astimezone(tz),
        model=run.model,
        model_version=run.model_version,
        fallback_reason=run.fallback_reason,
        mae=round(sum(errors) / len(errors), DECIMALS) if len(errors) == len(hours) else None,
        hours=[
            ForecastHour(
                datetime=h.datetime.astimezone(tz),
                price=round(h.prediction, DECIMALS),
                period=tariff_period(h.datetime, tz),
                actual=actual.get(h.datetime),
            )
            for h in hours
        ],
    )
