from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from src.api import deps
from src.api.deps import MAX_RANGE_DAYS
from src.api.main import create_app
from src.db import repository
from src.utils.calendar import local_day_hours
from src.utils.config import Settings

MADRID = ZoneInfo("Europe/Madrid")
TODAY = date(2026, 10, 6)  # martes
TOMORROW = TODAY + timedelta(days=1)
NOW = datetime(2026, 10, 6, 20, 30, tzinfo=MADRID).astimezone(UTC)


def save_prices(session, *days, price=100.0, skip_last=0):
    for day in days:
        hours = local_day_hours(day)
        repository.upsert_prices(session, [(ts, price + i) for i, ts in enumerate(hours[: len(hours) - skip_last])])


def save_run(session, day, prediction=90.0, minutes_ago=5, model="lightgbm"):
    repository.save_forecast(
        session,
        repository.ForecastToSave(
            target_day=day,
            generated_at=NOW - timedelta(minutes=minutes_ago),
            model=model,
            hours=[(ts, prediction) for ts in local_day_hours(day)],
        ),
    )


def make_client(session, now=NOW):
    app = create_app(Settings(_env_file=None))
    app.dependency_overrides[deps.get_session] = lambda: session
    app.dependency_overrides[deps.get_now] = lambda: now
    return TestClient(app)


@pytest.fixture
def client(db_session):
    return make_client(db_session)


def error_fields(response):
    assert response.status_code == 422
    return {d["field"]: d["message"] for d in response.json()["error"]["details"]}


# --- /v1/prices ---


def test_prices_default_to_today(client, db_session):
    save_prices(db_session, TODAY - timedelta(days=1), TODAY)

    body = client.get("/v1/prices").json()

    assert (body["start"], body["end"], body["unit"]) == ("2026-10-06", "2026-10-06", "€/MWh")
    assert body["missing_days"] == []
    assert len(body["hours"]) == 24
    assert body["hours"][0] == {"datetime": "2026-10-06T00:00:00+02:00", "price": 100.0, "period": "valle"}
    assert body["hours"][10]["period"] == "punta"
    assert body["hours"][8]["period"] == "llano"


def test_prices_of_tomorrow_once_published(client, db_session):
    save_prices(db_session, TODAY, TOMORROW)

    body = client.get("/v1/prices", params={"date": "2026-10-07"}).json()

    assert body["hours"][0]["datetime"] == "2026-10-07T00:00:00+02:00"
    assert body["hours"][-1]["datetime"] == "2026-10-07T23:00:00+02:00"


def test_tomorrow_not_yet_published_is_a_404(client, db_session):
    save_prices(db_session, TODAY)

    response = client.get("/v1/prices", params={"date": "2026-10-07"})

    assert response.status_code == 404
    assert response.json()["error"]["message"].startswith("REE aún no ha publicado los precios del 2026-10-07")


def test_range_reports_missing_days(client, db_session):
    save_prices(db_session, TODAY - timedelta(days=2))
    save_prices(db_session, TODAY, skip_last=3)

    body = client.get("/v1/prices", params={"start": "2026-10-04", "end": "2026-10-07"}).json()

    assert len(body["hours"]) == 24 + 21
    assert body["missing_days"] == ["2026-10-05", "2026-10-06", "2026-10-07"]


def test_range_without_data_is_a_404(client):
    response = client.get("/v1/prices", params={"start": "2025-01-01", "end": "2025-01-31"})

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "No hay precios entre el 2025-01-01 y el 2025-01-31"


def test_day_with_25_hours(db_session):
    day = date(2026, 10, 25)  # domingo, cambio a horario de invierno
    save_prices(db_session, day)

    body = make_client(db_session, now=NOW + timedelta(days=20)).get("/v1/prices", params={"date": "2026-10-25"}).json()

    assert len(body["hours"]) == 25
    assert [h["datetime"] for h in body["hours"][2:4]] == ["2026-10-25T02:00:00+02:00", "2026-10-25T02:00:00+01:00"]
    assert {h["period"] for h in body["hours"]} == {"valle"}
    assert body["missing_days"] == []


