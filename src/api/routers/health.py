"""/health: frescura de los datos y modelo en uso.

Responde 200 aunque haya avisos (`status: degraded`), para que la web pueda
mostrarlos; si la base de datos no responde, 503 con el formato de error común.
"""

from datetime import datetime, timedelta

from fastapi import APIRouter

from src.api.deps import NowDep, SessionDep
from src.api.errors import error_responses
from src.api.schemas.health import ForecastStatus, Health, ModelStatus, PricesStatus
from src.db import repository
from src.db.models import ModelArtifact, ModelRun
from src.utils.calendar import local_date, market_timezone

# El modelo se reentrena cada semana: con el doble de margen se da por desactualizado
MAX_MODEL_AGE_DAYS = 14

router = APIRouter(tags=["Estado"])


def build_health(
    now: datetime, last_price: datetime | None, run: ModelRun | None, artifact: ModelArtifact | None
) -> Health:
    tz = market_timezone()
    today = local_date(now, tz)
    tomorrow = today + timedelta(days=1)
    warnings: list[str] = []

    last_day = local_date(last_price, tz) if last_price else None
    if last_day is None:
        warnings.append("No hay precios en la base de datos")
    elif last_day < today:
        warnings.append(f"El último precio es del {last_day.isoformat()}: faltan los de hoy")

    forecast = None
    if run is None:
        warnings.append("Todavía no hay ninguna previsión")
    else:
        forecast = ForecastStatus(
            target_day=run.target_day,
            generated_at=run.generated_at.astimezone(tz),
            model=run.model,
            model_version=run.model_version,
            fallback_reason=run.fallback_reason,
        )
        if run.target_day < tomorrow:
            warnings.append(f"La última previsión es para el {run.target_day.isoformat()}: no hay previsión de mañana")
        if run.fallback_reason:
            warnings.append(f"La última previsión usa la referencia {run.model}: {run.fallback_reason}")

    model = None
    if artifact is None:
        warnings.append("No hay ningún modelo entrenado")
    else:
        age_days = (now - artifact.trained_at).days
        model = ModelStatus(
            version=artifact.version,
            trained_at=artifact.trained_at.astimezone(tz),
            train_end=artifact.train_end.astimezone(tz),
            training_rows=artifact.training_rows,
            age_days=age_days,
        )
        if age_days > MAX_MODEL_AGE_DAYS:
            warnings.append(f"El modelo tiene {age_days} días: el reentrenamiento semanal no se está ejecutando")

    return Health(
        status="degraded" if warnings else "ok",
        checked_at=now.astimezone(tz),
        warnings=warnings,
        prices=PricesStatus(
            last_hour=last_price.astimezone(tz) if last_price else None,
            last_day=last_day,
            has_tomorrow=last_day is not None and last_day >= tomorrow,
        ),
        forecast=forecast,
        model=model,
    )


@router.get(
    "/health",
    summary="Estado del servicio",
    description="Última hora con precio, última previsión y modelo en uso, con avisos si algo está desactualizado.",
    responses=error_responses(503),
)
def health(session: SessionDep, now: NowDep) -> Health:
    return build_health(
        now,
        repository.last_price_datetime(session),
        repository.latest_model_run(session),
        repository.get_model_artifact(session, include_data=False),
    )
