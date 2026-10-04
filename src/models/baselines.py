"""Previsiones de referencia: lo mínimo que un modelo tiene que mejorar.

Se calculan a partir de las variables de `src.processing.features`, que solo
usan días anteriores al predicho, así que no pueden mirar al futuro.

Si una hora no tiene el dato principal (la 2:00 del día siguiente al cambio a
horario de verano no tiene "precio de ayer"), se usa el siguiente de la lista
para que la referencia dé previsión en todas las horas.
"""

from collections.abc import Callable

import pandas as pd

# Nombre -> columnas de las variables, de la preferida al último respaldo
BASELINE_SOURCES: dict[str, list[str]] = {
    "precio_ayer": ["price_lag_1d", "same_hour_mean_7d", "prev_day_mean"],
    "media_7_dias": ["same_hour_mean_7d", "price_lag_1d", "prev_day_mean"],
}


def _first_available(columns: list[str]) -> Callable[[pd.DataFrame], pd.Series]:
    def predict(features: pd.DataFrame) -> pd.Series:
        prediction = features[columns[0]]
        for column in columns[1:]:
            prediction = prediction.fillna(features[column])
        return prediction.rename("prediction")

    return predict


BASELINES: dict[str, Callable[[pd.DataFrame], pd.Series]] = {
    name: _first_available(columns) for name, columns in BASELINE_SOURCES.items()
}


def _check_name(name: str) -> None:
    if name not in BASELINES:
        raise KeyError(f"Referencia desconocida: {name}. Disponibles: {', '.join(BASELINES)}")


def predict_baseline(name: str, features: pd.DataFrame) -> pd.Series:
    """Previsión de la referencia `name` para cada fila de `features`."""
    _check_name(name)
    return BASELINES[name](features)


class BaselineForecaster:
    """Adapta una referencia a la interfaz de `backtest` (no necesita entrenarse)."""

    def __init__(self, name: str):
        _check_name(name)
        self.name = name

    def fit(self, features: pd.DataFrame) -> None:
        pass

    def predict(self, features: pd.DataFrame) -> pd.Series:
        return predict_baseline(self.name, features)
