from datetime import date, timedelta

import pytest

from src.api.deps import DEFAULT_HISTORY_DAYS, MAX_HISTORY_DAYS
from src.db import repository
from src.utils.calendar import local_day_hours
from tests.api_helpers import NOW, PROFILE, TODAY, TOMORROW, error_fields, make_client, save_prices, save_profile


@pytest.fixture
def client(db_session):
    return make_client(db_session)


# --- /v1/best-hours ---


def test_best_window_and_cheapest_hours(client, db_session):
    save_profile(db_session, TODAY)

    body = client.get("/v1/best-hours", params={"hours": 3}).json()

    assert body["date"] == "2026-10-06"
    assert body["window"] == {
        "start": "2026-10-06T03:00:00+02:00",
        "end": "2026-10-06T06:00:00+02:00",
        "avg_price": 20.0,
    }
    assert [h["datetime"][11:16] for h in body["cheapest"]] == ["15:00", "04:00", "03:00"]
    assert body["cheapest"][0] == {"datetime": "2026-10-06T15:00:00+02:00", "price": 5.0, "period": "llano"}
    assert body["day_avg_price"] == round(sum(PROFILE) / 24, 2)
    assert body["saving_pct"] == round((sum(PROFILE) / 24 - 20) / (sum(PROFILE) / 24) * 100, 1)


def test_defaults_to_tomorrow_once_published(client, db_session):
    save_profile(db_session, TODAY)
    assert client.get("/v1/best-hours").json()["date"] == "2026-10-06"

    save_profile(db_session, TOMORROW)
    assert client.get("/v1/best-hours").json()["date"] == "2026-10-07"


def test_incomplete_tomorrow_is_not_the_default(client, db_session):
    save_profile(db_session, TODAY)
    repository.upsert_prices(db_session, [(local_day_hours(TOMORROW)[0], 1.0)])

    assert client.get("/v1/best-hours").json()["date"] == "2026-10-06"


def test_time_range(client, db_session):
    save_profile(db_session, TODAY)

    body = client.get("/v1/best-hours", params={"hours": 2, "from_hour": 8, "to_hour": 22}).json()

    assert body["window"]["start"] == "2026-10-06T14:00:00+02:00"  # 14-16 o 15-17: gana la más temprana
    assert all("08:00" <= h["datetime"][11:16] < "22:00" for h in body["cheapest"])
    assert body["day_avg_price"] == round(sum(PROFILE) / 24, 2)  # la media es la de todo el día


def test_range_until_midnight(client, db_session):
    save_profile(db_session, TODAY, [100.0] * 22 + [1.0, 2.0])

    body = client.get("/v1/best-hours", params={"hours": 2, "from_hour": 20}).json()

    assert body["window"]["end"] == "2026-10-07T00:00:00+02:00"


def test_day_with_25_hours(db_session):
    day = date(2026, 10, 25)
    save_profile(db_session, day, [100.0] * 2 + [1.0, 1.0] + [100.0] * 21)  # las dos 2:00 son baratas
    client = make_client(db_session, now=NOW + timedelta(days=20))

    body = client.get("/v1/best-hours", params={"hours": 2, "date": "2026-10-25"}).json()

    # las 2:00 de verano y las 2:00 de invierno: dos horas reales que terminan a las 3:00 de invierno
    assert body["window"] == {
        "start": "2026-10-25T02:00:00+02:00",
        "end": "2026-10-25T03:00:00+01:00",
        "avg_price": 1.0,
    }


@pytest.mark.parametrize(
    ("params", "field"),
    [
        ({"hours": 0}, "query.hours"),
        ({"hours": 25}, "query.hours"),
        ({"from_hour": 24}, "query.from_hour"),
        ({"to_hour": 0}, "query.to_hour"),
        ({"date": "2026-10-08"}, "query.date"),
    ],
)
def test_invalid_parameters(client, params, field):
    assert field in error_fields(client.get("/v1/best-hours", params=params))


