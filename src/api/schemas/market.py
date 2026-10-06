import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field

from src.api.schemas.common import Source, generation_source


class TechnologyShare(BaseModel):
    technology: str = Field(description="Nombre de la tecnología según REE")
    mwh: float
    pct: float | None = Field(description="% del total generado en el periodo")
    renewable: bool


class MarketDay(BaseModel):
    date: dt.date
    total_mwh: float
    renewable_mwh: float
    renewable_pct: float | None = Field(description="% de la generación que fue renovable")
    provisional: bool = Field(description="Datos de hoy: REE los actualiza hasta que acaba el día")
    mix: dict[str, float] = Field(description="MWh por tecnología, de mayor a menor")


class Market(BaseModel):
    start: dt.date
    end: dt.date
    unit: Literal["MWh"] = "MWh"
    renewable_pct: float | None = Field(description="% renovable de todo el periodo")
    technologies: list[TechnologyShare] = Field(description="Mix acumulado del periodo, de mayor a menor")
    missing_days: list[dt.date] = Field(description="Días del rango sin datos de generación")
    days: list[MarketDay]
    source: Source = generation_source()
