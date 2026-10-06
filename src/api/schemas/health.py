from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class PricesStatus(BaseModel):
    last_hour: datetime | None = Field(description="Inicio de la última hora con precio publicado")
    last_day: date | None = Field(description="Último día con precio publicado")
    has_tomorrow: bool = Field(description="Si REE ya ha publicado los precios de mañana")


class ForecastStatus(BaseModel):
    target_day: date = Field(description="Día previsto")
    generated_at: datetime
    model: str = Field(description='"lightgbm" o la referencia usada como respaldo')
    model_version: str | None
    fallback_reason: str | None = Field(description="Por qué se usó la referencia en lugar del modelo")


class ModelStatus(BaseModel):
    version: str
    trained_at: datetime
    train_end: datetime = Field(description="Fin del periodo de entrenamiento")
    training_rows: int
    age_days: int = Field(description="Días desde el entrenamiento")


class Health(BaseModel):
    status: Literal["ok", "degraded"] = Field(description='"degraded" si los datos o el modelo están desactualizados')
    checked_at: datetime
    warnings: list[str] = Field(description="Motivos por los que el estado no es ok")
    prices: PricesStatus
    forecast: ForecastStatus | None = Field(description="Última previsión generada")
    model: ModelStatus | None = Field(description="Modelo en uso: el entrenado más recientemente")
