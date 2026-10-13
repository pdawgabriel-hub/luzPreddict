import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field

from src.api.schemas.common import FORECAST_DISCLAIMER, Source, pvpc_source
from src.utils.calendar import TariffPeriod

Unit = Literal["€/MWh"]


class PriceHour(BaseModel):
    datetime: dt.datetime = Field(description="Inicio de la hora, en hora de Madrid")
    price: float = Field(description="PVPC en €/MWh")
    period: TariffPeriod = Field(description="Periodo de la tarifa 2.0TD")


class Prices(BaseModel):
    start: dt.date
    end: dt.date
    unit: Unit = "€/MWh"
    missing_days: list[dt.date] = Field(description="Días del rango sin todas sus horas publicadas")
    hours: list[PriceHour]
    source: Source = pvpc_source()


class ForecastHour(BaseModel):
    datetime: dt.datetime = Field(description="Inicio de la hora, en hora de Madrid")
    price: float = Field(description="Precio previsto en €/MWh")
    lower: float | None = Field(description="Límite inferior del intervalo de predicción (null sin intervalo)")
    upper: float | None = Field(description="Límite superior del intervalo de predicción (null sin intervalo)")
    period: TariffPeriod = Field(description="Periodo de la tarifa 2.0TD")
    actual: float | None = Field(description="Precio publicado por REE, si ya se conoce")


class Forecast(BaseModel):
    date: dt.date
    generated_at: dt.datetime
    model: str = Field(description='"lightgbm" o la referencia usada como respaldo')
    model_version: str | None
    fallback_reason: str | None = Field(description="Por qué se usó la referencia en lugar del modelo")
    unit: Unit = "€/MWh"
    mae: float | None = Field(description="Error absoluto medio frente al precio real, cuando ya está publicado entero")
    interval_level: float | None = Field(
        description=(
            "Parte de las horas en que el precio real quedó entre `lower` y `upper` al medir el modelo "
            "(0.8: 8 de cada 10). Null si la previsión no tiene intervalo, como la de respaldo"
        )
    )
    hours: list[ForecastHour]
    source: Source = pvpc_source()
    disclaimer: str = Field(default=FORECAST_DISCLAIMER, description="Aviso: la previsión es orientativa")


class Window(BaseModel):
    start: dt.datetime = Field(description="Inicio de la primera hora, en hora de Madrid")
    end: dt.datetime = Field(description="Fin de la última hora")
    avg_price: float = Field(description="Precio medio de la ventana en €/MWh")


class BestHours(BaseModel):
    date: dt.date
    hours: int = Field(description="Duración pedida, en horas")
    from_hour: int
    to_hour: int
    unit: Unit = "€/MWh"
    window: Window = Field(description="Las horas seguidas más baratas dentro de la franja")
    cheapest: list[PriceHour] = Field(description="Las horas más baratas de la franja, aunque no sean seguidas")
    day_avg_price: float = Field(description="Precio medio de todo el día")
    saving_pct: float | None = Field(
        description="Cuánto más barata es la ventana que la media del día, en % (negativo si es más cara)"
    )
    source: Source = pvpc_source()


class ForecastError(BaseModel):
    model: str
    mae: float = Field(description="Error absoluto medio en €/MWh")


class DaySummary(BaseModel):
    date: dt.date
    avg_price: float
    min_price: float
    min_hour: dt.datetime = Field(description="Hora más barata")
    max_price: float
    max_hour: dt.datetime = Field(description="Hora más cara")
    complete: bool = Field(description="Si el día tiene todas sus horas publicadas")
    forecast: ForecastError | None = Field(description="Error de la previsión de ese día, si la hubo")


class History(BaseModel):
    start: dt.date
    end: dt.date
    unit: Unit = "€/MWh"
    missing_days: list[dt.date] = Field(description="Días del rango sin todas sus horas publicadas")
    days: list[DaySummary]
    source: Source = pvpc_source()
