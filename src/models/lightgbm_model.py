"""Modelo LightGBM que predice el precio horario a partir de `FEATURES`.

Además de la previsión, dos modelos de regresión por cuantiles dan un intervalo
(`QUANTILES`): el precio real debería quedar dentro 8 de cada 10 horas.

Está en su propio módulo, separado del comando de entrenamiento, para que el
modelo guardado se pueda cargar desde cualquier programa: si la clase estuviera
en el módulo que se ejecuta con `python -m`, pickle la guardaría como
`__main__.LightGBMForecaster` y no se encontraría al cargarla.
"""

import lightgbm as lgb
import numpy as np
import pandas as pd

from src.processing.features import FEATURES, TARGET

# Elegidos en el periodo de validación (MAE 15,6 €/MWh frente a 26,5 de "precio de ayer")
TRAIN_DAYS = 730
DEFAULT_PARAMS = {
    "objective": "l1",
    "n_estimators": 500,
    "learning_rate": 0.03,
    "num_leaves": 31,
    "min_child_samples": 50,
    "subsample": 0.8,
    "subsample_freq": 1,
    "colsample_bytree": 0.8,
    "random_state": 42,
    "verbose": -1,
}
# Percentiles de los límites del intervalo y cobertura que se anuncia. Con 10 y 90, el
# precio real solo cayó dentro el 68 % de las horas de validación: con 5 y 95, el 80 %
# (79,5 % en el periodo de prueba, con 55 €/MWh de anchura media).
QUANTILES = (0.05, 0.95)
INTERVAL_LEVEL = 0.8


class LightGBMForecaster:
    """LightGBM que predice el precio horario a partir de `FEATURES`."""

    name = "lightgbm"

    def __init__(
        self,
        params: dict | None = None,
        train_days: int | None = TRAIN_DAYS,
        features: list[str] = FEATURES,
        quantiles: tuple[float, float] = QUANTILES,
    ):
        self.params = {**DEFAULT_PARAMS, **(params or {})}
        self.train_days = train_days
        self.features = list(features)
        self.quantiles = quantiles
        self.model: lgb.LGBMRegressor | None = None
        self.quantile_models: list[lgb.LGBMRegressor] = []
        self.training_rows_ = 0
        self.train_start_: pd.Timestamp | None = None
        self.train_end_: pd.Timestamp | None = None

    def fit(self, features: pd.DataFrame) -> None:
        train = features.dropna(subset=[TARGET])
        if self.train_days is not None and not train.empty:
            train = train[train.index > train.index.max() - pd.Timedelta(days=self.train_days)]
        if train.empty:
            raise ValueError("No hay filas con precio real para entrenar")

        self.model = lgb.LGBMRegressor(**self.params)
        self.model.fit(train[self.features], train[TARGET])
        # Mismos parámetros que el modelo principal, con otro objetivo
        self.quantile_models = [
            lgb.LGBMRegressor(**{**self.params, "objective": "quantile", "alpha": q}) for q in self.quantiles
        ]
        for model in self.quantile_models:
            model.fit(train[self.features], train[TARGET])
        self.training_rows_ = len(train)
        self.train_start_, self.train_end_ = train.index.min(), train.index.max()

    def predict(self, features: pd.DataFrame) -> pd.Series:
        if self.model is None:
            raise RuntimeError("El modelo no está entrenado: llama antes a fit()")
        return pd.Series(self.model.predict(features[self.features]), index=features.index, name="prediction")

    def predict_interval(self, features: pd.DataFrame) -> pd.DataFrame:
        """Previsión con su intervalo: columnas `lower`, `prediction` y `upper`."""
        prediction = self.predict(features).to_numpy()
        lower, upper = (model.predict(features[self.features]) for model in self.quantile_models)
        # Los tres modelos se entrenan por separado y en alguna hora podrían cruzarse
        return pd.DataFrame(
            {
                "lower": np.minimum(lower, prediction),
                "prediction": prediction,
                "upper": np.maximum(upper, prediction),
            },
            index=features.index,
        )

    def feature_importance(self) -> pd.Series:
        """Ganancia total aportada por cada variable, de mayor a menor."""
        if self.model is None:
            raise RuntimeError("El modelo no está entrenado: llama antes a fit()")
        gain = self.model.booster_.feature_importance(importance_type="gain")
        return pd.Series(gain, index=self.features, name="gain").sort_values(ascending=False)
