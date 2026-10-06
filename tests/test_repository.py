from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from src.db import repository as repo
from src.db.models import ModelArtifact, ModelRun

MADRID = ZoneInfo("Europe/Madrid")
START = datetime(2026, 10, 1, tzinfo=UTC)


def _hours(n, start=START, price=100.0):
    return [(start + timedelta(hours=i), price + i) for i in range(n)]


# --- Precios ---


def test_save_and_read_prices(db_session):
    assert repo.upsert_prices(db_session, _hours(48)) == 48

    rows = repo.get_prices(db_session)

    assert len(rows) == 48
    assert rows[0] == (START, 100.0)
    assert all(ts.tzinfo == UTC for ts, _ in rows)
    assert repo.last_price_datetime(db_session) == START + timedelta(hours=47)


def test_read_prices_in_a_range(db_session):
    repo.upsert_prices(db_session, _hours(48))

    rows = repo.get_prices(db_session, start=START + timedelta(hours=24), end=START + timedelta(hours=30))

    assert [ts for ts, _ in rows] == [START + timedelta(hours=h) for h in range(24, 30)]


def test_saving_the_same_prices_twice_changes_nothing(db_session):
    repo.upsert_prices(db_session, _hours(24))

    assert repo.upsert_prices(db_session, _hours(24)) == 0
    assert len(repo.get_prices(db_session)) == 24


def test_changed_prices_are_updated(db_session):
    repo.upsert_prices(db_session, _hours(24, price=100.0))

    changed = repo.upsert_prices(
        db_session, [(START, 999.0)] + _hours(24, price=100.0)[1:] + _hours(1, START + timedelta(hours=24))
    )

    assert changed == 2  # una hora cambiada y una nueva
    assert repo.get_prices(db_session)[0] == (START, 999.0)


def test_empty_database_has_no_last_price(db_session):
    assert repo.last_price_datetime(db_session) is None
    assert repo.get_prices(db_session) == []


# --- Generación ---


def test_save_and_read_generation(db_session):
    rows = [(date(2026, 10, d), tech, 100.0 * d) for d in (1, 2, 3) for tech in ("Eólica", "Nuclear")]
    assert repo.upsert_generation(db_session, rows) == 6

    assert repo.get_generation(db_session, start=date(2026, 10, 2), end=date(2026, 10, 3)) == rows[2:]
    assert repo.last_generation_date(db_session) == date(2026, 10, 3)
    assert repo.upsert_generation(db_session, rows) == 0  # idempotente


# --- Previsiones ---


def _forecast(generated_at=datetime(2026, 10, 6, 19, 30, tzinfo=UTC), price=150.0, model="precio_ayer"):
    day_start = datetime(2026, 10, 7, tzinfo=MADRID)
    return repo.ForecastToSave(
        target_day=date(2026, 10, 7),
        generated_at=generated_at,
        model=model,
        hours=_hours(24, start=day_start.astimezone(UTC), price=price),
        fallback_reason="FileNotFoundError: sin modelo" if model == "precio_ayer" else None,
    )


def test_save_and_read_a_forecast(db_session):
    run = repo.save_forecast(db_session, _forecast())

    assert run.id is not None
    assert run.model == "precio_ayer"
    assert len(run.hours) == 24
    assert run.hours[0].prediction == 150.0
    assert repo.latest_forecast(db_session, date(2026, 10, 7)).id == run.id


def test_saving_the_same_run_twice_does_not_duplicate_it(db_session):
    first = repo.save_forecast(db_session, _forecast(price=150.0))
    second = repo.save_forecast(db_session, _forecast(price=160.0))

    assert second.id == first.id
    assert db_session.query(ModelRun).count() == 1
    assert [h.prediction for h in second.hours][:2] == [160.0, 161.0]


