from datetime import date

import numpy as np
import pandas as pd
import pytest

from src.models.baselines import predict_baseline
from src.models.lightgbm_model import LightGBMForecaster
from src.models.predict import FALLBACK_BASELINE, forecast_table, next_day, predict_day
from src.models.registry import IncompatibleModelError, ModelArtifact, build_metadata
from src.processing.features import build_features, features_for_day
from src.utils.calendar import local_day_hours, market_timezone
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


# --- Días de 23 y 25 horas ---


@pytest.fixture(scope="module")
def spring_prices():
    return synthetic_prices(first_day=date(2026, 3, 1), n_days=29)  # hasta el 29 de marzo (23 h)


@pytest.fixture(scope="module")
def autumn_prices():
    return synthetic_prices(first_day=date(2026, 10, 1), n_days=25)  # hasta el 25 de octubre (25 h)


def _trained(prices):
    model = LightGBMForecaster(params=FAST, train_days=None)
    model.fit(build_features(prices))
    return ModelArtifact(model=model, metadata=build_metadata(model))


@pytest.mark.parametrize(
    "fixture, day, expected_hours",
    [
        ("spring_prices", date(2026, 3, 29), 23),
        ("spring_prices", date(2026, 3, 30), 24),
        ("autumn_prices", date(2026, 10, 25), 25),
        ("autumn_prices", date(2026, 10, 26), 24),
    ],
)
def test_predicts_every_local_hour_around_clock_changes(request, fixture, day, expected_hours):
    prices = request.getfixturevalue(fixture)
    forecast = predict_day(prices, day=day, artifact=_trained(prices))

    assert len(forecast.prices) == expected_hours
    assert forecast.prices.index.equals(pd.DatetimeIndex(local_day_hours(day)))
    assert forecast.prices.notna().all()
    assert not forecast.used_fallback


def test_the_repeated_2_am_gets_the_same_forecast(autumn_prices):
    forecast = predict_day(autumn_prices, day=date(2026, 10, 25), artifact=_trained(autumn_prices))

    local_hours = forecast.prices.index.tz_convert(market_timezone()).hour
    at_two = forecast.prices[local_hours == 2]
    assert len(at_two) == 2
    assert at_two.iloc[0] == at_two.iloc[1]


def test_fallback_also_covers_clock_change_days(spring_prices, autumn_prices):
    def no_model():
        raise FileNotFoundError("sin modelo")

    spring = predict_day(spring_prices, day=date(2026, 3, 30), load=no_model)  # su 2:00 no tiene "ayer"
    autumn = predict_day(autumn_prices, day=date(2026, 10, 25), load=no_model)

    assert spring.used_fallback and spring.prices.notna().all()
    assert autumn.used_fallback and len(autumn.prices) == 25


# --- Activación del respaldo ---


class BrokenModel:
    """Modelo que se comporta mal de una forma concreta."""

    name = "lightgbm"

    def __init__(self, behaviour):
        self.behaviour = behaviour

    def predict(self, features):
        if self.behaviour == "raises":
            raise RuntimeError("el modelo ha fallado")
        values = pd.Series(150.0, index=features.index)
        if self.behaviour == "nan":
            values.iloc[3] = np.nan
        elif self.behaviour == "inf":
            values.iloc[3] = np.inf
        elif self.behaviour == "too_few_hours":
            values = values.iloc[:-1]
        elif self.behaviour == "other_hours":
            values.index = values.index + pd.Timedelta(days=1)
        return values


@pytest.mark.parametrize(
    "behaviour, reason",
    [
        ("raises", "RuntimeError: el modelo ha fallado"),
        ("nan", "vacíos o infinitos"),
        ("inf", "vacíos o infinitos"),
        ("too_few_hours", "otras horas"),
        ("other_hours", "otras horas"),
    ],
)
def test_misbehaving_model_activates_the_fallback(prices, artifact, behaviour, reason, caplog):
    broken = ModelArtifact(model=BrokenModel(behaviour), metadata=artifact.metadata)

    forecast = predict_day(prices, artifact=broken)

    assert forecast.model == FALLBACK_BASELINE
    assert reason in forecast.fallback_reason
    assert len(forecast.prices) == 24 and forecast.prices.notna().all()
    assert "en lugar del modelo" in caplog.text


@pytest.mark.parametrize(
    "error",
    [
        FileNotFoundError("No hay modelo guardado: ejecuta make train"),
        IncompatibleModelError("Las variables del modelo no coinciden con las actuales"),
    ],
)
def test_unusable_saved_model_activates_the_fallback(prices, error):
    def load():
        raise error

    forecast = predict_day(prices, load=load)

    assert forecast.model == FALLBACK_BASELINE
    assert type(error).__name__ in forecast.fallback_reason


def test_fallback_uses_only_earlier_prices(prices):
    """El respaldo tampoco puede mirar el día que predice."""

    def no_model():
        raise FileNotFoundError("sin modelo")

    day = date(2026, 2, 1)
    tampered = prices.copy()
    tampered.loc[tampered.index >= local_day_hours(day)[0], "price"] = -999_999.0

    original = predict_day(prices, day=day, load=no_model)
    changed = predict_day(tampered, day=day, load=no_model)

    pd.testing.assert_series_equal(original.prices, changed.prices)
