from datetime import date

import numpy as np
import pandas as pd
import pytest

from src.models.baselines import BaselineForecaster
from src.models.evaluate import METRICS, backtest, interval_metrics
from src.models.lightgbm_model import LightGBMForecaster
from src.models.train import compare_models
from src.processing.features import FEATURES, build_features
from src.utils.calendar import local_day_hours
from tests.fakes import synthetic_prices

FAST = {"n_estimators": 60, "learning_rate": 0.1}


@pytest.fixture(scope="module")
def prices():
    return synthetic_prices()


def test_fit_and_predict(prices):
    features = build_features(prices)
    model = LightGBMForecaster(params=FAST)

    model.fit(features)
    prediction = model.predict(features.iloc[-24:])

    assert len(prediction) == 24
    assert prediction.notna().all()
    assert prediction.index.equals(features.index[-24:])


def test_trains_only_on_the_last_days(prices):
    features = build_features(prices)

    model = LightGBMForecaster(params=FAST, train_days=14)
    model.fit(features)

    assert model.training_rows_ == 14 * 24


def test_rows_without_price_are_not_used_for_training(prices):
    features = build_features(prices)
    features.loc[features.index[-24:], "price"] = np.nan

    model = LightGBMForecaster(params=FAST, train_days=None)
    model.fit(features)

    assert model.training_rows_ == len(prices) - 24


def test_interval_surrounds_the_prediction(prices):
    features = build_features(prices)
    model = LightGBMForecaster(params=FAST)
    model.fit(features)

    interval = model.predict_interval(features.iloc[-48:])

    assert list(interval.columns) == ["lower", "prediction", "upper"]
    assert interval.index.equals(features.index[-48:])
    pd.testing.assert_series_equal(interval["prediction"], model.predict(features.iloc[-48:]), check_names=False)
    assert (interval["lower"] <= interval["prediction"]).all()
    assert (interval["prediction"] <= interval["upper"]).all()
    assert (interval["upper"] > interval["lower"]).mean() > 0.9  # no es un punto


def test_interval_covers_about_80_percent_of_unseen_hours(prices):
    results = backtest(
        prices, LightGBMForecaster(params=FAST), date(2026, 2, 20), date(2026, 3, 11), refit_every_days=7
    )

    coverage = interval_metrics(results["price"], results["lower"], results["upper"])["coverage"]

    assert 0.6 <= coverage <= 0.95


def test_backtest_includes_the_interval_only_for_models_that_give_it(prices):
    day = date(2026, 3, 5)
    with_interval = backtest(prices, LightGBMForecaster(params=FAST), day, day)
    without = backtest(prices, BaselineForecaster("precio_ayer"), day, day)

    assert {"lower", "upper"} <= set(with_interval.columns)
    assert not {"lower", "upper"} & set(without.columns)


def test_errors_before_training_or_without_data(prices):
    model = LightGBMForecaster(params=FAST)
    with pytest.raises(RuntimeError, match="no está entrenado"):
        model.predict(build_features(prices))
    with pytest.raises(RuntimeError, match="no está entrenado"):
        model.predict_interval(build_features(prices))
    with pytest.raises(ValueError, match="No hay filas"):
        model.fit(build_features(prices).assign(price=np.nan))


def test_feature_importance_covers_every_feature(prices):
    model = LightGBMForecaster(params=FAST)
    model.fit(build_features(prices))

    importance = model.feature_importance()

    assert set(importance.index) == set(FEATURES)
    assert importance.is_monotonic_decreasing


def test_lightgbm_never_uses_the_price_of_the_day_it_predicts(prices):
    day = date(2026, 3, 5)
    tampered = prices.copy()
    tampered.loc[tampered.index >= local_day_hours(day)[0], "price"] = -999_999.0

    original = backtest(prices, LightGBMForecaster(params=FAST), day, day)
    changed = backtest(tampered, LightGBMForecaster(params=FAST), day, day)

    pd.testing.assert_series_equal(original["prediction"], changed["prediction"])
    pd.testing.assert_series_equal(original["lower"], changed["lower"])
    pd.testing.assert_series_equal(original["upper"], changed["upper"])


def test_learns_weekly_and_hourly_patterns_better_than_yesterday_price(prices):
    summary, results = compare_models(
        prices,
        date(2026, 2, 20),
        date(2026, 3, 11),
        forecasters=[BaselineForecaster("precio_ayer"), LightGBMForecaster(params=FAST)],
        refit_every_days=7,
    )

    assert list(summary.columns) == METRICS
    assert summary.index[0] == "lightgbm"  # ordenado de mejor a peor MAE
    assert summary.loc["lightgbm", "mae"] < summary.loc["precio_ayer", "mae"]
    assert set(results) == {"precio_ayer", "lightgbm"}


def test_multi_day_backtest_with_refits_never_uses_future_prices(prices):
    """Con reentrenos por el camino, cambiar los precios desde D no altera ninguna previsión hasta D."""
    start, cut, end = date(2026, 3, 1), date(2026, 3, 4), date(2026, 3, 7)
    tampered = prices.copy()
    tampered.loc[tampered.index >= local_day_hours(cut)[0], "price"] *= 3

    original = backtest(prices, LightGBMForecaster(params=FAST), start, end, refit_every_days=2)
    changed = backtest(tampered, LightGBMForecaster(params=FAST), start, end, refit_every_days=2)

    until_cut = original["day"] <= cut
    pd.testing.assert_series_equal(original.loc[until_cut, "prediction"], changed.loc[until_cut, "prediction"])
    # Después de D sí deben cambiar: el modelo ya conoce los precios alterados
    assert not np.allclose(original.loc[~until_cut, "prediction"], changed.loc[~until_cut, "prediction"])
