from datetime import UTC, date, datetime

import pandas as pd
import pytest

from src.ingestion import generation, prices
from src.processing import dataset
from tests.fakes import FakeClient, FakeGenerationClient


@pytest.fixture
def price_table():
    """Tres días de PVPC con el formato de src.ingestion.prices (incluye el día de 25 h)."""
    return prices.fetch_pvpc(date(2026, 10, 24), date(2026, 10, 26), client=FakeClient(price=123.4))


@pytest.fixture
def generation_table():
    return generation.fetch_generation(date(2026, 10, 1), date(2026, 10, 3), client=FakeGenerationClient())


def test_prices_roundtrip_is_identical_to_the_parquet_format(db_session, price_table):
    assert dataset.save_prices(db_session, price_table) == len(price_table) == 24 + 25 + 24

    loaded = dataset.load_prices(db_session)

    pd.testing.assert_frame_equal(loaded, price_table)
    assert str(loaded["datetime"].dtype) == "datetime64[us, UTC]"


def test_load_prices_in_a_window(db_session, price_table):
    dataset.save_prices(db_session, price_table)
    since = datetime(2026, 10, 25, 0, tzinfo=UTC)

    loaded = dataset.load_prices(db_session, since=since, until=datetime(2026, 10, 25, 6, tzinfo=UTC))

    assert loaded["datetime"].tolist() == list(pd.date_range(since, periods=6, freq="h"))


def test_load_clean_prices_is_ready_for_features(db_session, price_table):
    dataset.save_prices(db_session, price_table)

    clean = dataset.load_clean_prices(db_session)

    assert list(clean.columns) == ["price", "is_interpolated"]
    assert clean.index.name == "datetime"
    assert len(clean) == len(price_table)


def test_generation_roundtrip_is_identical_to_the_parquet_format(db_session, generation_table):
    assert dataset.save_generation(db_session, generation_table) == 6

    loaded = dataset.load_generation(db_session)

    pd.testing.assert_frame_equal(loaded, generation_table)


def test_load_generation_in_a_window(db_session, generation_table):
    dataset.save_generation(db_session, generation_table)

    loaded = dataset.load_generation(db_session, since=date(2026, 10, 2), until=date(2026, 10, 2))

    assert set(loaded["date"]) == {date(2026, 10, 2)}


def test_saving_twice_changes_nothing(db_session, price_table, generation_table):
    dataset.save_prices(db_session, price_table)
    dataset.save_generation(db_session, generation_table)

    assert dataset.save_prices(db_session, price_table) == 0
    assert dataset.save_generation(db_session, generation_table) == 0


def test_empty_database_gives_empty_tables_with_the_right_format(db_session):
    pd.testing.assert_frame_equal(dataset.load_prices(db_session), prices.empty_prices())
    pd.testing.assert_frame_equal(dataset.load_generation(db_session), generation.empty_generation())
    assert dataset.load_clean_prices(db_session).empty


def test_saving_empty_tables_does_nothing(db_session):
    assert dataset.save_prices(db_session, prices.empty_prices()) == 0
    assert dataset.save_generation(db_session, generation.empty_generation()) == 0
