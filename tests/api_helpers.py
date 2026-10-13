"""Utilidades comunes de los tests de la API: cliente con la base de pruebas y hora fija, y datos de ejemplo."""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from src.api import deps
from src.api.main import create_app
from src.db import repository
from src.utils.calendar import local_day_hours
from src.utils.config import Settings

MADRID = ZoneInfo("Europe/Madrid")
TODAY = date(2026, 10, 6)  # martes
TOMORROW = TODAY + timedelta(days=1)
NOW = datetime(2026, 10, 6, 20, 30, tzinfo=MADRID).astimezone(UTC)  # después de que REE publique

# Día con la madrugada barata (3:00 a 5:00) y una hora suelta muy barata a las 15:00
PROFILE = [100.0] * 24
PROFILE[3:6] = [20.0, 10.0, 30.0]
PROFILE[15] = 5.0


def make_client(session, now=NOW, **kwargs):
    """Cliente de una app nueva que usa `session` y cree que son las `now`."""
    app = create_app(Settings(_env_file=None))
    app.dependency_overrides[deps.get_session] = lambda: session
    app.dependency_overrides[deps.get_now] = lambda: now
    return TestClient(app, **kwargs)


def save_prices(session, *days, price=100.0, skip_last=0):
    """Precios crecientes (price, price + 1, ...) en cada hora; `skip_last` deja sin publicar las últimas."""
    for day in days:
        hours = local_day_hours(day)
        repository.upsert_prices(session, [(ts, price + i) for i, ts in enumerate(hours[: len(hours) - skip_last])])


def save_profile(session, day, profile=PROFILE):
    repository.upsert_prices(session, list(zip(local_day_hours(day), profile, strict=True)))


def save_run(session, day, prediction=90.0, minutes_ago=5, model="lightgbm", interval=None, model_version=None):
    """Previsión con el mismo valor en cada hora; con `interval`, un intervalo de ± ese valor."""
    bounds = (prediction - interval, prediction + interval) if interval is not None else ()
    repository.save_forecast(
        session,
        repository.ForecastToSave(
            target_day=day,
            generated_at=NOW - timedelta(minutes=minutes_ago),
            model=model,
            model_version=model_version,
            hours=[repository.HourToSave(ts, prediction, *bounds) for ts in local_day_hours(day)],
        ),
    )


def error_fields(response):
    """Campos con error de una respuesta 422, con su mensaje."""
    assert response.status_code == 422, response.json()
    return {d["field"]: d["message"] for d in response.json()["error"]["details"]}


METRICS = {
    "period": {"start": "2026-07-09", "end": "2026-10-06", "days": 90},
    "models": {
        "lightgbm": {"mae": 21.93, "rmse": 29.61, "bias": -4.8, "n": 2160.0},
        "media_7_dias": {"mae": 32.45, "rmse": 44.23, "bias": -2.3, "n": 2160.0},
        "precio_ayer": {"mae": 33.54, "rmse": 52.7, "bias": -0.49, "n": 2160.0},
    },
    "interval": {"level": 0.8, "coverage": 0.795, "width": 54.83, "n": 2160},
}


def save_artifact(session, metrics=METRICS):
    """Modelo guardado ayer, con las métricas de un entrenamiento real."""
    repository.save_model_artifact(
        session,
        repository.ArtifactToSave(
            version="20261006-172844",
            trained_at=NOW - timedelta(days=1),
            train_start=NOW - timedelta(days=731),
            train_end=NOW - timedelta(days=1, hours=2),
            training_rows=17_520,
            features=["hour", "price_lag_1d"],
            params={"objective": "l1", "n_estimators": 500},
            metrics=metrics,
            library_versions={"lightgbm": "4.7.0"},
            format_version=1,
            data=b"x" * 10_000,
        ),
    )
