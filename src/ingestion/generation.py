"""Descarga de la estructura de generación diaria y su almacenamiento local.

Tabla en formato largo: `date` (día local), `technology` y `mwh` (energía
generada ese día por esa tecnología en el sistema nacional). No se guarda la
"Generación total" de REE porque es la suma de las tecnologías.
"""

from datetime import date
from pathlib import Path

import pandas as pd

from src.ingestion.ree_client import ReeClient
from src.utils.calendar import local_date
from src.utils.config import get_settings

GENERATION_PATH = "generacion/estructura-generacion"
TOTAL_SERIES = "Generación total"

# Comprobado contra el indicador "Renovable" de REE: la suma coincide exactamente
RENEWABLE_TECHNOLOGIES = frozenset(
    {
        "Eólica",
        "Solar fotovoltaica",
        "Solar térmica",
        "Hidráulica",
        "Hidroeólica",
        "Otras renovables",
        "Residuos renovables",
    }
)

COLUMNS = ["date", "technology", "mwh"]


def default_path() -> Path:
    return get_settings().raw_dir / "generation.parquet"


def empty_generation() -> pd.DataFrame:
    return pd.DataFrame(
        {"date": pd.Series(dtype="object"), "technology": pd.Series(dtype="str"), "mwh": pd.Series(dtype="float64")}
    )


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    df = df[COLUMNS].copy()
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["technology"] = df["technology"].astype("str")
    df["mwh"] = df["mwh"].astype("float64")
    df = df.drop_duplicates(["date", "technology"], keep="last")
    return df.sort_values(["date", "technology"]).reset_index(drop=True)


def fetch_generation(start: date, end: date, client: ReeClient | None = None) -> pd.DataFrame:
    """Generación diaria por tecnología entre dos días locales (ambos incluidos)."""
    client = client or ReeClient()
    series = client.fetch(GENERATION_PATH, start, end, time_trunc="day")
    rows = [
        {"date": local_date(point.datetime), "technology": technology, "mwh": point.value}
        for technology, points in series.items()
        if technology != TOTAL_SERIES
        for point in points
    ]
    if not rows:
        return empty_generation()
    return _normalize(pd.DataFrame(rows))


def merge_generation(existing: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    """Une dos tablas; en los pares (día, tecnología) repetidos prevalece `new`."""
    frames = [df for df in (existing, new) if not df.empty]
    if not frames:
        return empty_generation()
    return _normalize(pd.concat(frames, ignore_index=True))


def load_generation(path: Path | None = None) -> pd.DataFrame:
    path = path or default_path()
    if not path.exists():
        return empty_generation()
    return _normalize(pd.read_parquet(path))


def save_generation(df: pd.DataFrame, path: Path | None = None) -> Path:
    path = path or default_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    _normalize(df).to_parquet(path, index=False)
    return path
