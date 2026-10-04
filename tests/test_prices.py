from datetime import UTC, date, datetime

import pandas as pd

from src.ingestion import prices
from tests.fakes import FakeClient


def _prices(hours, price, start="2026-01-01T00:00Z"):
    index = pd.date_range(start, periods=hours, freq="h", tz="UTC")
    return pd.DataFrame({"datetime": index, "price": float(price)})


def test_fetch_pvpc_returns_utc_hours_for_the_local_days():
    client = FakeClient()

    df = prices.fetch_pvpc(date(2026, 10, 24), date(2026, 10, 25), client=client)

    assert client.calls == [(prices.PVPC_PATH, date(2026, 10, 24), date(2026, 10, 25))]
    assert list(df.columns) == ["datetime", "price"]
    assert str(df["datetime"].dtype) == "datetime64[us, UTC]"
    assert len(df) == 24 + 25  # el 25 de octubre tiene 25 horas
    assert df["datetime"].is_monotonic_increasing


def test_fetch_pvpc_without_the_series_returns_an_empty_table():
    df = prices.fetch_pvpc(date(2026, 1, 1), date(2026, 1, 1), client=FakeClient(series="Otra serie"))
    assert df.empty
    assert list(df.columns) == ["datetime", "price"]


def test_merge_prices_keeps_new_values_on_overlap():
    existing = _prices(48, 1.0)
    new = _prices(48, 2.0, start="2026-01-02T00:00Z")

    merged = prices.merge_prices(existing, new)

    assert len(merged) == 72
    assert merged["datetime"].is_unique
    assert merged.loc[merged["datetime"] < datetime(2026, 1, 2, tzinfo=UTC), "price"].eq(1.0).all()
    assert merged.loc[merged["datetime"] >= datetime(2026, 1, 2, tzinfo=UTC), "price"].eq(2.0).all()


def test_merge_prices_with_empty_tables():
    assert prices.merge_prices(prices.empty_prices(), prices.empty_prices()).empty
    assert len(prices.merge_prices(prices.empty_prices(), _prices(3, 1.0))) == 3


def test_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "raw" / "pvpc.parquet"
    original = _prices(5, 123.45)

    prices.save_pvpc(original, path)
    loaded = prices.load_pvpc(path)

    pd.testing.assert_frame_equal(loaded, prices.merge_prices(prices.empty_prices(), original))
    assert str(loaded["datetime"].dt.tz) == "UTC"


def test_load_missing_file_returns_empty_table(tmp_path):
    assert prices.load_pvpc(tmp_path / "no-existe.parquet").empty
