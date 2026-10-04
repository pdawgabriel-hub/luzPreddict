"""Previsión del PVPC del día siguiente, hora a hora.

Usa el modelo guardado (`make train`). Si no se puede usar, porque no existe,
es incompatible, falla o devuelve valores no válidos, se publica la referencia
"precio de ayer" y se indica el motivo: siempre hay previsión.

Uso:
    python -m src.models.predict                  # primer día sin precio publicado
    python -m src.models.predict --day 2026-10-06
"""

import argparse
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import numpy as np
import pandas as pd

from src.ingestion.prices import load_pvpc
from src.models.baselines import predict_baseline
from src.models.registry import ModelArtifact, load_artifact
from src.processing.clean import clean_prices
from src.processing.features import PRICE_FEATURES, features_for_day
from src.utils.calendar import local_date, market_timezone
from src.utils.logging import configure_logging

logger = logging.getLogger(__name__)

# La mejor referencia en el backtest (MAE 28,5 €/MWh frente a 28,9 de "media 7 días" desde 2025)
FALLBACK_BASELINE = "precio_ayer"


@dataclass(frozen=True)
class Forecast:
    day: date  # día local previsto
    prices: pd.Series  # €/MWh por hora, con índice UTC
    model: str  # "lightgbm" o el nombre de la referencia usada como respaldo
    model_version: str | None  # versión del modelo guardado (None si es una referencia)
    fallback_reason: str | None  # por qué no se usó el modelo (None si se usó)
    generated_at: datetime  # UTC

    @property
    def used_fallback(self) -> bool:
        return self.fallback_reason is not None


def next_day(prices: pd.DataFrame) -> date:
    """Primer día local sin precio publicado."""
    known = prices["price"].dropna()
    if known.empty:
        raise ValueError("No hay precios: ejecuta make backfill")
    return local_date(known.index.max()) + timedelta(days=1)


def predict_day(
    prices: pd.DataFrame,
    day: date | None = None,
    artifact: ModelArtifact | None = None,
    load: Callable[[], ModelArtifact] = load_artifact,
) -> Forecast:
    """Previsión de las horas del día `day` (por defecto, el primero sin precio publicado)."""
    day = day or next_day(prices)
    features = features_for_day(prices, day)
    if features[PRICE_FEATURES].isna().all().all():
        raise ValueError(f"No hay precios de los días anteriores al {day}: no se puede predecir")
    generated_at = datetime.now(UTC)

    try:
        artifact = artifact or load()
        values = artifact.model.predict(features)
        if not np.isfinite(values.to_numpy(dtype=float)).all():
            raise ValueError("el modelo devolvió valores vacíos o infinitos")
        return Forecast(
            day, values.rename("prediction"), artifact.model.name, artifact.metadata.version, None, generated_at
        )
    except Exception as exc:  # cualquier fallo del modelo activa el respaldo
        reason = f"{type(exc).__name__}: {exc}"
        logger.warning("Previsión del %s con %s en lugar del modelo (%s)", day, FALLBACK_BASELINE, reason)

    values = predict_baseline(FALLBACK_BASELINE, features)
    if values.isna().any():
        raise ValueError(f"Ni el modelo ni la referencia pueden predecir todas las horas del {day}")
    return Forecast(day, values.rename("prediction"), FALLBACK_BASELINE, None, reason, generated_at)


def forecast_table(forecast: Forecast) -> pd.DataFrame:
    """La previsión por hora local, en €/MWh y €/kWh, para mostrarla."""
    local = forecast.prices.index.tz_convert(market_timezone())
    return pd.DataFrame(
        {
            "hora": local.strftime("%H:%M"),
            "€/MWh": forecast.prices.to_numpy(),
            "€/kWh": forecast.prices.to_numpy() / 1000,
        }
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--day", type=date.fromisoformat, help="día local a predecir (AAAA-MM-DD)")
    args = parser.parse_args(argv)

    configure_logging()
    forecast = predict_day(clean_prices(load_pvpc()), args.day)

    source = f"{forecast.model} {forecast.model_version}" if forecast.model_version else forecast.model
    print(f"\nPrevisión del PVPC para el {forecast.day:%d/%m/%Y} ({source})")
    if forecast.used_fallback:
        print(f"Respaldo activado: {forecast.fallback_reason}")
    table = forecast_table(forecast)
    print(table.to_string(index=False, formatters={"€/MWh": "{:.1f}".format, "€/kWh": "{:.3f}".format}))
    cheapest = table.loc[table["€/MWh"].idxmin()]
    print(f"\nMedia {table['€/MWh'].mean():.1f} €/MWh · hora más barata {cheapest['hora']} ({cheapest['€/MWh']:.1f})")


if __name__ == "__main__":
    main()
