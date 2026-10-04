from datetime import date

import pytest

from src.ingestion import backfill, prices
from src.utils.config import get_settings
from tests.fakes import FakeClient

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
