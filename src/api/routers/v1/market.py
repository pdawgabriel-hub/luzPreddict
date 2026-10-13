"""/v1/market: mix de generación y peso renovable."""

from fastapi import APIRouter, HTTPException

from src.api.deps import HistoryRangeDep, NowDep, SessionDep, today
from src.api.errors import error_responses
from src.api.schemas.market import Market, MarketDay, TechnologyShare
from src.db import repository
from src.services.market import daily_mix, period_mix

router = APIRouter(tags=["Mercado"])


def _round(value: float | None, decimals: int = 1) -> float | None:
    return round(value, decimals) if value is not None else None


@router.get(
    "/market",
    summary="Mix de generación",
    description=(
        "Generación diaria por tecnología y % renovable, más el mix acumulado del periodo. "
        "Por defecto, los últimos 30 días; hasta un año por petición."
    ),
    responses=error_responses(404, 422),
)
def get_market(days: HistoryRangeDep, session: SessionDep, now: NowDep) -> Market:
    mixes = daily_mix(repository.get_generation(session, days.start, days.end))
    if not mixes:
        raise HTTPException(
            404, f"No hay datos de generación entre el {days.start.isoformat()} y el {days.end.isoformat()}"
        )

    total = sum(m.total_mwh for m in mixes)
    renewable = sum(m.renewable_mwh for m in mixes)
    present = {m.day for m in mixes}
    return Market(
        start=days.start,
        end=days.end,
        renewable_pct=_round(renewable / total * 100 if total > 0 else None),
        technologies=[
            TechnologyShare(technology=s.technology, mwh=round(s.mwh), pct=_round(s.pct, 2), renewable=s.renewable)
            for s in period_mix(mixes)
        ],
        missing_days=[d for d in days.days if d not in present],
        days=[
            MarketDay(
                date=m.day,
                total_mwh=round(m.total_mwh),
                renewable_mwh=round(m.renewable_mwh),
                renewable_pct=_round(m.renewable_pct),
                provisional=m.day >= today(now),
                mix={tech: round(mwh) for tech, mwh in m.mix.items()},
            )
            for m in mixes
        ],
    )
