"""Respuesta de /api/model (uso interno de la web: página "Modelo")."""

import datetime as dt
from typing import Any

from pydantic import BaseModel, Field


class ModelInfo(BaseModel):
    version: str
    trained_at: dt.datetime
    train_start: dt.datetime = Field(description="Primera hora con la que se entrenó")
    train_end: dt.datetime = Field(description="Última hora con la que se entrenó")
    training_rows: int
    features: list[str]
    params: dict[str, Any] = Field(description="Hiperparámetros de LightGBM")
    library_versions: dict[str, str]


class ModelMetrics(BaseModel):
    model: str = Field(description='"lightgbm" o el nombre de una referencia')
    label: str = Field(description="Nombre para mostrar")
    is_baseline: bool
    mae: float = Field(description="Error absoluto medio, en €/MWh")
    rmse: float
    bias: float = Field(description="Error medio con signo (negativo: la previsión se queda corta)")


class IntervalMetrics(BaseModel):
    level: float = Field(description="Cobertura anunciada del intervalo (0.8: 8 de cada 10 horas)")
    coverage: float = Field(description="Parte de las horas en que el precio real quedó dentro del intervalo")
    width: float = Field(description="Anchura media del intervalo, en €/MWh")


class Backtest(BaseModel):
    start: dt.date
    end: dt.date
    days: int
    method: str = Field(description="Cómo se midió")
    models: list[ModelMetrics] = Field(description="De menor a mayor error")
    improvement_pct: float | None = Field(description="Cuánto menos se equivoca LightGBM que la mejor referencia, en %")
    interval: IntervalMetrics | None = Field(description="Intervalo de predicción de LightGBM (None si no lo tiene)")


class DailyErrorOut(BaseModel):
    date: dt.date
    model: str = Field(description="Modelo que hizo la previsión publicada ese día")
    mae: float
    rmse: float
    bias: float


class LiveErrors(BaseModel):
    start: dt.date
    end: dt.date
    days: list[DailyErrorOut]
    mae: float | None = Field(description="Error absoluto medio de los días con previsión")
    fallback_days: int = Field(description="Días en que se usó una referencia porque el modelo no estaba disponible")


class ModelReport(BaseModel):
    model: ModelInfo
    backtest: Backtest | None = Field(description="Métricas del entrenamiento (None en modelos sin métricas)")
    live: LiveErrors = Field(description="Error real de las previsiones publicadas")
