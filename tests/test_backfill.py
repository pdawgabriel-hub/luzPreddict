from datetime import date

import pytest

from src.ingestion import backfill, generation, prices
from src.utils.config import get_settings
from tests.fakes import FakeClient, FakeGenerationClient

TODAY = date(2026, 10, 4)


@pytest.fixture
def path(tmp_path):
    return tmp_path / "pvpc.parquet"


def test_default_end_is_tomorrow():
    assert backfill.default_end(TODAY) == date(2026, 10, 5)


def test_first_run_downloads_from_the_start_of_the_history(path):
    client = FakeClient()

    df = backfill.update_pvpc(client=client, path=path, today=TODAY)

    assert client.calls == [(prices.PVPC_PATH, get_settings().history_start, date(2026, 10, 5))]
    assert path.exists()
    assert len(prices.load_pvpc(path)) == len(df)


def test_incremental_run_starts_from_the_last_saved_day(path):
    backfill.update_pvpc(start=date(2026, 9, 1), end=date(2026, 9, 30), client=FakeClient(price=1.0), path=path)
    client = FakeClient(price=2.0)

    df = backfill.update_pvpc(client=client, path=path, today=TODAY)

    # Se vuelve a pedir el 30 de septiembre por si estaba incompleto
    assert client.calls == [(prices.PVPC_PATH, date(2026, 9, 30), date(2026, 10, 5))]
    assert df["datetime"].is_unique
    first_day = df[df["datetime"].dt.tz_convert("Europe/Madrid").dt.date == date(2026, 9, 1)]
    assert first_day["price"].eq(1.0).all()
    assert df["price"].iloc[-1] == 2.0


def test_full_run_ignores_the_saved_file(path):
    backfill.update_pvpc(start=date(2026, 9, 1), end=date(2026, 9, 2), client=FakeClient(), path=path)
    client = FakeClient()

    backfill.update_pvpc(full=True, client=client, path=path, today=TODAY)

    assert client.calls[0][1] == get_settings().history_start


def test_nothing_to_download_when_already_up_to_date(path):
    backfill.update_pvpc(start=date(2026, 10, 6), end=date(2026, 10, 6), client=FakeClient(), path=path)
    client = FakeClient()

    df = backfill.update_pvpc(client=client, path=path, today=TODAY)

    assert client.calls == []
    assert len(df) == 24


def test_warns_about_missing_hours(path, caplog):
    class GappyClient(FakeClient):
        def fetch(self, *args, **kwargs):
            series = super().fetch(*args, **kwargs)
            return {name: points[:5] + points[8:] for name, points in series.items()}

    backfill.update_pvpc(start=date(2026, 9, 1), end=date(2026, 9, 1), client=GappyClient(), path=path)

    assert "faltan 3 horas" in caplog.text


# --- Generación ---


def test_generation_first_run_goes_until_today(tmp_path):
    client = FakeGenerationClient()

    backfill.update_generation(client=client, path=tmp_path / "gen.parquet", today=TODAY)

    assert client.calls == [(generation.GENERATION_PATH, get_settings().history_start, TODAY, "day")]


def test_generation_incremental_run_starts_from_the_last_saved_day(tmp_path):
    path = tmp_path / "gen.parquet"
    backfill.update_generation(start=date(2026, 9, 1), end=date(2026, 9, 30), client=FakeGenerationClient(), path=path)
    client = FakeGenerationClient(mwh={"Eólica": 7.0, "Nuclear": 50.0})

    df = backfill.update_generation(client=client, path=path, today=TODAY)

    assert client.calls[0][1:3] == (date(2026, 9, 30), TODAY)
    assert df["date"].nunique() == 34  # del 1 de septiembre al 4 de octubre
    last_wind = df[(df["date"] == TODAY) & (df["technology"] == "Eólica")]["mwh"]
    assert last_wind.tolist() == [7.0]


def test_generation_warns_about_missing_days(tmp_path, caplog):
    path = tmp_path / "gen.parquet"
    backfill.update_generation(start=date(2026, 9, 1), end=date(2026, 9, 2), client=FakeGenerationClient(), path=path)
    backfill.update_generation(start=date(2026, 9, 5), end=date(2026, 9, 5), client=FakeGenerationClient(), path=path)

    assert "faltan 2 días" in caplog.text


# --- Línea de comandos ---


@pytest.mark.parametrize(
    "argv, expected",
    [([], ["pvpc", "generacion"]), (["--only", "pvpc"], ["pvpc"]), (["--only", "generacion"], ["generacion"])],
)
def test_cli_runs_the_selected_datasets(monkeypatch, argv, expected):
    ran = []
    monkeypatch.setattr(backfill, "update_pvpc", lambda **kw: ran.append("pvpc"))
    monkeypatch.setattr(backfill, "update_generation", lambda **kw: ran.append("generacion"))

    backfill.main(argv)

    assert ran == expected
