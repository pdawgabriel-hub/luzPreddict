from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.pool import NullPool

from src.db.models import DailyError, ForecastHour, GenerationDay, ModelArtifact, ModelRun, PriceHour
from src.db.session import check_test_database_url, make_engine, session_scope

MADRID = ZoneInfo("Europe/Madrid")
TABLES = {
    "price_hour": ["datetime"],
    "generation_day": ["date", "technology"],
    "model_artifact": ["version"],
    "model_run": ["id"],
    "forecast_hour": ["run_id", "datetime"],
    "daily_error": ["day", "model"],
}


def _artifact(version="20261006-190000"):
    now = datetime(2026, 10, 6, 17, tzinfo=UTC)
    return ModelArtifact(
        version=version,
        trained_at=now,
        train_start=datetime(2024, 10, 6, tzinfo=UTC),
        train_end=now,
        training_rows=17_520,
        features=["hour", "price_lag_1d"],
        params={"objective": "l1"},
        metrics={"models": {"lightgbm": {"mae": 16.0}}},
        library_versions={"lightgbm": "4.7.0"},
        format_version=1,
        data=b"\x00\x01modelo",
    )


# --- Estructura ---


def test_all_tables_exist_with_their_primary_keys(db_engine):
    inspector = inspect(db_engine)
    assert set(TABLES) <= set(inspector.get_table_names())
    for table, columns in TABLES.items():
        assert inspector.get_pk_constraint(table)["constrained_columns"] == columns
        assert inspector.get_pk_constraint(table)["name"] == f"pk_{table}"


# --- Fechas en UTC ---


def test_datetimes_are_stored_and_returned_in_utc(db_session):
    db_session.add(PriceHour(datetime=datetime(2026, 7, 1, 0, tzinfo=MADRID), price=100.5))
    db_session.flush()
    db_session.expire_all()

    stored = db_session.scalars(select(PriceHour)).one()

    assert stored.datetime == datetime(2026, 6, 30, 22, tzinfo=UTC)
    assert stored.datetime.tzinfo == UTC
    assert stored.updated_at is not None


def test_datetimes_without_timezone_are_rejected(db_session):
    db_session.add(PriceHour(datetime=datetime(2026, 7, 1, 0), price=1.0))
    with pytest.raises(StatementError, match="Fecha sin zona horaria"):
        db_session.flush()


# --- Claves y relaciones ---


def test_one_price_per_hour(db_session):
    hour = datetime(2026, 7, 1, tzinfo=UTC)
    db_session.add(PriceHour(datetime=hour, price=1.0))
    db_session.flush()
    db_session.add(PriceHour(datetime=hour.astimezone(MADRID), price=2.0))  # el mismo instante
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_one_generation_value_per_day_and_technology(db_session):
    db_session.add_all([GenerationDay(date=date(2026, 10, 1), technology=t, mwh=1.0) for t in ("Eólica", "Solar")])
    db_session.flush()
    db_session.add(GenerationDay(date=date(2026, 10, 1), technology="Eólica", mwh=2.0))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_run_with_its_hours_and_artifact(db_session):
    db_session.add(_artifact())
    run = ModelRun(
        target_day=date(2026, 10, 7),
        generated_at=datetime(2026, 10, 6, 19, 30, tzinfo=UTC),
        model="lightgbm",
        model_version="20261006-190000",
        hours=[
            ForecastHour(datetime=datetime(2026, 10, 6, 22 + i, tzinfo=UTC), prediction=150.0 + i) for i in range(2)
        ],
    )
    db_session.add(run)
    db_session.flush()
    db_session.expire_all()

    stored = db_session.get(ModelRun, run.id)
    assert [h.prediction for h in stored.hours] == [150.0, 151.0]
    assert stored.fallback_reason is None


