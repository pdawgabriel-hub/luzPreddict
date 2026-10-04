from datetime import date

import pandas as pd
import pytest

from src.models.baselines import predict_baseline
from src.models.lightgbm_model import LightGBMForecaster
from src.models.predict import FALLBACK_BASELINE, forecast_table, next_day, predict_day
from src.models.registry import ModelArtifact, build_metadata
from src.processing.features import build_features, features_for_day
from tests.fakes import synthetic_prices

FAST = {"n_estimators": 30, "learning_rate": 0.1}


@pytest.fixture(scope="module")
def prices():
    return synthetic_prices(n_days=40)  # del 1 de enero al 9 de febrero de 2026


@pytest.fixture(scope="module")
def artifact(prices):
    model = LightGBMForecaster(params=FAST, train_days=None)
    model.fit(build_features(prices))
    return ModelArtifact(model=model, metadata=build_metadata(model))


def test_next_day_is_the_first_without_price(prices):
    assert next_day(prices) == date(2026, 2, 10)


def test_predicts_every_hour_of_the_next_day_with_the_model(prices, artifact):
    forecast = predict_day(prices, artifact=artifact)

    assert forecast.day == date(2026, 2, 10)
    assert len(forecast.prices) == 24
    assert forecast.prices.notna().all()
    assert forecast.model == "lightgbm"
    assert forecast.model_version == artifact.metadata.version
    assert not forecast.used_fallback
    pd.testing.assert_series_equal(
        forecast.prices, artifact.model.predict(features_for_day(prices, forecast.day)), check_names=False
    )


def test_can_predict_a_past_day_using_only_earlier_prices(prices, artifact):
    forecast = predict_day(prices, day=date(2026, 2, 1), artifact=artifact)
    assert forecast.day == date(2026, 2, 1)
    assert len(forecast.prices) == 24


def test_falls_back_to_yesterday_price_when_there_is_no_saved_model(prices):
    def no_model():
        raise FileNotFoundError("No hay modelo guardado: ejecuta make train")

    forecast = predict_day(prices, load=no_model)

    assert forecast.model == FALLBACK_BASELINE
    assert forecast.model_version is None
    assert forecast.used_fallback
    assert "make train" in forecast.fallback_reason
    expected = predict_baseline(FALLBACK_BASELINE, features_for_day(prices, forecast.day))
    pd.testing.assert_series_equal(forecast.prices, expected, check_names=False)


def test_forecast_table_uses_local_hours_and_both_units(prices, artifact):
    table = forecast_table(predict_day(prices, artifact=artifact))

    assert list(table.columns) == ["hora", "€/MWh", "€/kWh"]
    assert table["hora"].iloc[0] == "00:00"
    assert table["€/kWh"].iloc[0] == pytest.approx(table["€/MWh"].iloc[0] / 1000)


def test_without_history_there_is_no_forecast(prices, artifact):
    with pytest.raises(ValueError, match="No hay precios de los días anteriores"):
        predict_day(prices, day=date(2025, 6, 1), artifact=artifact)
