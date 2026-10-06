from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from src.db import repository as repo
from src.db.models import ModelRun

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
