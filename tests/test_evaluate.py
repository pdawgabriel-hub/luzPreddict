import math

import numpy as np
import pandas as pd
import pytest

from src.models.evaluate import METRICS, metrics_by_group, regression_metrics


def test_regression_metrics_on_known_values():
    y_true = pd.Series([100.0, 100.0, 100.0, 100.0])
    y_pred = pd.Series([110.0, 90.0, 120.0, 100.0])  # errores: +10, -10, +20, 0

    m = regression_metrics(y_true, y_pred)

    assert m["mae"] == pytest.approx(10.0)
    assert m["rmse"] == pytest.approx(math.sqrt((100 + 100 + 400 + 0) / 4))
    assert m["bias"] == pytest.approx(5.0)  # sobrestima de media
    assert m["n"] == 4


def test_rmse_penalizes_large_errors_more_than_mae():
    y_true = pd.Series([0.0] * 4)
    small = regression_metrics(y_true, pd.Series([10.0, -10.0, 10.0, -10.0]))
    one_large = regression_metrics(y_true, pd.Series([40.0, 0.0, 0.0, 0.0]))

    assert small["mae"] == one_large["mae"] == 10.0
    assert one_large["rmse"] > small["rmse"]


def test_hours_without_real_or_predicted_value_are_ignored():
    y_true = pd.Series([100.0, np.nan, 100.0])
    y_pred = pd.Series([110.0, 500.0, np.nan])

    assert regression_metrics(y_true, y_pred) == {"mae": 10.0, "rmse": 10.0, "bias": 10.0, "n": 1}


def test_negative_prices_are_handled():
    m = regression_metrics(pd.Series([-10.0, 5.0]), pd.Series([0.0, 5.0]))
    assert m["mae"] == pytest.approx(5.0)
    assert m["bias"] == pytest.approx(5.0)


def test_no_pairs_returns_nan_metrics():
    m = regression_metrics(pd.Series([np.nan]), pd.Series([1.0]))
    assert m["n"] == 0
    assert math.isnan(m["mae"])


def test_metrics_by_group():
    y_true = pd.Series([100.0, 100.0, 100.0, 100.0])
    y_pred = pd.Series([110.0, 130.0, 100.0, 100.0])
    hours = pd.Series([8, 8, 20, 20], name="hour")

    table = metrics_by_group(y_true, y_pred, hours)

    assert list(table.columns) == METRICS
    assert table.index.name == "hour"
    assert table.loc[8, "mae"] == pytest.approx(20.0)
    assert table.loc[20, "mae"] == 0.0
    assert table.loc[8, "n"] == 2
