"""/api/model: el modelo en uso, su backtest y su error real (uso interno de la web)."""

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.cache import cache_until_refresh
from src.api.deps import MAX_HISTORY_DAYS, NowDep, SessionDep, today
from src.api.errors import error_responses
from src.api.schemas.model import Backtest, DailyErrorOut, LiveErrors, ModelInfo, ModelMetrics, ModelReport
from src.db import repository
from src.db.models import ModelArtifact
from src.utils.calendar import market_timezone

MODEL = "lightgbm"
LABELS = {MODEL: "LightGBM", "precio_ayer": "Precio de ayer", "media_7_dias": "Media 7 días"}
BACKTEST_METHOD = (
    "Walk-forward: cada día se predice solo con los días anteriores, como en producción, "
    "y se compara con el precio publicado por REE."
)

router = APIRouter(prefix="/api/model", tags=["Previsión"], dependencies=[Depends(cache_until_refresh)])


def build_backtest(metrics: dict) -> Backtest | None:
    """Métricas guardadas al entrenar (ver `src.models.train.train_final_model`)."""
    period, models = metrics.get("period"), metrics.get("models")
    if not period or not models:
        return None
    rows = sorted(
        (
            ModelMetrics(
                model=name,
                label=LABELS.get(name, name),
                is_baseline=name != MODEL,
                mae=values["mae"],
                rmse=values["rmse"],
                bias=values["bias"],
            )
            for name, values in models.items()
        ),
        key=lambda m: (m.mae, m.model),
    )
    model = next((m for m in rows if not m.is_baseline), None)
    baselines = [m for m in rows if m.is_baseline]
    improvement = None
    if model and baselines and baselines[0].mae > 0:
        improvement = round((baselines[0].mae - model.mae) / baselines[0].mae * 100, 1)
    return Backtest(
        start=period["start"],
        end=period["end"],
        days=period["days"],
        method=BACKTEST_METHOD,
        models=rows,
        improvement_pct=improvement,
    )


def _model_info(artifact: ModelArtifact) -> ModelInfo:
    tz = market_timezone()
    return ModelInfo(
        version=artifact.version,
        trained_at=artifact.trained_at.astimezone(tz),
        train_start=artifact.train_start.astimezone(tz),
        train_end=artifact.train_end.astimezone(tz),
        training_rows=artifact.training_rows,
        features=artifact.features,
        params=artifact.params,
        library_versions=artifact.library_versions,
    )


@router.get(
    "",
    summary="Modelo en uso, backtest y error real",
    description=(
        "Datos del modelo entrenado más recientemente, sus métricas frente a las referencias "
        "y el error de las previsiones publicadas en los últimos `days` días."
    ),
    responses=error_responses(404, 422),
)
def get_model(
    session: SessionDep,
    now: NowDep,
    days: Annotated[int, Query(ge=1, le=MAX_HISTORY_DAYS, description="Días de error real")] = 30,
) -> ModelReport:
    artifact = repository.get_model_artifact(session, include_data=False)
    if artifact is None:
        raise HTTPException(404, "Todavía no hay ningún modelo entrenado")

    # Hasta mañana: en cuanto REE publica (hacia las 20:15), la previsión de mañana ya se puede evaluar
    end = today(now) + timedelta(days=1)
    start = end - timedelta(days=days - 1)
    errors = repository.get_daily_errors(session, start, end)
    return ModelReport(
        model=_model_info(artifact),
        backtest=build_backtest(artifact.metrics or {}),
        live=LiveErrors(
            start=start,
            end=end,
            days=[
                DailyErrorOut(
                    date=e.day, model=e.model, mae=round(e.mae, 2), rmse=round(e.rmse, 2), bias=round(e.bias, 2)
                )
                for e in errors
            ],
            mae=round(sum(e.mae for e in errors) / len(errors), 2) if errors else None,
            fallback_days=sum(1 for e in errors if e.model != MODEL),
        ),
    )
