"""Modelo LightGBM: comparación con las referencias y entrenamiento final.

Validación temporal en dos periodos, para no elegir la configuración mirando
el resultado final:

- Validación (2024): se compararon configuraciones y se eligió la de
  `lightgbm_model.DEFAULT_PARAMS` y `TRAIN_DAYS` (objetivo L1 y últimos 2 años).
- Prueba (desde 2025): se evalúa la configuración elegida contra las referencias.

Uso:
    python -m src.models.train backtest              # periodo de prueba hasta hoy
    python -m src.models.train backtest --start 2024-01-01 --end 2024-12-31
    python -m src.models.train fit                   # entrena con todo y guarda en models/
"""

import argparse
import logging
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from src.ingestion.prices import load_pvpc
from src.models.baselines import BASELINES, BaselineForecaster
from src.models.evaluate import Forecaster, backtest, regression_metrics
from src.models.lightgbm_model import LightGBMForecaster
from src.models.registry import ModelArtifact, build_metadata, save_artifact
from src.processing.clean import clean_prices
from src.processing.features import build_features
from src.utils.calendar import local_date
from src.utils.logging import configure_logging

logger = logging.getLogger(__name__)

VALIDATION_PERIOD = (date(2024, 1, 1), date(2024, 12, 31))
TEST_START = date(2025, 1, 1)
REFIT_EVERY_DAYS = 30
# Días recientes con los que se miden las métricas que se guardan con el modelo
METRICS_DAYS = 90
# Días de precios necesarios antes del primer día evaluable (la variable más larga mira 7 días atrás)
MIN_HISTORY_DAYS = 8


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


def train_final_model(
    prices: pd.DataFrame,
    metrics_days: int = METRICS_DAYS,
    refit_every_days: int = REFIT_EVERY_DAYS,
) -> ModelArtifact:
    """Entrena LightGBM con todos los precios conocidos y lo acompaña de sus métricas.

    Las métricas salen de un backtest de los últimos `metrics_days` días, de
    LightGBM y de las referencias, para saber cuánto mejora el modelo guardado.
    Si no hay tanta historia, el periodo empieza en cuanto hay una semana de datos.
    """
    known = prices["price"].dropna()
    first_day, last_day = local_date(known.index.min()), local_date(known.index.max())
    start = max(last_day - timedelta(days=metrics_days - 1), first_day + timedelta(days=MIN_HISTORY_DAYS))
    if start > last_day:
        raise ValueError(f"Hacen falta al menos {MIN_HISTORY_DAYS + 1} días de precios para entrenar y medir el modelo")
    metrics_days = (last_day - start).days + 1
    summary, _ = compare_models(prices, start, last_day, refit_every_days=refit_every_days)
    metrics = {
        "period": {"start": start.isoformat(), "end": last_day.isoformat(), "days": metrics_days},
        "models": {name: {k: round(float(v), 2) for k, v in row.items()} for name, row in summary.iterrows()},
    }

    model = LightGBMForecaster()
    model.fit(build_features(prices))
    return ModelArtifact(model=model, metadata=build_metadata(model, metrics=metrics))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)

    compare = commands.add_parser("backtest", help="compara LightGBM con las referencias")
    compare.add_argument("--start", type=date.fromisoformat, default=TEST_START, help="primer día del backtest")
    compare.add_argument("--end", type=date.fromisoformat, help="último día (por defecto, el último con precio)")

    fit = commands.add_parser("fit", help="entrena con todos los datos y guarda el modelo")
    fit.add_argument("--output", type=Path, help="directorio donde guardarlo (por defecto, models/)")
    fit.add_argument("--metrics-days", type=int, default=METRICS_DAYS, help="días recientes para medir el modelo")
    args = parser.parse_args(argv)

    configure_logging()
    prices = clean_prices(load_pvpc())

    if args.command == "backtest":
        end = args.end or local_date(prices["price"].dropna().index.max())
        summary, _ = compare_models(prices, args.start, end)
        print(f"\nBacktest del {args.start} al {end} (reentrenando cada {REFIT_EVERY_DAYS} días), €/MWh:\n")
        print(summary.round(1).to_string())
    else:
        artifact = train_final_model(prices, metrics_days=args.metrics_days)
        path = save_artifact(artifact, args.output)
        meta = artifact.metadata
        print(f"\nModelo {meta.version} guardado en {path}")
        print(f"Entrenado con {meta.training_rows} horas, del {meta.train_start:%d/%m/%Y} al {meta.train_end:%d/%m/%Y}")
        period = meta.metrics["period"]
        print(f"MAE de los últimos {period['days']} días (€/MWh):")
        for name, values in meta.metrics["models"].items():
            print(f"  {name:13s} {values['mae']:.1f}")


if __name__ == "__main__":
    main()
