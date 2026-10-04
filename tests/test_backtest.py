from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from src.models.baselines import BaselineForecaster, predict_baseline
from src.models.evaluate import backtest
from src.processing.features import build_features
from src.utils.calendar import hours_in_day, local_day_hours
from tests.fakes import coded_prices

START, END = date(2026, 1, 15), date(2026, 1, 21)


class SpyForecaster:
    """Registra qué datos recibe en cada entrenamiento y previsión."""

    name = "espía"

    def __init__(self):
        self.fits = []  # última hora con precio vista en cada fit
        self.predict_inputs = []

    def fit(self, features):
        self.fits.append(features.dropna(subset=["price"]).index.max())

    def predict(self, features):
        self.predict_inputs.append(features)
        return pd.Series(0.0, index=features.index)


@pytest.fixture
def prices():
    return coded_prices(first_day=date(2026, 1, 1), n_days=30)


def test_one_row_per_hour_of_each_day(prices):
    result = backtest(prices, BaselineForecaster("precio_ayer"), START, END)

    assert list(result.columns) == ["day", "price", "prediction"]
    assert len(result) == 7 * 24
    assert sorted(result["day"].unique()) == [START + timedelta(days=i) for i in range(7)]
    assert result["price"].equals(prices["price"].reindex(result.index))


def test_same_predictions_as_computing_features_on_the_full_history(prices):
    """Recalcular las variables con solo 10 días de historia no cambia nada."""
    result = backtest(prices, BaselineForecaster("media_7_dias"), START, END)

    full = predict_baseline("media_7_dias", build_features(prices)).reindex(result.index)
    np.testing.assert_allclose(result["prediction"], full)


def test_the_model_never_sees_the_price_of_the_day_it_predicts(prices):
    spy = SpyForecaster()

    backtest(prices, spy, START, END, refit_every_days=2)

    for inputs in spy.predict_inputs:
        assert inputs["price"].isna().all()
    first_hours = [local_day_hours(START + timedelta(days=i))[0] for i in range(0, 7, 2)]
    assert spy.fits == [first_hour - pd.Timedelta(hours=1) for first_hour in first_hours]


def test_changing_prices_from_a_day_onwards_does_not_change_its_prediction(prices):
    tampered = prices.copy()
    tampered.loc[tampered.index >= local_day_hours(END)[0], "price"] = -999_999.0

    original = backtest(prices, BaselineForecaster("precio_ayer"), END, END)
    changed = backtest(tampered, BaselineForecaster("precio_ayer"), END, END)

    pd.testing.assert_series_equal(original["prediction"], changed["prediction"])


@pytest.mark.parametrize("refit_every_days, expected_fits", [(None, 1), (7, 1), (3, 3), (1, 7)])
def test_refit_schedule(prices, refit_every_days, expected_fits):
    spy = SpyForecaster()
    backtest(prices, spy, START, END, refit_every_days=refit_every_days)
    assert len(spy.fits) == expected_fits


def test_days_with_23_and_25_hours():
    prices = coded_prices(first_day=date(2026, 3, 15), n_days=230)
    result = backtest(prices, BaselineForecaster("precio_ayer"), date(2026, 3, 29), date(2026, 3, 30))
    assert len(result) == hours_in_day(date(2026, 3, 29)) + hours_in_day(date(2026, 3, 30)) == 23 + 24

    result = backtest(prices, BaselineForecaster("precio_ayer"), date(2026, 10, 25), date(2026, 10, 25))
    assert len(result) == 25
    assert result["prediction"].notna().all()


def test_days_without_real_price_are_still_predicted(prices):
    last_day = date(2026, 1, 30)
    result = backtest(
        prices, BaselineForecaster("precio_ayer"), last_day + timedelta(days=1), last_day + timedelta(days=1)
    )

    assert result["price"].isna().all()  # mañana: aún no hay precio real
    assert result["prediction"].notna().all()


def test_inverted_range_is_rejected(prices):
    with pytest.raises(ValueError, match="posterior"):
        backtest(prices, BaselineForecaster("precio_ayer"), END, START)
