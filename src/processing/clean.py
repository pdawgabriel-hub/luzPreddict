"""Limpieza del PVPC: serie horaria continua en UTC.

Trabajar en UTC evita los problemas de los cambios de hora: en hora local hay
días de 23 y 25 horas, pero en UTC la serie es siempre una hora tras otra.
"""

import pandas as pd

# Huecos de como mucho estas horas seguidas se interpolan; los mayores se dejan vacíos
MAX_INTERPOLATION_HOURS = 3


def clean_prices(raw: pd.DataFrame, max_gap_hours: int = MAX_INTERPOLATION_HOURS) -> pd.DataFrame:
    """Convierte la tabla bruta (`datetime`, `price`) en una serie horaria continua.

    Devuelve un DataFrame con índice `datetime` (UTC, una fila por hora entre la
    primera y la última) y las columnas `price` e `is_interpolated`. Solo se
    rellenan los huecos completos de `max_gap_hours` horas o menos; en los más
    largos `price` queda vacío para no inventar datos.
    """
    datetimes = pd.to_datetime(raw["datetime"])
    if datetimes.dt.tz is None:
        raise ValueError("La columna datetime debe tener zona horaria")

    series = pd.Series(
        raw["price"].astype("float64").to_numpy(), index=datetimes.dt.tz_convert("UTC"), name="price"
    ).loc[lambda s: s.index.notna()]
    # Primero los duplicados (gana el último en llegar) y después el orden
    series = series[~series.index.duplicated(keep="last")].sort_index()

    if series.empty:
        index = pd.DatetimeIndex([], tz="UTC", name="datetime")
        return pd.DataFrame(
            {"price": pd.Series(dtype="float64"), "is_interpolated": pd.Series(dtype="bool")}, index=index
        )

    full_index = pd.date_range(series.index.min(), series.index.max(), freq="h", name="datetime")
    series = series.reindex(full_index)

    fillable = series.isna() & (_gap_lengths(series) <= max_gap_hours)
    interpolated = series.interpolate(method="time", limit_area="inside")
    price = series.where(~fillable, interpolated)

    return pd.DataFrame({"price": price, "is_interpolated": fillable})


def _gap_lengths(series: pd.Series) -> pd.Series:
    """Para cada hora vacía, la longitud del hueco al que pertenece (0 si tiene valor)."""
    missing = series.isna()
    gap_id = (missing != missing.shift()).cumsum()
    return missing.groupby(gap_id).transform("sum").where(missing, 0)
