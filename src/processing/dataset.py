"""Puente entre la base de datos y pandas para el pipeline.

Las tablas que se leen son idénticas a las de los ficheros parquet de
`src.ingestion` (mismas columnas y tipos), así que la limpieza, las variables y
el modelo funcionan igual con un origen que con otro.

Este módulo usa pandas: es del pipeline. La API trabaja con `src.db.repository`.
"""

from datetime import date, datetime

import pandas as pd
from sqlalchemy.orm import Session

from src.db import repository
from src.ingestion import generation, prices
from src.processing.clean import clean_prices


def load_prices(session: Session, since: datetime | None = None, until: datetime | None = None) -> pd.DataFrame:
    """PVPC guardado (`datetime` en UTC, `price` en €/MWh) con `since <= datetime < until`."""
    rows = repository.get_prices(session, start=since, end=until)
    if not rows:
        return prices.empty_prices()
    return prices.merge_prices(prices.empty_prices(), pd.DataFrame(rows, columns=["datetime", "price"]))


def load_clean_prices(session: Session, since: datetime | None = None, until: datetime | None = None) -> pd.DataFrame:
    """PVPC guardado como serie horaria continua, listo para calcular variables."""
    return clean_prices(load_prices(session, since, until))


def load_generation(session: Session, since: date | None = None, until: date | None = None) -> pd.DataFrame:
    """Generación guardada (`date`, `technology`, `mwh`) con `since <= date <= until`."""
    rows = repository.get_generation(session, start=since, end=until)
    if not rows:
        return generation.empty_generation()
    return generation.merge_generation(generation.empty_generation(), pd.DataFrame(rows, columns=generation.COLUMNS))


def save_prices(session: Session, df: pd.DataFrame) -> int:
    """Guarda una tabla de PVPC (`datetime`, `price`). Devuelve las filas nuevas o cambiadas."""
    if df.empty:
        return 0
    datetimes = pd.to_datetime(df["datetime"], utc=True).dt.to_pydatetime()
    return repository.upsert_prices(session, zip(datetimes, df["price"].astype(float), strict=True))


def save_generation(session: Session, df: pd.DataFrame) -> int:
    """Guarda una tabla de generación (`date`, `technology`, `mwh`). Devuelve las filas nuevas o cambiadas."""
    if df.empty:
        return 0
    rows = zip(df["date"], df["technology"].astype(str), df["mwh"].astype(float), strict=True)
    return repository.upsert_generation(session, rows)
