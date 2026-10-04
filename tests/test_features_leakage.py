"""Las variables del día D no pueden usar ningún dato de D ni posterior.

Al predecir D solo se conoce el precio hasta el final de D-1. Si alguna
variable dependiera de D, el modelo parecería acertar en el backtest y
fallaría en producción.
"""

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from src.processing.features import FEATURES, build_features
from src.utils.calendar import local_day_hours, market_timezone
from tests.fakes import coded_prices, row


def hours_of(df, day):
    local = df.index.tz_convert(market_timezone())
    return df.index[local.date == day]


def assert_no_leakage(build, day, days_before=10, days_after=2):
    """Falla si alguna variable de `day` cambia al alterar los precios desde `day` en adelante."""
    prices = coded_prices(first_day=day - timedelta(days=days_before), n_days=days_before + 1 + days_after)
    first_hour_of_day = local_day_hours(day)[0]

    tampered = prices.copy()
    tampered.loc[tampered.index >= first_hour_of_day, "price"] = -999_999.0

    target_rows = hours_of(prices, day)
    pd.testing.assert_frame_equal(
        build(prices).loc[target_rows, FEATURES],
        build(tampered).loc[target_rows, FEATURES],
    )


@pytest.mark.parametrize(
    "day",
    [
        date(2026, 1, 20),  # día normal
        date(2026, 3, 29),  # 23 horas
        date(2026, 3, 30),  # día siguiente al de 23 horas
        date(2026, 10, 25),  # 25 horas
        date(2026, 10, 26),  # día siguiente al de 25 horas
        date(2026, 10, 12),  # festivo
        date(2026, 11, 1),  # primer día de mes y festivo en domingo
    ],
)
def test_features_of_a_day_never_use_that_day_or_later(day):
    assert_no_leakage(build_features, day)


def test_the_check_detects_a_naive_shift_on_the_25_hour_day():
    """Con shift(24), la última hora del día de 25 h mira la primera hora del propio día."""

    def build_with_naive_lag(df):
        out = build_features(df)
        out["price_lag_1d"] = df["price"].shift(24)
        return out

    assert_no_leakage(build_with_naive_lag, date(2026, 10, 24))  # día normal: no se nota
    with pytest.raises(AssertionError):
        assert_no_leakage(build_with_naive_lag, date(2026, 10, 25))


# --- Días de 23 y 25 horas ---


def test_23_hour_day_has_no_2_am_and_the_next_day_has_no_lag_for_it():
    df = build_features(coded_prices(first_day=date(2026, 3, 20), n_days=12))
    spring = df.loc[hours_of(df, date(2026, 3, 29))]

    assert len(spring) == 23
    assert 2 not in set(spring["hour"])

    next_day_2am = row(df, date(2026, 3, 30), 2)
    assert np.isnan(next_day_2am["price_lag_1d"])  # el 29 no tuvo 2:00
    assert next_day_2am["price_lag_2d"] == row(df, date(2026, 3, 28), 2)["price"]


def test_25_hour_day_repeats_2_am_with_the_same_features():
    df = build_features(coded_prices(first_day=date(2026, 10, 15), n_days=14))
    autumn = df.loc[hours_of(df, date(2026, 10, 25))]

    assert len(autumn) == 25
    repeated = autumn[autumn["hour"] == 2]
    assert len(repeated) == 2
    pd.testing.assert_frame_equal(
        repeated.iloc[[0]][FEATURES].reset_index(drop=True), repeated.iloc[[1]][FEATURES].reset_index(drop=True)
    )


def test_day_after_25_hour_day_uses_all_of_its_hours():
    prices = coded_prices(first_day=date(2026, 10, 15), n_days=14)
    df = build_features(prices)
    autumn_prices = prices.loc[hours_of(prices, date(2026, 10, 25)), "price"]

    next_day = row(df, date(2026, 10, 26), 12)

    assert next_day["prev_day_mean"] == pytest.approx(autumn_prices.mean())  # media de las 25 horas
    assert next_day["prev_day_last"] == autumn_prices.iloc[-1]
    # La 2:00 repetida se promedia
    assert row(df, date(2026, 10, 26), 2)["price_lag_1d"] == pytest.approx(
        autumn_prices[autumn_prices.index.tz_convert(market_timezone()).hour == 2].mean()
    )
