"""Atribución a REE en todas las respuestas de /v1 y aviso en la previsión."""

import pytest

from src.api.schemas.common import FORECAST_DISCLAIMER, REE_URL
from src.db import repository
from tests.api_helpers import TODAY, make_client, save_prices, save_run

PVPC = {"name": "Red Eléctrica (REE)", "url": REE_URL, "series": "PVPC 2.0TD"}
GENERATION = {"name": "Red Eléctrica (REE)", "url": REE_URL, "series": "Estructura de la generación"}


@pytest.fixture
def client(db_session):
    save_prices(db_session, TODAY)
    save_run(db_session, TODAY)
    repository.upsert_generation(db_session, [(TODAY, "Eólica", 100.0)])
    return make_client(db_session)


@pytest.mark.parametrize(
    ("path", "source"),
    [
        ("/v1/prices", PVPC),
        ("/v1/forecast", PVPC),
        ("/v1/best-hours", PVPC),
        ("/v1/history", PVPC),
        ("/v1/market", GENERATION),
    ],
)
def test_every_public_response_cites_ree(client, path, source):
    response = client.get(path)

    assert response.status_code == 200
    assert response.json()["source"] == source


def test_forecast_carries_the_disclaimer(client):
    body = client.get("/v1/forecast").json()

    assert body["disclaimer"] == FORECAST_DISCLAIMER
    assert "orientativa" in body["disclaimer"]


@pytest.mark.parametrize("path", ["/v1/prices", "/v1/best-hours", "/v1/history", "/v1/market"])
def test_published_data_has_no_disclaimer(client, path):
    assert "disclaimer" not in client.get(path).json()


def test_errors_do_not_carry_a_source(client):
    assert "source" not in client.get("/v1/prices", params={"date": "2026-10-07"}).json()


def test_documentation_shows_source_and_disclaimer(client):
    schema = client.get("/openapi.json").json()
    schemas = schema["components"]["schemas"]

    assert schemas["Forecast"]["properties"]["disclaimer"]["default"] == FORECAST_DISCLAIMER
    assert schemas["Market"]["properties"]["source"]["default"]["series"] == "Estructura de la generación"
    assert "`source`" in schema["info"]["description"]
