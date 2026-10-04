"""Métricas de error de una previsión de precios.

Todas en €/MWh. No se usa el error porcentual (MAPE): con precios cercanos a 0
o negativos se dispara y deja de tener sentido.
"""

import numpy as np
import pandas as pd

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