def test_inconsistent_range(client):
    assert error_fields(client.get("/v1/best-hours", params={"from_hour": 10, "to_hour": 10})) == {
        "query.to_hour": "to_hour debe ser posterior a from_hour"
    }
    assert error_fields(client.get("/v1/best-hours", params={"hours": 4, "from_hour": 20, "to_hour": 23})) == {
        "query.hours": "No caben 4 horas entre las 20:00 y las 23:00"
    }


def test_no_prices_or_no_room(client, db_session):
    response = client.get("/v1/best-hours", params={"date": "2026-10-07"})
    assert response.status_code == 404
    assert response.json()["error"]["message"].startswith("REE aún no ha publicado")

    save_prices(db_session, TODAY, skip_last=4)  # faltan las 20:00-23:00
    response = client.get("/v1/best-hours", params={"hours": 2, "from_hour": 20})
    assert response.status_code == 404
    assert response.json()["error"]["message"] == "No hay 2 horas seguidas con precio publicado en esa franja"


# --- /v1/history ---


def test_history_defaults_to_the_last_30_days(client, db_session):
    save_prices(db_session, TODAY - timedelta(days=1), TODAY)

    body = client.get("/v1/history").json()

    assert (body["start"], body["end"]) == (
        (TODAY - timedelta(days=DEFAULT_HISTORY_DAYS - 1)).isoformat(),
        "2026-10-06",
    )
    assert [d["date"] for d in body["days"]] == ["2026-10-05", "2026-10-06"]
    assert len(body["missing_days"]) == DEFAULT_HISTORY_DAYS - 2


def test_daily_summary(client, db_session):
    save_profile(db_session, TODAY)

    [day] = client.get("/v1/history", params={"start": "2026-10-06", "end": "2026-10-06"}).json()["days"]

    assert day == {
        "date": "2026-10-06",
        "avg_price": round(sum(PROFILE) / 24, 2),
        "min_price": 5.0,
        "min_hour": "2026-10-06T15:00:00+02:00",
        "max_price": 100.0,
        "max_hour": "2026-10-06T00:00:00+02:00",  # con empate, la más temprana
        "complete": True,
        "forecast": None,
    }


def test_history_includes_the_forecast_error(client, db_session):
    save_prices(db_session, TODAY - timedelta(days=1), TODAY)
    repository.upsert_daily_errors(db_session, [(TODAY, "lightgbm", 12.345, 15.0, -1.0, 24)])

    days = client.get("/v1/history", params={"start": "2026-10-05", "end": "2026-10-06"}).json()["days"]

    assert days[0]["forecast"] is None
    assert days[1]["forecast"] == {"model": "lightgbm", "mae": 12.35}


def test_incomplete_day(client, db_session):
    save_prices(db_session, TODAY, skip_last=3)

    body = client.get("/v1/history", params={"start": "2026-10-06", "end": "2026-10-06"}).json()

    assert body["days"][0]["complete"] is False
    assert body["missing_days"] == ["2026-10-06"]


def test_history_range_limits(client, db_session):
    save_prices(db_session, TODAY)
    start = TODAY - timedelta(days=MAX_HISTORY_DAYS - 1)
    assert client.get("/v1/history", params={"start": start.isoformat(), "end": "2026-10-06"}).status_code == 200

    too_long = {"start": (start - timedelta(days=1)).isoformat(), "end": "2026-10-06"}
    assert error_fields(client.get("/v1/history", params=too_long)) == {
        "query.end": f"El rango no puede superar {MAX_HISTORY_DAYS} días"
    }
    assert "query.end" in error_fields(client.get("/v1/history", params={"start": "2026-10-01"}))


def test_history_without_data(client):
    response = client.get("/v1/history", params={"start": "2025-01-01", "end": "2025-01-31"})
    assert response.status_code == 404
