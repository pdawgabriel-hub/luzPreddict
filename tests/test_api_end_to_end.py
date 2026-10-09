"""De extremo a extremo: lo que guarda el pipeline es lo que sirve la API.

Se entrena el modelo y se ejecuta la tarea diaria (con su reintento) sobre la
base de pruebas, y después se consulta la API con la hora de cada momento.
"""

from datetime import UTC, datetime, time, timedelta

import pytest

from src import pipeline
from src.db import repository
from tests.api_helpers import MADRID, make_client
from tests.fakes import SEEDED_LAST_DAY as DAY1
from tests.fakes import FakeReeClient

DAY2, DAY3 = DAY1 + timedelta(days=1), DAY1 + timedelta(days=2)
EVENING = datetime.combine(DAY1, time(22, 0), tzinfo=MADRID).astimezone(UTC)  # después del reintento


@pytest.fixture
def pending(seeded, sessions, fast_model):
    """19:30 UTC del día 1: modelo entrenado y REE sin publicar aún el día 2."""
    pipeline.train(seeded, metrics_days=3)
    result = pipeline.daily(client=FakeReeClient(published_until=DAY1), today=DAY1, session_factory=sessions)
    assert result.status == "pendiente"
    return result


@pytest.fixture
def published(pending, seeded, sessions):
    """Reintento de las 21:30 UTC: REE ya ha publicado el día 2."""
    result = pipeline.daily(
        client=FakeReeClient(published_until=DAY2, price=150.0), today=DAY1, session_factory=sessions
    )
    assert result.status == "completo"
    return result


def test_before_ree_publishes(pending, seeded):
    client = make_client(seeded, now=EVENING)

    health = client.get("/health").json()
    assert health["status"] == "ok", health["warnings"]
    assert health["prices"]["last_day"] == DAY1.isoformat()
    assert not health["prices"]["has_tomorrow"]
    assert health["forecast"]["target_day"] == DAY2.isoformat()
    assert health["forecast"]["model"] == "lightgbm"
    assert health["model"]["version"] == pending.forecast.model_version

    forecast = client.get("/v1/forecast").json()
    assert forecast["date"] == DAY2.isoformat()
    assert [h["price"] for h in forecast["hours"]] == [round(p, 2) for p in pending.forecast.prices]
    assert all(h["actual"] is None for h in forecast["hours"]) and forecast["mae"] is None

    response = client.get("/v1/prices", params={"date": DAY2.isoformat()})
    assert response.status_code == 404
    assert response.headers["cache-control"] == "no-store"  # no se queda en caché tras publicarse


def test_after_ree_publishes(published, pending, seeded):
    client = make_client(seeded, now=EVENING)
    [error] = repository.get_daily_errors(seeded, DAY2, DAY2)

    # Los precios publicados y la mejor hora ya son de mañana
    prices = client.get("/v1/prices", params={"date": DAY2.isoformat()}).json()
    assert len(prices["hours"]) == 24 and {h["price"] for h in prices["hours"]} == {150.0}
    assert client.get("/v1/best-hours").json()["date"] == DAY2.isoformat()

    # La previsión del día 2 se compara con el precio real, con el mismo error en toda la API
    forecast = client.get("/v1/forecast", params={"date": DAY2.isoformat()}).json()
    assert {h["actual"] for h in forecast["hours"]} == {150.0}
    assert forecast["mae"] == pytest.approx(error.mae, abs=0.01)

    [day] = client.get("/v1/history", params={"start": DAY2.isoformat(), "end": DAY2.isoformat()}).json()["days"]
    assert day["forecast"] == {"model": "lightgbm", "mae": round(error.mae, 2)}

    report = client.get("/api/model", params={"days": 7}).json()
    assert report["live"]["days"] == [
        {
            "date": DAY2.isoformat(),
            "model": "lightgbm",
            "mae": round(error.mae, 2),
            "rmse": round(error.rmse, 2),
            "bias": round(error.bias, 2),
        }
    ]
    assert report["backtest"]["days"] == 3
    assert {m["model"] for m in report["backtest"]["models"]} == {"lightgbm", "precio_ayer", "media_7_dias"}

    # La previsión más reciente ya es la del día 3
    health = client.get("/health").json()
    assert health["prices"]["has_tomorrow"]
    assert health["forecast"]["target_day"] == DAY3.isoformat() == client.get("/v1/forecast").json()["date"]


def test_generation_downloaded_by_the_pipeline_is_served(published, seeded):
    client = make_client(seeded, now=EVENING)
    market = client.get("/v1/market", params={"start": DAY1.isoformat(), "end": DAY1.isoformat()}).json()

    [day] = market["days"]
    assert day["date"] == DAY1.isoformat()
    assert day["total_mwh"] > 0
    assert sum(day["mix"].values()) == pytest.approx(day["total_mwh"], abs=len(day["mix"]))
