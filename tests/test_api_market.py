from datetime import timedelta

import pytest

from src.api.deps import DEFAULT_HISTORY_DAYS
from src.db import repository
from tests.api_helpers import TODAY, error_fields, make_client

YESTERDAY = TODAY - timedelta(days=1)


@pytest.fixture
def client(db_session):
    repository.upsert_generation(
        db_session,
        [
            (YESTERDAY, "Eólica", 300_000.4),
            (YESTERDAY, "Nuclear", 100_000.0),
            (YESTERDAY, "Ciclo combinado", 100_000.0),
            (TODAY, "Eólica", 100_000.0),
            (TODAY, "Nuclear", 100_000.0),
        ],
    )
    return make_client(db_session)


def test_market_defaults_to_the_last_30_days(client):
    body = client.get("/v1/market").json()

    assert (body["start"], body["end"]) == (
        (TODAY - timedelta(days=DEFAULT_HISTORY_DAYS - 1)).isoformat(),
        "2026-10-06",
    )
    assert body["unit"] == "MWh"
    assert [d["date"] for d in body["days"]] == ["2026-10-05", "2026-10-06"]
    assert len(body["missing_days"]) == DEFAULT_HISTORY_DAYS - 2


def test_daily_renewable_share_and_mix(client):
    yesterday, today = client.get("/v1/market", params={"start": "2026-10-05", "end": "2026-10-06"}).json()["days"]

    assert yesterday == {
        "date": "2026-10-05",
        "total_mwh": 500_000,
        "renewable_mwh": 300_000,
        "renewable_pct": 60.0,
        "provisional": False,
        "mix": {"Eólica": 300_000, "Ciclo combinado": 100_000, "Nuclear": 100_000},
    }
    assert today["renewable_pct"] == 50.0
    assert today["provisional"] is True  # REE actualiza el día en curso


def test_period_mix(client):
    body = client.get("/v1/market", params={"start": "2026-10-05", "end": "2026-10-06"}).json()

    assert body["renewable_pct"] == round(400_000 / 700_000 * 100, 1)
    assert body["technologies"][0] == {"technology": "Eólica", "mwh": 400_000, "pct": 57.14, "renewable": True}
    assert [t["technology"] for t in body["technologies"]] == ["Eólica", "Nuclear", "Ciclo combinado"]
    assert body["missing_days"] == []


def test_market_errors(client):
    response = client.get("/v1/market", params={"start": "2025-01-01", "end": "2025-01-31"})
    assert response.status_code == 404
    assert response.json()["error"]["message"] == "No hay datos de generación entre el 2025-01-01 y el 2025-01-31"

    assert "query.end" in error_fields(client.get("/v1/market", params={"start": "2026-10-06", "end": "2026-10-01"}))


def test_market_is_documented(client):
    operation = client.get("/openapi.json").json()["paths"]["/v1/market"]["get"]
    assert operation["tags"] == ["Mercado"]
    assert {"404", "422", "500"} <= set(operation["responses"])
