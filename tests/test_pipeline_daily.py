"""Varios días de la tarea diaria seguidos, como en producción."""

from datetime import timedelta

import pandas as pd
import pytest

from src import pipeline
from src.db import repository
from src.db.models import DailyError, ModelRun
from src.ingestion.ree_client import ReeApiError
from src.models.evaluate import regression_metrics
from src.models.lightgbm_model import LightGBMForecaster
from src.models.predict import FALLBACK_BASELINE
from src.models.registry import ModelArtifact, build_metadata, save_to_db
from src.processing import dataset
from src.processing.features import FEATURES, build_features
from src.utils.calendar import local_day_hours
from tests.fakes import FAST_PARAMS, FakeReeClient
from tests.fakes import SEEDED_LAST_DAY as DAY1

DAY2, DAY3, DAY4 = (DAY1 + timedelta(days=i) for i in (1, 2, 3))


def _real_prices(session, day):
    hours = local_day_hours(day)
    return dict(repository.get_prices(session, start=hours[0], end=hours[-1] + timedelta(hours=1)))


# --- Flujo completo ---


def test_several_days_of_the_daily_task(seeded, sessions, fast_model):
    pipeline.train(seeded, metrics_days=3)

    # Día 1, 19:30 UTC: REE aún no ha publicado mañana
    first = pipeline.daily(client=FakeReeClient(published_until=DAY1), today=DAY1, session_factory=sessions)
    assert (first.status, first.forecast.day, first.errors_updated) == ("pendiente", DAY2, 0)

    # Reintento a las 21:30: REE ya ha publicado el día 2
    retry = pipeline.daily(
        client=FakeReeClient(published_until=DAY2, price=150.0), today=DAY1, session_factory=sessions
    )
    assert (retry.status, retry.forecast.day) == ("completo", DAY3)
    assert retry.errors_updated == 1  # la previsión del día 2 ya se puede evaluar

    # Día siguiente: REE publica el día 3
    next_day = pipeline.daily(
        client=FakeReeClient(published_until=DAY3, price=150.0), today=DAY2, session_factory=sessions
    )
    assert (next_day.status, next_day.forecast.day) == ("completo", DAY4)
    assert next_day.errors_updated == 1  # solo el día 3 es nuevo; el día 2 no ha cambiado

    assert seeded.query(ModelRun).count() == 3
    assert [e.day for e in repository.get_daily_errors(seeded)] == [DAY2, DAY3]


def test_daily_error_compares_the_forecast_with_the_real_price(seeded, sessions, fast_model):
    pipeline.train(seeded, metrics_days=3)
    pipeline.daily(client=FakeReeClient(published_until=DAY1), today=DAY1, session_factory=sessions)
    pipeline.daily(client=FakeReeClient(published_until=DAY2, price=150.0), today=DAY1, session_factory=sessions)

    run = repository.latest_forecast(seeded, DAY2)
    real = _real_prices(seeded, DAY2)
    expected = regression_metrics(
        pd.Series([real[h.datetime] for h in run.hours]), pd.Series([h.prediction for h in run.hours])
    )
    error = seeded.get(DailyError, (DAY2, "lightgbm"))

    assert error.mae == pytest.approx(expected["mae"])
    assert error.rmse == pytest.approx(expected["rmse"])
    assert error.bias == pytest.approx(expected["bias"])
    assert error.n == 24


def test_repeating_a_whole_day_changes_nothing(seeded, sessions):
    client = FakeReeClient(published_until=DAY2, price=150.0)
    pipeline.daily(client=FakeReeClient(published_until=DAY1), today=DAY1, session_factory=sessions)
    pipeline.daily(client=client, today=DAY1, session_factory=sessions)

    again = pipeline.daily(client=client, today=DAY1, session_factory=sessions)

    assert again.backfill.prices_changed == 0
    assert again.errors_updated == 0
    assert seeded.query(ModelRun).count() == 2


# --- REE sin datos o caída ---


def test_ree_without_new_data_still_produces_tomorrows_forecast(seeded, sessions):
    result = pipeline.daily(client=FakeReeClient(published_until=DAY1), today=DAY1, session_factory=sessions)

    assert result.status == "pendiente"
    assert result.backfill.last_price_day == DAY1  # ningún día nuevo
    assert result.forecast.day == DAY2
    assert len(repository.latest_forecast(seeded, DAY2).hours) == 24


def test_ree_down_fails_the_task_without_saving_a_forecast(seeded, sessions):
    client = FakeReeClient(published_until=DAY1, error=ReeApiError("REE respondió 503: Service Unavailable"))

    with pytest.raises(ReeApiError, match="503"):
        pipeline.daily(client=client, today=DAY1, session_factory=sessions)

    assert seeded.query(ModelRun).count() == 0


# --- Respaldo ---


def _save_artifact(session, features=FEATURES, data=b"no es un modelo"):
    repository.save_model_artifact(
        session,
        repository.ArtifactToSave(
            version="20260209-190000",
            trained_at=local_day_hours(DAY1)[0],
            train_start=local_day_hours(DAY1)[0],
            train_end=local_day_hours(DAY1)[0],
            training_rows=1,
            features=list(features),
            params={},
            metrics={},
            library_versions={},
            format_version=1,
            data=data,
        ),
    )


def test_without_a_model_the_fallback_is_saved_and_evaluated(seeded, sessions):
    pipeline.daily(client=FakeReeClient(published_until=DAY1), today=DAY1, session_factory=sessions)
    pipeline.daily(client=FakeReeClient(published_until=DAY2, price=150.0), today=DAY1, session_factory=sessions)

    run = repository.latest_forecast(seeded, DAY2)
    assert (run.model, run.model_version) == (FALLBACK_BASELINE, None)
    assert "make train" in run.fallback_reason
    assert seeded.get(DailyError, (DAY2, FALLBACK_BASELINE)) is not None


def test_corrupt_model_in_the_database_activates_the_fallback(seeded, sessions):
    _save_artifact(seeded)

    result = pipeline.daily(client=FakeReeClient(published_until=DAY1), today=DAY1, session_factory=sessions)

    assert result.forecast.model == FALLBACK_BASELINE
    assert repository.latest_forecast(seeded, DAY2).model_version is None


def test_model_trained_with_other_features_activates_the_fallback(seeded, sessions):
    model = LightGBMForecaster(params=FAST_PARAMS, features=FEATURES[:-1])  # como si faltara una variable
    model.fit(build_features(dataset.load_clean_prices(seeded)))
    save_to_db(seeded, ModelArtifact(model=model, metadata=build_metadata(model)))

    result = pipeline.daily(client=FakeReeClient(published_until=DAY1), today=DAY1, session_factory=sessions)

    assert result.forecast.model == FALLBACK_BASELINE
    assert "IncompatibleModelError" in result.forecast.fallback_reason