@pytest.mark.parametrize(
    ("params", "field", "message"),
    [
        ({"date": "2026-10-06", "start": "2026-10-01"}, "date", "Usa date o start/end, no ambos"),
        ({"start": "2026-10-01"}, "end", "Hay que indicar start y end"),
        ({"end": "2026-10-01"}, "start", "Hay que indicar start y end"),
        ({"start": "2026-10-05", "end": "2026-10-01"}, "end", "end no puede ser anterior a start"),
        ({"start": "2026-09-01", "end": "2026-10-02"}, "end", f"El rango no puede superar {MAX_RANGE_DAYS} días"),
        ({"date": "2021-05-31"}, "date", "No hay datos antes del 2021-06-01"),
        ({"date": "2026-10-08"}, "date", "La fecha no puede ser posterior al 2026-10-07"),
        ({"start": "2026-10-01", "end": "2026-10-08"}, "end", "La fecha no puede ser posterior al 2026-10-07"),
    ],
)
def test_invalid_ranges(client, params, field, message):
    assert error_fields(client.get("/v1/prices", params=params)) == {f"query.{field}": message}


def test_longest_range_is_allowed(client, db_session):
    save_prices(db_session, TODAY)
    start = TODAY - timedelta(days=MAX_RANGE_DAYS - 1)
    assert client.get("/v1/prices", params={"start": start.isoformat(), "end": "2026-10-06"}).status_code == 200


def test_malformed_date(client):
    assert "query.date" in error_fields(client.get("/v1/prices", params={"date": "06/10/2026"}))


# --- /v1/forecast ---


def test_forecast_defaults_to_the_latest(client, db_session):
    save_run(db_session, TODAY, minutes_ago=60 * 24)
    save_run(db_session, TOMORROW)

    body = client.get("/v1/forecast").json()

    assert body["date"] == "2026-10-07"
    assert body["model"] == "lightgbm"
    assert body["mae"] is None
    assert len(body["hours"]) == 24
    assert body["hours"][0] == {
        "datetime": "2026-10-07T00:00:00+02:00",
        "price": 90.0,
        "period": "valle",
        "actual": None,
    }


def test_forecast_of_a_published_day_includes_actual_prices_and_error(client, db_session):
    save_prices(db_session, TODAY)  # 100, 101, ..., 123
    save_run(db_session, TODAY, prediction=110.0)

    body = client.get("/v1/forecast", params={"date": "2026-10-06"}).json()

    assert [h["actual"] for h in body["hours"][:2]] == [100.0, 101.0]
    assert body["mae"] == round(sum(abs(110 - (100 + i)) for i in range(24)) / 24, 2)


def test_forecast_is_rounded_like_ree_prices(client, db_session):
    save_prices(db_session, TODAY)
    save_run(db_session, TODAY, prediction=170.8665909175672)

    body = client.get("/v1/forecast", params={"date": "2026-10-06"}).json()

    assert body["hours"][0]["price"] == 170.87
    assert body["mae"] == round(body["mae"], 2)


def test_partial_actual_prices_give_no_error(client, db_session):
    save_prices(db_session, TODAY, skip_last=2)
    save_run(db_session, TODAY)

    body = client.get("/v1/forecast", params={"date": "2026-10-06"}).json()

    assert body["hours"][-1]["actual"] is None
    assert body["mae"] is None


def test_the_latest_run_of_the_day_is_used(client, db_session):
    save_run(db_session, TOMORROW, prediction=80.0, minutes_ago=90, model="precio_ayer")
    save_run(db_session, TOMORROW, prediction=95.0)

    body = client.get("/v1/forecast", params={"date": "2026-10-07"}).json()

    assert body["model"] == "lightgbm"
    assert body["hours"][0]["price"] == 95.0


def test_forecast_not_found(client, db_session):
    assert client.get("/v1/forecast").json()["error"]["message"] == "Todavía no hay ninguna previsión"

    save_run(db_session, TODAY)
    response = client.get("/v1/forecast", params={"date": "2026-10-07"})
    assert response.status_code == 404
    assert response.json()["error"]["message"] == "No hay previsión para el 2026-10-07"


def test_forecast_up_to_the_day_after_tomorrow(client):
    assert client.get("/v1/forecast", params={"date": "2026-10-08"}).status_code == 404  # válido, sin datos
    assert error_fields(client.get("/v1/forecast", params={"date": "2026-10-09"})) == {
        "query.date": "La fecha no puede ser posterior al 2026-10-08"
    }


# --- Documentación ---


def test_openapi_documents_parameters_and_errors(client):
    schema = client.get("/openapi.json").json()

    prices = schema["paths"]["/v1/prices"]["get"]
    assert [p["name"] for p in prices["parameters"]] == ["date", "start", "end"]
    assert {"200", "404", "422", "500"} <= set(prices["responses"])
    assert prices["tags"] == ["Precios"]
    assert schema["paths"]["/v1/forecast"]["get"]["tags"] == ["Previsión"]
    assert "HTTPValidationError" not in schema["components"]["schemas"]
