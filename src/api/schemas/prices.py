import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field

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


class ForecastHour(BaseModel):
    datetime: dt.datetime = Field(description="Inicio de la hora, en hora de Madrid")
    price: float = Field(description="Precio previsto en €/MWh")
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
    hours: list[ForecastHour]
