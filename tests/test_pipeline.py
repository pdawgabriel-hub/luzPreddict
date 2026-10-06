from datetime import timedelta

import pytest

from src import pipeline
from src.db import repository
from src.db.models import ModelRun
from src.ingestion import prices
from tests.fakes import SEEDED_LAST_DAY as LAST_DAY
from tests.fakes import FakeReeClient


def test_backfill_continues_from_the_last_saved_day(seeded):
    client = FakeReeClient(published_until=LAST_DAY + timedelta(days=2))

    result = pipeline.backfill(seeded, client=client, today=LAST_DAY + timedelta(days=1))

    pvpc_calls = [c for c in client.calls if c[0] == prices.PVPC_PATH]
    assert pvpc_calls[0][1:] == (LAST_DAY, LAST_DAY + timedelta(days=2))  # repite el último día y llega a mañana
    assert result.last_price_day == LAST_DAY + timedelta(days=2)
    assert result.prices_changed > 0
    assert repository.last_generation_date(seeded) == LAST_DAY + timedelta(days=1)


def test_train_saves_the_model_in_the_database(seeded, fast_model):
    version = pipeline.train(seeded, metrics_days=3)

    stored = repository.get_model_artifact(seeded)
    assert stored.version == version
    assert set(stored.metrics["models"]) == {"lightgbm", "precio_ayer", "media_7_dias"}


def test_daily_saves_a_forecast_for_the_first_unpublished_day(seeded, sessions, fast_model):
    pipeline.train(seeded, metrics_days=3)
    client = FakeReeClient(published_until=LAST_DAY + timedelta(days=1))

    result = pipeline.daily(client=client, today=LAST_DAY, session_factory=sessions)

    assert result.status == "completo"  # mañana ya está publicado
    assert result.forecast.day == LAST_DAY + timedelta(days=2)
    assert result.forecast.model == "lightgbm"
    run = repository.latest_forecast(seeded, result.forecast.day)
    assert run.id == result.run_id
    assert run.model_version == result.forecast.model_version
    assert len(run.hours) == 24


def test_daily_is_pending_when_tomorrow_is_not_published_yet(seeded, sessions):
    client = FakeReeClient(published_until=LAST_DAY)  # REE aún no ha publicado mañana

    result = pipeline.daily(client=client, today=LAST_DAY, session_factory=sessions)

    assert result.status == "pendiente"
    assert result.forecast.day == LAST_DAY + timedelta(days=1)  # se prevé mañana igualmente
    assert result.forecast.model == "precio_ayer"  # no hay modelo guardado: respaldo


def test_predict_command_needs_prices():
    with pytest.raises(ValueError, match="make backfill"):
        pipeline.forecast_next_day(_EmptyRepositorySession())


class _EmptyRepositorySession:
    """Sesión mínima para una base de datos sin precios."""

    def scalar(self, *args, **kwargs):
        return None


def test_repeating_daily_does_not_duplicate_the_forecast(seeded, sessions):
    client = FakeReeClient(published_until=LAST_DAY)

    first = pipeline.daily(client=client, today=LAST_DAY, session_factory=sessions)
    second = pipeline.daily(client=client, today=LAST_DAY, session_factory=sessions)

    assert second.run_id == first.run_id
    assert seeded.query(ModelRun).count() == 1


def test_a_changed_forecast_is_saved_as_a_new_run(seeded, sessions, fast_model):
    client = FakeReeClient(published_until=LAST_DAY)
    first = pipeline.daily(client=client, today=LAST_DAY, session_factory=sessions)  # respaldo, sin modelo

    pipeline.train(seeded, metrics_days=3)
    second = pipeline.daily(client=client, today=LAST_DAY, session_factory=sessions)  # ya con LightGBM

    assert second.run_id != first.run_id
    assert repository.latest_forecast(seeded, second.forecast.day).model == "lightgbm"
