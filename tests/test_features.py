from datetime import date, timedelta

import pandas as pd
import pytest

from src.processing.features import FEATURES, TARIFF_PERIOD_CODES, build_features
from src.utils.calendar import tariff_period
from tests.fakes import coded_prices, row

START = date(2026, 1, 1)


def test_all_features_are_added_and_the_index_is_kept():
    prices = coded_prices()
    df = build_features(prices)

    assert list(df.columns) == ["price", *FEATURES]
    assert df.index.equals(prices.index)


def test_calendar_features_use_local_time():
    df = build_features(coded_prices())
    r = row(df, date(2026, 1, 6), 10)  # martes 6 de enero (Reyes), 10:00 en Madrid

    assert r["hour"] == 10
    assert r["dayofweek"] == 1
    assert r["month"] == 1
    assert r["dayofyear"] == 6
    assert r["is_weekend"] == 0
    assert r["is_holiday"] == 1


def test_tariff_period_matches_the_calendar_rules():
    prices = coded_prices(n_days=14)  # incluye fines de semana y el festivo del 6 de enero
    df = build_features(prices)

    expected = [TARIFF_PERIOD_CODES[tariff_period(ts)] for ts in prices.index.to_pydatetime()]
    assert df["tariff_period"].tolist() == expected


def test_lags_point_to_the_same_local_hour_k_days_before():
    df = build_features(coded_prices())
    r = row(df, START + timedelta(days=10), 18)  # día 10, 18:00

    assert r["price_lag_1d"] == 9 * 100 + 18
    assert r["price_lag_2d"] == 8 * 100 + 18
    assert r["price_lag_3d"] == 7 * 100 + 18
    assert r["price_lag_7d"] == 3 * 100 + 18
    assert r["same_hour_mean_7d"] == pytest.approx(sum(d * 100 + 18 for d in range(3, 10)) / 7)


def test_previous_day_statistics():
    df = build_features(coded_prices())
    r = row(df, START + timedelta(days=10), 5)

    assert r["prev_day_mean"] == pytest.approx(900 + 11.5)  # media de las horas 0-23 del día 9
    assert r["prev_day_min"] == 900
    assert r["prev_day_max"] == 923
    assert r["prev_day_last"] == 923
    assert r["prev_7d_mean"] == pytest.approx(sum(d * 100 + 11.5 for d in range(3, 10)) / 7)


def test_first_days_have_no_price_features():
    df = build_features(coded_prices())
    first_day = df.iloc[:24]

    assert first_day["price_lag_1d"].isna().all()
    assert first_day["prev_day_mean"].isna().all()
    assert pd.isna(row(df, START + timedelta(days=6), 0)["prev_7d_mean"])  # aún no hay 7 días completos
    assert pd.notna(row(df, START + timedelta(days=7), 0)["prev_7d_mean"])


def test_rows_to_predict_can_have_an_empty_price():
    prices = coded_prices()
    prices.loc[prices.index[-24:], "price"] = float("nan")  # último día: a predecir

    df = build_features(prices)

    assert df.iloc[-24:][FEATURES].notna().all().all()


def test_empty_input():
    df = build_features(coded_prices().iloc[:0])
    assert df.empty
    assert list(df.columns) == ["price", *FEATURES]
