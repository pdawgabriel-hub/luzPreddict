"""Descarga del PVPC horario y su almacenamiento local en parquet.

La tabla tiene dos columnas: `datetime` (inicio de la hora, en UTC) y
`price` (€/MWh).
"""

from datetime import date
from pathlib import Path

import pandas as pd

from src.ingestion.ree_client import ReeClient
from src.utils.config import get_settings

PVPC_PATH = "mercados/precios-mercados-tiempo-real"
PVPC_SERIES = "PVPC"


def default_path() -> Path:
    return get_settings().raw_dir / "pvpc.parquet"


def empty_prices() -> pd.DataFrame:
    return pd.DataFrame(
        {"datetime": pd.Series(dtype="datetime64[us, UTC]"), "price": pd.Series(dtype="float64")},
    )


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    df = df[["datetime", "price"]].copy()
    df["datetime"] = pd.to_datetime(df["datetime"], utc=True).dt.as_unit("us")
    df["price"] = df["price"].astype("float64")
    return df.drop_duplicates("datetime", keep="last").sort_values("datetime").reset_index(drop=True)


def fetch_pvpc(start: date, end: date, client: ReeClient | None = None) -> pd.DataFrame:
    """PVPC horario entre dos días locales (ambos incluidos)."""
    client = client or ReeClient()
    points = client.fetch(PVPC_PATH, start, end).get(PVPC_SERIES, [])
    if not points:
        return empty_prices()
    return _normalize(pd.DataFrame({"datetime": [p.datetime for p in points], "price": [p.value for p in points]}))


def merge_prices(existing: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    """Une dos tablas de precios; en las horas repetidas prevalece `new`."""
    frames = [df for df in (existing, new) if not df.empty]
    if not frames:
        return empty_prices()
    return _normalize(pd.concat(frames, ignore_index=True))


def load_pvpc(path: Path | None = None) -> pd.DataFrame:
    path = path or default_path()
    if not path.exists():
        return empty_prices()
    return _normalize(pd.read_parquet(path))


def save_pvpc(df: pd.DataFrame, path: Path | None = None) -> Path:
    path = path or default_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    _normalize(df).to_parquet(path, index=False)
    return path