def test_forecast_hours_need_an_existing_run(db_session):
    db_session.add(ForecastHour(run_id=999_999, datetime=datetime(2026, 10, 7, tzinfo=UTC), prediction=1.0))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_deleting_a_run_deletes_its_hours(db_session):
    run = ModelRun(
        target_day=date(2026, 10, 7),
        generated_at=datetime(2026, 10, 6, 19, 30, tzinfo=UTC),
        model="precio_ayer",
        fallback_reason="FileNotFoundError: sin modelo",
        hours=[ForecastHour(datetime=datetime(2026, 10, 6, 22, tzinfo=UTC), prediction=1.0)],
    )
    db_session.add(run)
    db_session.flush()

    db_session.delete(run)
    db_session.flush()

    assert db_session.scalars(select(ForecastHour)).all() == []


def test_deleting_an_artifact_keeps_its_runs(db_session):
    artifact = _artifact()
    run = ModelRun(
        target_day=date(2026, 10, 7), generated_at=artifact.trained_at, model="lightgbm", model_version=artifact.version
    )
    db_session.add_all([artifact, run])
    db_session.flush()

    db_session.delete(artifact)
    db_session.flush()
    db_session.expire_all()

    assert db_session.get(ModelRun, run.id).model_version is None


def test_artifact_keeps_bytes_and_metadata(db_session):
    db_session.add(_artifact())
    db_session.flush()
    db_session.expire_all()

    stored = db_session.get(ModelArtifact, "20261006-190000")

    assert stored.data == b"\x00\x01modelo"
    assert stored.metrics == {"models": {"lightgbm": {"mae": 16.0}}}
    assert stored.features == ["hour", "price_lag_1d"]


def test_one_daily_error_per_day_and_model(db_session):
    db_session.add(DailyError(day=date(2026, 10, 6), model="lightgbm", mae=16.0, rmse=22.0, bias=-1.0, n=24))
    db_session.flush()
    db_session.add(DailyError(day=date(2026, 10, 6), model="lightgbm", mae=1.0, rmse=1.0, bias=0.0, n=24))
    with pytest.raises(IntegrityError):
        db_session.flush()


# --- Sesión y conexión ---


def test_session_scope_commits_on_success_and_rolls_back_on_error(db_engine):
    hour = datetime(2030, 1, 1, tzinfo=UTC)
    try:
        with pytest.raises(RuntimeError), session_scope(db_engine) as session:
            session.add(PriceHour(datetime=hour, price=1.0))
            raise RuntimeError("algo falla a mitad")
        with session_scope(db_engine) as session:
            assert session.get(PriceHour, hour) is None

        with session_scope(db_engine) as session:
            session.add(PriceHour(datetime=hour, price=2.0))
        with session_scope(db_engine) as session:
            assert session.get(PriceHour, hour).price == 2.0
    finally:
        with session_scope(db_engine) as session:
            session.query(PriceHour).filter_by(datetime=hour).delete()


def test_engine_uses_null_pool(db_engine):
    assert isinstance(db_engine.pool, NullPool)


def test_missing_database_url_is_a_clear_error(monkeypatch):
    monkeypatch.setattr("src.db.session.get_settings", lambda: type("S", (), {"database_url": None})())
    with pytest.raises(RuntimeError, match="Falta DATABASE_URL"):
        make_engine()


@pytest.mark.parametrize(
    "test_url, real_url, message",
    [
        ("postgresql+psycopg://u:p@localhost:5433/luzpreddict", None, "debe terminar en _test"),
        (
            "postgresql+psycopg://u:p@localhost:5433/datos_test",
            "postgresql+psycopg://otro:x@localhost:5433/datos_test",
            "misma base de datos",
        ),
    ],
)
def test_tests_refuse_to_use_the_working_database(test_url, real_url, message):
    with pytest.raises(RuntimeError, match=message):
        check_test_database_url(test_url, real_url)


def test_a_separate_test_database_is_accepted():
    check_test_database_url(
        "postgresql+psycopg://u:p@localhost:5433/luzpreddict_test",
        "postgresql+psycopg://u:p@localhost:5433/luzpreddict",
    )
