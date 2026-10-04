"""Métricas de error y backtest diario de una previsión de precios.

Todas las métricas en €/MWh. No se usa el error porcentual (MAPE): con precios cercanos a 0
o negativos se dispara y deja de tener sentido.
"""

from datetime import date, timedelta
from typing import Protocol

import numpy as np
import pandas as pd

from src.processing.features import HISTORY_DAYS, build_features, features_for_day
from src.utils.calendar import local_day_hours

METRICS = ["mae", "rmse", "bias", "n"]


def regression_metrics(y_true: pd.Series, y_pred: pd.Series) -> dict[str, float]:
    """MAE, RMSE y sesgo de una previsión, ignorando las horas sin valor real o previsto.

    El sesgo es la media de (previsión - real): positivo si se sobrestima.
    """
    pairs = pd.DataFrame({"true": y_true, "pred": y_pred}).dropna()
    if pairs.empty:
        return {"mae": np.nan, "rmse": np.nan, "bias": np.nan, "n": 0}
    error = pairs["pred"] - pairs["true"]
    return {
        "mae": float(error.abs().mean()),
        "rmse": float(np.sqrt((error**2).mean())),
        "bias": float(error.mean()),
        "n": int(len(error)),
    }


def metrics_by_group(y_true: pd.Series, y_pred: pd.Series, groups: pd.Series | pd.Index) -> pd.DataFrame:
    """Las mismas métricas por grupo (por ejemplo, por hora del día o por año)."""
    groups = pd.Series(np.asarray(groups), index=y_true.index, name=getattr(groups, "name", None))
    rows = {key: regression_metrics(y_true[mask], y_pred[mask]) for key, mask in groups.groupby(groups).groups.items()}
    return pd.DataFrame.from_dict(rows, orient="index", columns=METRICS).rename_axis(groups.name)


# --- Backtest ---


class Forecaster(Protocol):
    """Cualquier modelo que se pueda evaluar con `backtest`."""

    name: str

    def fit(self, features: pd.DataFrame) -> None:
        """Entrena con variables y precio real de días ya conocidos."""

    def predict(self, features: pd.DataFrame) -> pd.Series:
        """Previsión para las filas de `features` (con `price` vacío)."""


def backtest(
    prices: pd.DataFrame,
    forecaster: Forecaster,
    start: date,
    end: date,
    refit_every_days: int | None = None,
    history_days: int = HISTORY_DAYS,
) -> pd.DataFrame:
    """Simula la previsión diaria entre `start` y `end` (días locales, incluidos).

    Para cada día D, el modelo solo ve los precios anteriores a D: las horas de D
    se le pasan con el precio vacío, igual que ocurrirá en producción. Se entrena
    antes del primer día y, si `refit_every_days` está definido, cada esos días.

    Devuelve una fila por hora con `day` (día local), `price` (real) y `prediction`.
    """
    if start > end:
        raise ValueError(f"La fecha inicial ({start}) es posterior a la final ({end})")

    results = []
    day, days_since_fit = start, None
    while day <= end:
        day_hours = pd.DatetimeIndex(local_day_hours(day), name="datetime")
        known = prices.loc[prices.index < day_hours[0], ["price"]]

        if days_since_fit is None or (refit_every_days and days_since_fit >= refit_every_days):
            forecaster.fit(build_features(known))
            days_since_fit = 0

        features = features_for_day(prices, day, history_days)

        results.append(
            pd.DataFrame(
                {
                    "day": day,
                    "price": prices["price"].reindex(day_hours),
                    "prediction": forecaster.predict(features).to_numpy(),
                },
                index=day_hours,
            )
        )
        day += timedelta(days=1)
        days_since_fit += 1

    return pd.concat(results)
