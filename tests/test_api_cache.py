from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from src.api.cache import next_refresh, seconds_until_refresh
from src.db import repository
from tests.test_api_prices import NOW, TODAY, make_client, save_prices, save_run


def utc(hour, minute=0, day=6):
    return datetime(2026, 10, day, hour, minute, tzinfo=UTC)


# --- Siguiente actualización ---


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (utc(8), utc(19, 50)),  # por la mañana: hasta la tarea de la tarde
        (utc(19, 49), utc(19, 50)),
        (utc(19, 50), utc(21, 50)),  # justo a la hora: ya cuenta la siguiente
        (utc(20, 30), utc(21, 50)),  # entre la tarea y su reintento
        (utc(21, 50), utc(19, 50, day=7)),
        (utc(23, 59), utc(19, 50, day=7)),
    ],
)
def test_next_refresh(now, expected):
    assert next_refresh(now) == expected


def test_next_refresh_accepts_any_time_zone():
    madrid = datetime(2026, 10, 6, 20, 30, tzinfo=ZoneInfo("Europe/Madrid"))  # 18:30 UTC
    assert next_refresh(madrid) == utc(19, 50)
    assert seconds_until_refresh(madrid) == 80 * 60


def test_refresh_times_do_not_move_with_daylight_saving():
    """El cron de GitHub va en UTC: en invierno la tarea corre a las 20:30 de Madrid, no a las 21:30."""
    winter = datetime(2026, 12, 1, 20, 0, tzinfo=ZoneInfo("Europe/Madrid"))  # 19:00 UTC
    assert next_refresh(winter) == datetime(2026, 12, 1, 19, 50, tzinfo=UTC)


# --- Cabeceras ---


@pytest.fixture
def client(db_session):
    save_prices(db_session, TODAY)
    save_run(db_session, TODAY)
    repository.upsert_generation(db_session, [(TODAY, "Eólica", 100.0)])
    return make_client(db_session)  # NOW: 18:30 UTC


@pytest.mark.parametrize("path", ["/v1/prices", "/v1/forecast", "/v1/best-hours", "/v1/history", "/v1/market"])
def test_public_responses_are_cached_until_the_next_refresh(client, path):
    response = client.get(path)

    assert response.status_code == 200
    seconds = seconds_until_refresh(NOW)
    assert seconds == 80 * 60
    assert response.headers["cache-control"] == f"public, max-age={seconds}, s-maxage={seconds}"


def test_cache_header_survives_compression(client):
    response = client.get("/v1/prices", headers={"Accept-Encoding": "gzip"})  # 24 horas: más de 1000 bytes

    assert response.headers["content-encoding"] == "gzip"
    assert response.headers["cache-control"].startswith("public, max-age=")


@pytest.mark.parametrize(
    "params",
    [
        {"date": "2026-10-07"},  # 404: REE aún no ha publicado
        {"date": "06/10/2026"},  # 422
    ],
)
def test_errors_are_never_cached(client, params):
    response = client.get("/v1/prices", params=params)

    assert response.status_code in (404, 422)
    assert response.headers["cache-control"] == "no-store"


def test_internal_errors_are_never_cached(db_session):
    client = make_client(db_session)
    client.app.add_api_route("/v1/boom", lambda: 1 / 0)
    response = TestClient(client.app, raise_server_exceptions=False).get("/v1/boom")

    assert response.status_code == 500
    assert response.headers["cache-control"] == "no-store"


def test_health_is_never_cached(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
