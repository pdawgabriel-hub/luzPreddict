from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from src.processing.clean import clean_prices
from src.utils.calendar import local_day_hours


def _raw(hours, start="2026-01-01T00:00Z", drop=()):
    """`hours` horas seguidas con precio = número de hora, quitando las posiciones de `drop`."""
    index = pd.date_range(start, periods=hours, freq="h", tz="UTC")
    raw = pd.DataFrame({"datetime": index, "price": np.arange(hours, dtype=float)})
    return raw.drop(index=list(drop)).reset_index(drop=True)


def test_result_is_a_continuous_hourly_utc_index():
    df = clean_prices(_raw(48, drop=[10]))

    assert df.index.name == "datetime"
    assert str(df.index.tz) == "UTC"
    assert len(df) == 48
    assert (df.index[1:] - df.index[:-1] == pd.Timedelta(hours=1)).all()
    assert list(df.columns) == ["price", "is_interpolated"]


def test_short_gaps_are_interpolated_and_flagged():
    df = clean_prices(_raw(20, drop=[5, 6, 7]))  # hueco de 3 horas

    assert df["price"].iloc[5:8].tolist() == pytest.approx([5.0, 6.0, 7.0])
    assert df["is_interpolated"].iloc[5:8].all()
    assert df["is_interpolated"].sum() == 3


def test_long_gaps_are_left_empty_entirely():
    df = clean_prices(_raw(20, drop=[5, 6, 7, 8]))  # hueco de 4 horas

    assert df["price"].iloc[5:9].isna().all()  # ni siquiera se rellenan las primeras horas
    assert not df["is_interpolated"].any()


def test_max_gap_is_configurable():
    df = clean_prices(_raw(20, drop=[5, 6, 7, 8]), max_gap_hours=4)
    assert df["price"].notna().all()


def test_duplicates_keep_the_last_value_and_order_is_fixed():
    raw = _raw(3)
    raw = pd.concat([raw.iloc[[2, 0, 1]], raw.iloc[[1]].assign(price=99.0)])  # desordenado; el 99 llega el último

    df = clean_prices(raw)

    assert df["price"].tolist() == [0.0, 99.0, 2.0]


def test_local_times_are_converted_to_utc():
    raw = _raw(3).assign(datetime=lambda d: d["datetime"].dt.tz_convert("Europe/Madrid"))
    assert clean_prices(raw).index[0] == pd.Timestamp("2026-01-01T00:00Z")


@pytest.mark.parametrize(
    "first_day, n_days, expected_hours",
    [
        (date(2026, 3, 28), 3, 24 + 23 + 24),  # cambio a horario de verano
        (date(2026, 10, 24), 3, 24 + 25 + 24),  # cambio a horario de invierno
    ],
)
def test_no_artificial_gaps_around_clock_changes(first_day, n_days, expected_hours):
    hours = [h for i in range(n_days) for h in local_day_hours(first_day + timedelta(days=i))]
    raw = pd.DataFrame({"datetime": pd.to_datetime(hours), "price": 1.0})

    df = clean_prices(raw)

    assert len(df) == expected_hours
    assert not df["is_interpolated"].any()
    assert df["price"].notna().all()


def test_naive_datetimes_are_rejected():
    raw = _raw(3).assign(datetime=lambda d: d["datetime"].dt.tz_localize(None))
    with pytest.raises(ValueError, match="zona horaria"):
        clean_prices(raw)


def test_empty_input():
    df = clean_prices(_raw(0))
    assert df.empty
    assert list(df.columns) == ["price", "is_interpolated"]
