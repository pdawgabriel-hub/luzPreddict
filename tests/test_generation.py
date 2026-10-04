from datetime import date

import pandas as pd

from src.ingestion import generation
from tests.fakes import FakeGenerationClient


def _table(rows):
    return pd.DataFrame(rows, columns=generation.COLUMNS)


def test_fetch_generation_uses_local_days_and_drops_the_total():
    client = FakeGenerationClient()

    df = generation.fetch_generation(date(2026, 10, 24), date(2026, 10, 26), client=client)

    assert client.calls == [(generation.GENERATION_PATH, date(2026, 10, 24), date(2026, 10, 26), "day")]
    assert list(df.columns) == generation.COLUMNS
    # REE fecha cada día a medianoche local (22:00 o 23:00 UTC del día anterior)
    assert sorted(df["date"].unique()) == [date(2026, 10, 24), date(2026, 10, 25), date(2026, 10, 26)]
    assert set(df["technology"]) == {"Eólica", "Nuclear"}
    assert len(df) == 6


def test_fetch_generation_without_data_returns_an_empty_table():
    df = generation.fetch_generation(date(2026, 1, 1), date(2026, 1, 1), client=FakeGenerationClient(mwh={}))
    assert df.empty
    assert list(df.columns) == generation.COLUMNS


def test_merge_generation_keeps_new_values_for_the_same_day_and_technology():
    existing = _table([(date(2026, 9, 1), "Eólica", 1.0), (date(2026, 9, 2), "Eólica", 1.0)])
    new = _table([(date(2026, 9, 2), "Eólica", 2.0), (date(2026, 9, 2), "Nuclear", 3.0)])

    merged = generation.merge_generation(existing, new)

    assert merged.values.tolist() == [
        [date(2026, 9, 1), "Eólica", 1.0],
        [date(2026, 9, 2), "Eólica", 2.0],
        [date(2026, 9, 2), "Nuclear", 3.0],
    ]


def test_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "raw" / "generation.parquet"
    original = generation.fetch_generation(date(2026, 9, 1), date(2026, 9, 3), client=FakeGenerationClient())

    generation.save_generation(original, path)

    pd.testing.assert_frame_equal(generation.load_generation(path), original)


def test_load_missing_file_returns_empty_table(tmp_path):
    assert generation.load_generation(tmp_path / "no-existe.parquet").empty


def test_renewable_technologies_match_ree_names():
    assert "Eólica" in generation.RENEWABLE_TECHNOLOGIES
    assert "Solar fotovoltaica" in generation.RENEWABLE_TECHNOLOGIES
    assert "Nuclear" not in generation.RENEWABLE_TECHNOLOGIES
    assert "Ciclo combinado" not in generation.RENEWABLE_TECHNOLOGIES