def test_latest_forecast_is_the_most_recently_generated(db_session):
    repo.save_forecast(db_session, _forecast(generated_at=datetime(2026, 10, 6, 19, 30, tzinfo=UTC)))
    later = repo.save_forecast(
        db_session, _forecast(generated_at=datetime(2026, 10, 6, 21, 30, tzinfo=UTC), price=170.0)
    )

    assert repo.latest_forecast(db_session, date(2026, 10, 7)).id == later.id
    assert repo.latest_forecast(db_session, date(2026, 10, 8)) is None


def test_naive_datetimes_are_rejected(db_session):
    with pytest.raises(Exception, match="Fecha sin zona horaria"):
        repo.upsert_prices(db_session, [(datetime(2026, 10, 1, 0), 1.0)])


# --- Modelo entrenado ---


def _artifact(version, trained_at, data=b"modelo"):
    return repo.ArtifactToSave(
        version=version,
        trained_at=trained_at,
        train_start=trained_at - timedelta(days=730),
        train_end=trained_at,
        training_rows=17_520,
        features=["hour"],
        params={"objective": "l1"},
        metrics={"models": {"lightgbm": {"mae": 16.0}}},
        library_versions={"lightgbm": "4.7.0"},
        format_version=1,
        data=data,
    )


def test_save_and_read_model_artifacts(db_session):
    old = _artifact("20261001-190000", datetime(2026, 10, 1, 19, tzinfo=UTC))
    new = _artifact("20261006-190000", datetime(2026, 10, 6, 19, tzinfo=UTC), data=b"nuevo")
    repo.save_model_artifact(db_session, new)
    repo.save_model_artifact(db_session, old)

    assert repo.get_model_artifact(db_session).version == new.version  # el más reciente, no el último guardado
    assert repo.get_model_artifact(db_session, old.version).data == b"modelo"
    assert repo.get_model_artifact(db_session, "no-existe") is None


def test_saving_the_same_version_again_replaces_it(db_session):
    trained_at = datetime(2026, 10, 6, 19, tzinfo=UTC)
    repo.save_model_artifact(db_session, _artifact("v1", trained_at, data=b"a"))
    repo.save_model_artifact(db_session, _artifact("v1", trained_at, data=b"b"))
    db_session.expire_all()

    assert repo.get_model_artifact(db_session, "v1").data == b"b"
    assert db_session.query(ModelArtifact).count() == 1


def test_no_model_in_an_empty_database(db_session):
    assert repo.get_model_artifact(db_session) is None


# --- Error diario ---


def test_save_and_read_daily_errors(db_session):
    rows = [
        (date(2026, 10, 5), "lightgbm", 16.0, 22.0, -1.0, 24),
        (date(2026, 10, 5), "precio_ayer", 28.5, 44.7, 0.0, 24),
        (date(2026, 10, 6), "lightgbm", 14.0, 20.0, 1.5, 24),
    ]
    assert repo.upsert_daily_errors(db_session, rows) == 3
    assert repo.upsert_daily_errors(db_session, rows) == 0  # idempotente

    lightgbm = repo.get_daily_errors(db_session, model="lightgbm")
    assert [(e.day, e.mae) for e in lightgbm] == [(date(2026, 10, 5), 16.0), (date(2026, 10, 6), 14.0)]
    assert len(repo.get_daily_errors(db_session, start=date(2026, 10, 6))) == 1


def test_recomputed_daily_error_is_updated(db_session):
    repo.upsert_daily_errors(db_session, [(date(2026, 10, 5), "lightgbm", 16.0, 22.0, -1.0, 23)])
    db_session.flush()
    first = repo.get_daily_errors(db_session)[0]
    computed_at = first.computed_at

    # Al llegar la hora que faltaba, el error del día se recalcula
    changed = repo.upsert_daily_errors(db_session, [(date(2026, 10, 5), "lightgbm", 15.0, 21.0, -0.5, 24)])
    db_session.expire_all()

    updated = repo.get_daily_errors(db_session)[0]
    assert changed == 1
    assert (updated.mae, updated.n) == (15.0, 24)
    assert updated.computed_at >= computed_at
