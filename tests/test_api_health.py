from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from src.api import deps
from src.api.main import create_app
from src.api.middleware import REQUEST_ID_HEADER
from src.api.routers.health import MAX_MODEL_AGE_DAYS, build_health
from src.db import repository
from src.db.session import make_engine, session_scope
from src.utils.calendar import local_day_hours
from src.utils.config import Settings

MADRID = ZoneInfo("Europe/Madrid")
TODAY = date(2026, 10, 6)
NOW = datetime(2026, 10, 6, 20, 30, tzinfo=MADRID).astimezone(UTC)  # después de que REE publique
TOMORROW = TODAY + timedelta(days=1)


def last_hour_of(day):
    return local_day_hours(day)[-1].astimezone(UTC)


def run(target_day=TOMORROW, model="lightgbm", fallback_reason=None):
    return SimpleNamespace(
        target_day=target_day,
        generated_at=NOW - timedelta(minutes=5),
        model=model,
        model_version="20261004-030000" if model == "lightgbm" else None,
        fallback_reason=fallback_reason,
    )


def artifact(age_days=2):
    trained_at = NOW - timedelta(days=age_days, hours=1)
    return SimpleNamespace(
        version="20261004-030000",
        trained_at=trained_at,
        train_end=trained_at - timedelta(days=1),
        training_rows=17_520,
    )


# --- Avisos ---


def test_everything_up_to_date_is_ok():
    health = build_health(NOW, last_hour_of(TOMORROW), run(), artifact())

    assert health.status == "ok"
    assert health.warnings == []
    assert health.prices.last_day == TOMORROW
    assert health.prices.has_tomorrow
    assert health.model.age_days == 2


def test_before_ree_publishes_tomorrow_is_still_ok():
    health = build_health(NOW, last_hour_of(TODAY), run(), artifact())

    assert health.status == "ok"
    assert not health.prices.has_tomorrow


def test_missing_todays_prices_is_degraded():
    health = build_health(NOW, last_hour_of(TODAY - timedelta(days=1)), run(), artifact())

    assert health.status == "degraded"
    assert health.warnings == ["El último precio es del 2026-10-05: faltan los de hoy"]


def test_old_forecast_and_fallback_are_reported():
    health = build_health(
        NOW, last_hour_of(TODAY), run(target_day=TODAY, model="precio_ayer", fallback_reason="sin modelo"), artifact()
    )

    assert health.warnings == [
        "La última previsión es para el 2026-10-06: no hay previsión de mañana",
        "La última previsión usa la referencia precio_ayer: sin modelo",
    ]
    assert health.forecast.model_version is None


def test_old_model_is_reported():
    assert build_health(NOW, last_hour_of(TODAY), run(), artifact(MAX_MODEL_AGE_DAYS)).status == "ok"

    health = build_health(NOW, last_hour_of(TODAY), run(), artifact(MAX_MODEL_AGE_DAYS + 1))
    assert health.warnings == ["El modelo tiene 15 días: el reentrenamiento semanal no se está ejecutando"]


def test_empty_database():
    health = build_health(NOW, None, None, None)

    assert health.status == "degraded"
    assert len(health.warnings) == 3
    assert health.prices.last_hour is None and not health.prices.has_tomorrow
    assert health.forecast is None and health.model is None


def test_times_are_given_in_madrid_time():
    health = build_health(NOW, last_hour_of(TODAY), run(), artifact())

    assert health.checked_at.utcoffset() == timedelta(hours=2)  # horario de verano
    assert health.prices.last_hour == datetime(2026, 10, 6, 23, tzinfo=MADRID)
    assert health.prices.last_hour.utcoffset() == timedelta(hours=2)


# --- Ruta, contra la base de datos de pruebas ---


@pytest.fixture
def app(db_session):
    app = create_app(Settings(_env_file=None))
    app.dependency_overrides[deps.get_session] = lambda: db_session
    app.dependency_overrides[deps.get_now] = lambda: NOW
    return app


def test_health_on_an_empty_database(app):
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["forecast"] is None and body["model"] is None


def test_health_reads_prices_forecast_and_model(app, db_session):
    repository.upsert_prices(db_session, [(ts, 100.0) for ts in local_day_hours(TOMORROW)])
    repository.save_model_artifact(
        db_session,
        repository.ArtifactToSave(
            version="20261004-030000",
            trained_at=NOW - timedelta(days=2),
            train_start=NOW - timedelta(days=732),
            train_end=NOW - timedelta(days=3),
            training_rows=17_520,
            features=["hour"],
            params={},
            metrics={},
            library_versions={},
            format_version=1,
            data=b"x" * 1000,
        ),
    )
    repository.save_forecast(
        db_session,
        repository.ForecastToSave(
            target_day=TOMORROW + timedelta(days=1),
            generated_at=NOW - timedelta(minutes=5),
            model="lightgbm",
            model_version="20261004-030000",
            hours=[(ts, 90.0) for ts in local_day_hours(TOMORROW + timedelta(days=1))],
        ),
    )

    body = TestClient(app).get("/health").json()

    assert body["status"] == "ok", body["warnings"]
    assert body["checked_at"] == "2026-10-06T20:30:00+02:00"
    assert body["prices"] == {"last_hour": "2026-10-07T23:00:00+02:00", "last_day": "2026-10-07", "has_tomorrow": True}
    assert body["forecast"]["target_day"] == "2026-10-08"
    assert body["forecast"]["model_version"] == "20261004-030000"
    assert body["model"]["version"] == "20261004-030000"
    assert body["model"]["age_days"] == 2


def test_latest_run_wins(db_session):
    for day, minutes in [(TOMORROW, 60), (TODAY, 5)]:
        repository.save_forecast(
            db_session,
            repository.ForecastToSave(
                target_day=day,
                generated_at=NOW - timedelta(minutes=minutes),
                model="precio_ayer",
                hours=[(ts, 90.0) for ts in local_day_hours(day)],
            ),
        )
    assert repository.latest_model_run(db_session).target_day == TODAY  # la generada más tarde


def test_unreachable_database_is_a_503():
    engine = make_engine("postgresql+psycopg://luz:luz@127.0.0.1:1/nada?connect_timeout=1")

    def unreachable():
        with session_scope(engine) as session:
            yield session

    app = create_app(Settings(_env_file=None))
    app.dependency_overrides[deps.get_session] = unreachable
    response = TestClient(app).get("/health")

    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "service_unavailable"
    assert error["message"] == "Base de datos no disponible"
    assert error["request_id"] == response.headers[REQUEST_ID_HEADER]
    assert response.headers["retry-after"] == "30"
    assert "luz:luz" not in response.text
