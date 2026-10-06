"""Atribución de los datos y aviso de la previsión, comunes a las respuestas de /v1."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

REE_NAME = "Red Eléctrica (REE)"
REE_URL = "https://www.ree.es/es/apidatos"

FORECAST_DISCLAIMER = (
    "Previsión orientativa calculada por luzPreddict con datos de REE: "
    "no es un precio oficial ni garantiza el precio final."
)


class Source(BaseModel):
    """De dónde salen los datos de la respuesta."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(default=REE_NAME, description="Organismo que publica los datos")
    url: str = Field(default=REE_URL, description="API pública de la que se descargan")
    series: str = Field(description="Serie de datos de REE")


PVPC_SOURCE = Source(series="PVPC 2.0TD")
GENERATION_SOURCE = Source(series="Estructura de la generación")


def pvpc_source() -> Any:
    return Field(default=PVPC_SOURCE, description="Fuente de los datos")


def generation_source() -> Any:
    return Field(default=GENERATION_SOURCE, description="Fuente de los datos")
