"""Modelo LightGBM y su comparación con las referencias mediante backtest.

Validación temporal en dos periodos, para no elegir la configuración mirando
el resultado final:

- Validación (2024): se compararon configuraciones y se eligió la de
  `DEFAULT_PARAMS` y `TRAIN_DAYS` (objetivo L1 y últimos 2 años de datos).
- Prueba (desde 2025): se evalúa la configuración elegida contra las referencias.

Uso:
    python -m src.models.train                       # periodo de prueba hasta hoy
    python -m src.models.train --start 2024-01-01 --end 2024-12-31
"""

import argparse
import logging
from datetime import date

import lightgbm as lgb
import pandas as pd

from src.ingestion.prices import load_pvpc
from src.models.baselines import BASELINES, BaselineForecaster
from src.models.evaluate import Forecaster, backtest, regression_metrics
from src.processing.clean import clean_prices
from src.processing.features import FEATURES, TARGET
from src.utils.calendar import local_date
from src.utils.logging import configure_logging

logger = logging.getLogger(__name__)

VALIDATION_PERIOD = (date(2024, 1, 1), date(2024, 12, 31))
TEST_START = date(2025, 1, 1)
REFIT_EVERY_DAYS = 30

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


class LightGBMForecaster:
    """LightGBM que predice el precio horario a partir de `FEATURES`."""

    name = "lightgbm"

    def __init__(self, params: dict | None = None, train_days: int | None = TRAIN_DAYS, features: list[str] = FEATURES):
        self.params = {**DEFAULT_PARAMS, **(params or {})}
        self.train_days = train_days
        self.features = list(features)
        self.model: lgb.LGBMRegressor | None = None
        self.training_rows_ = 0

    def fit(self, features: pd.DataFrame) -> None:
        train = features.dropna(subset=[TARGET])
        if self.train_days is not None and not train.empty:
            train = train[train.index > train.index.max() - pd.Timedelta(days=self.train_days)]
        if train.empty:
            raise ValueError("No hay filas con precio real para entrenar")

        self.model = lgb.LGBMRegressor(**self.params)
        self.model.fit(train[self.features], train[TARGET])
        self.training_rows_ = len(train)

    def predict(self, features: pd.DataFrame) -> pd.Series:
        if self.model is None:
            raise RuntimeError("El modelo no está entrenado: llama antes a fit()")
        return pd.Series(self.model.predict(features[self.features]), index=features.index, name="prediction")

    def feature_importance(self) -> pd.Series:
        """Ganancia total aportada por cada variable, de mayor a menor."""
        if self.model is None:
            raise RuntimeError("El modelo no está entrenado: llama antes a fit()")
        gain = self.model.booster_.feature_importance(importance_type="gain")
        return pd.Series(gain, index=self.features, name="gain").sort_values(ascending=False)


def default_forecasters() -> list[Forecaster]:
    return [*(BaselineForecaster(name) for name in BASELINES), LightGBMForecaster()]


def compare_models(
    prices: pd.DataFrame,
    start: date,
    end: date,
    forecasters: list[Forecaster] | None = None,
    refit_every_days: int = REFIT_EVERY_DAYS,
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    """Backtest de cada modelo en el mismo periodo.

    Devuelve una tabla de métricas (una fila por modelo, de mejor a peor MAE) y
    los resultados hora a hora de cada uno.
    """
    results = {}
    for forecaster in forecasters or default_forecasters():
        logger.info("Backtest de %s del %s al %s", forecaster.name, start, end)
        results[forecaster.name] = backtest(prices, forecaster, start, end, refit_every_days=refit_every_days)

    summary = pd.DataFrame(
        {name: regression_metrics(r["price"], r["prediction"]) for name, r in results.items()}
    ).T.sort_values("mae")
    summary["n"] = summary["n"].astype(int)
    return summary.rename_axis("modelo"), results


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start", type=date.fromisoformat, default=TEST_START, help="primer día del backtest")
    parser.add_argument("--end", type=date.fromisoformat, help="último día (por defecto, el último con precio)")
    args = parser.parse_args(argv)

    configure_logging()
    prices = clean_prices(load_pvpc())
    end = args.end or local_date(prices["price"].dropna().index.max())
    summary, _ = compare_models(prices, args.start, end)

    print(f"\nBacktest del {args.start} al {end} (reentrenando cada {REFIT_EVERY_DAYS} días), €/MWh:\n")
    print(summary.round(1).to_string())


if __name__ == "__main__":
    main()
