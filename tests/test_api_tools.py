from datetime import timedelta

import pytest

from src.api.schemas.tools import MAX_TASKS
from src.db import repository
from src.services.planner import BASE_LOAD_KW, CONTRACTED_POWERS_KW
from src.services.simulator import APPLIANCES
from src.services.tariffs import PROFILES
from src.utils.calendar import local_day_hours
from tests.test_api_best_hours_history import PROFILE, save_profile
from tests.test_api_prices import TODAY, TOMORROW, make_client

LAVADORA = APPLIANCES["lavadora"]  # 0,5 kW durante 2 h


@pytest.fixture
def client(db_session):
    save_profile(db_session, TODAY)  # 100 €/MWh salvo 3:00-5:00 (20, 10, 30) y 15:00 (5)
    return make_client(db_session)


def error(response, status=422):
    assert response.status_code == status, response.json()
    return response.json()["error"]


def details(response):
    return {d["field"]: d["message"] for d in error(response)["details"]}


# --- Catálogo ---


def test_catalog(client):
    response = client.get("/api/tools/catalog")
    body = response.json()

    assert [a["id"] for a in body["appliances"]] == list(APPLIANCES)
    assert body["appliances"][0] == {"id": "lavadora", "name": "Lavadora", "power_kw": 0.5, "hours": 2, "kwh": 1.0}
    assert [p["id"] for p in body["profiles"]] == list(PROFILES)
    assert body["contracted_powers_kw"] == list(CONTRACTED_POWERS_KW)
    assert body["base_load_kw"] == BASE_LOAD_KW
    assert response.headers["cache-control"] == "public, max-age=3600"


# --- Simulador ---


def test_simulate_one_appliance(client):
    body = client.post("/api/tools/simulate", json={"appliance": "lavadora", "start_hour": 20}).json()

    assert body["date"] == "2026-10-06"
    [sim] = body["simulations"]
    assert sim["start"] == "2026-10-06T20:00:00+02:00"
    assert sim["end"] == "2026-10-06T22:00:00+02:00"
    assert sim["cost"] == pytest.approx(1.0 * 0.100)
    assert sim["best"] == {"start": "2026-10-06T03:00:00+02:00", "end": "2026-10-06T05:00:00+02:00", "avg_price": 0.015}
    assert sim["best_cost"] == pytest.approx(1.0 * 0.015)
    assert sim["saving_per_use"] == pytest.approx(0.085)
    assert sim["yearly_saving"] == pytest.approx(0.085 * 52)
    assert body["total_yearly_saving"] == sim["yearly_saving"]
    assert body["source"]["series"] == "PVPC 2.0TD"


def test_simulate_all_appliances(client):
    body = client.post("/api/tools/simulate", json={"start_hour": 20, "uses_per_week": 3}).json()

    assert [s["appliance"]["id"] for s in body["simulations"]] == list(APPLIANCES)
    coche = body["simulations"][-1]
    assert coche["start"] == "2026-10-06T18:00:00+02:00"  # 6 horas desde las 20:00 no caben: se adelanta
    assert body["total_yearly_saving"] == pytest.approx(sum(s["yearly_saving"] for s in body["simulations"]), abs=1e-3)


def test_simulate_custom_appliance_within_a_range(client):
    custom = {"name": "Bomba de calor", "power_kw": 2, "hours": 2}
    body = client.post(
        "/api/tools/simulate", json={"appliance": custom, "start_hour": 20, "from_hour": 8, "to_hour": 20}
    ).json()

    [sim] = body["simulations"]
    assert sim["appliance"] == {
        "id": "personalizado",
        "name": "Bomba de calor",
        "power_kw": 2.0,
        "hours": 2,
        "kwh": 4.0,
    }
    assert sim["best"]["start"] == "2026-10-06T14:00:00+02:00"  # 14-16 incluye la hora de 5 €/MWh


def test_simulate_range_too_short(client):
    body = client.post("/api/tools/simulate", json={"appliance": "coche", "from_hour": 10, "to_hour": 12}).json()

    [sim] = body["simulations"]
    assert sim["best"] is None and sim["yearly_saving"] is None
    assert body["total_yearly_saving"] == 0


def test_simulate_validation(client):
    assert details(client.post("/api/tools/simulate", json={"appliance": "nevera"})) == {
        "body.appliance": "Aparato desconocido: nevera. Opciones: lavadora, lavavajillas, secadora, horno, coche"
    }
    assert details(client.post("/api/tools/simulate", json={"from_hour": 20, "to_hour": 8})) == {
        "body": "to_hour debe ser posterior a from_hour"
    }
    assert "body.appliance.CustomAppliance.power_kw" in details(
        client.post("/api/tools/simulate", json={"appliance": {"name": "x", "power_kw": 0, "hours": 1}})
    )
    assert details(client.post("/api/tools/simulate", json={"date": "2026-10-08"})) == {
        "body.date": "La fecha no puede ser posterior al 2026-10-07"
    }


def test_simulate_unpublished_day(client):
    message = error(client.post("/api/tools/simulate", json={"date": TOMORROW.isoformat()}), 404)["message"]
    assert message.startswith("REE aún no ha publicado")


# --- Planificador ---


def test_plan_moves_flexible_tasks_and_keeps_fixed_ones(client):
    tasks = [
        {"id": "lavadora", "appliance": "lavadora", "habitual_hour": 20},
        {"id": "horno", "appliance": "horno", "habitual_hour": 21, "fixed": True},
    ]
    body = client.post("/api/tools/plan", json={"power_kw": 4.6, "tasks": tasks}).json()

    lavadora, horno = body["tasks"]
    assert lavadora["placed"] and lavadora["start"] == "2026-10-06T03:00:00+02:00"
    assert lavadora["saving"] == pytest.approx(0.085)
    assert horno["start"] == horno["habitual_start"] == "2026-10-06T21:00:00+02:00"
    assert horno["saving"] == 0
    assert body["saving"] == pytest.approx(0.085)
    assert body["unplaced"] == [] and body["habitual_overloads"] == []

    hours = {h["datetime"][11:16]: h for h in body["hours"]}
    assert len(hours) == 24
    assert hours["03:00"] == {"datetime": "2026-10-06T03:00:00+02:00", "price": 0.02, "kw": 0.9, "habitual_kw": 0.4}
    assert hours["21:00"]["kw"] == pytest.approx(BASE_LOAD_KW + 1.5)  # solo el horno: la lavadora se ha movido
    assert hours["21:00"]["habitual_kw"] == pytest.approx(BASE_LOAD_KW + 1.5 + 0.5)  # horno + lavadora a las 20 h


def test_plan_reports_what_does_not_fit(client):
    tasks = [{"id": "coche", "appliance": "coche", "habitual_hour": 0}]
    body = client.post("/api/tools/plan", json={"power_kw": 3.45, "tasks": tasks}).json()

    assert body["unplaced"] == ["coche"]
    assert body["tasks"][0]["placed"] is False
    assert body["tasks"][0]["start"] is None and body["tasks"][0]["saving"] is None
    assert len(body["habitual_overloads"]) == 6  # 3,7 kW + consumo base superan los 3,45 kW


def test_plan_validation(client):
    task = {"id": "a", "appliance": "lavadora", "habitual_hour": 20}
    assert (
        error(client.post("/api/tools/plan", json={"tasks": [task, task]}))["message"] == "Hay tareas con el mismo id"
    )
    assert error(client.post("/api/tools/plan", json={"power_kw": 0.3, "tasks": [task]}))["message"].startswith(
        "La potencia contratada (0.3 kW) debe superar el consumo base"
    )
    assert "body.tasks" in details(client.post("/api/tools/plan", json={"tasks": []}))
    too_many = [{**task, "id": str(i)} for i in range(MAX_TASKS + 1)]
    assert "body.tasks" in details(client.post("/api/tools/plan", json={"tasks": too_many}))
    assert "body.tasks.0.habitual_hour" in details(
        client.post("/api/tools/plan", json={"tasks": [{**task, "habitual_hour": 24}]})
    )


# --- Factura ---


def test_bill_against_a_fixed_price(client):
    body = client.post(
        "/api/tools/bill",
        json={"start": "2026-10-06", "end": "2026-10-06", "total_kwh": 24, "profile": "constante", "fixed_price": 0.08},
    ).json()

    pvpc = sum(PROFILE) / 1000  # 1 kWh cada hora
    assert body["pvpc_cost"] == pytest.approx(pvpc, abs=1e-4)
    assert body["fixed_cost"] == pytest.approx(24 * 0.08)
    assert body["fixed_saving"] == pytest.approx(24 * 0.08 - pvpc, abs=1e-4)
    assert body["effective_price"] == pytest.approx(pvpc / 24, abs=1e-4)
    assert body["fixed_saving"] < 0  # 1,92 € con el fijo frente a 2,065 € con PVPC
    assert body["days_fixed_was_cheaper"] == 1
    assert {p["period"]: p["kwh"] for p in body["periods"]} == {"punta": 8, "llano": 8, "valle": 8}
    assert body["days"] == [{"date": "2026-10-06", "kwh": 24, "pvpc_cost": round(pvpc, 4), "fixed_cost": 1.92}]
    assert body["missing_days"] == []
    assert body["note"].startswith("Solo el término de energía")


def test_bill_defaults_to_the_last_30_days(client):
    body = client.post("/api/tools/bill", json={"total_kwh": 100}).json()

    assert (body["start"], body["end"]) == ((TODAY - timedelta(days=29)).isoformat(), TODAY.isoformat())
    assert len(body["missing_days"]) == 29  # solo hay precios de hoy: el consumo va a ese día
    assert body["fixed_cost"] is None and body["fixed_saving"] is None


def test_bill_shifting_consumption_lowers_the_cost(client):
    body = client.post(
        "/api/tools/bill", json={"start": "2026-10-06", "end": "2026-10-06", "total_kwh": 24, "shift_fraction": 0.5}
    ).json()
    assert body["pvpc_shifted_cost"] < body["pvpc_cost"]
    assert body["break_even_price"] == pytest.approx(body["pvpc_shifted_cost"] / 24, abs=1e-4)


def test_bill_validation(client, db_session):
    assert details(client.post("/api/tools/bill", json={"total_kwh": 100, "profile": "raro"})) == {
        "body.profile": "Perfil desconocido: raro. Opciones: tipico, teletrabajo, coche_noche, constante"
    }
    assert "body.total_kwh" in details(client.post("/api/tools/bill", json={"total_kwh": 0}))
    assert "body.shift_fraction" in details(client.post("/api/tools/bill", json={"total_kwh": 1, "shift_fraction": 2}))
    assert details(
        client.post("/api/tools/bill", json={"total_kwh": 1, "start": "2026-10-06", "end": "2026-10-01"})
    ) == {"body.end": "end no puede ser anterior a start"}
    response = client.post("/api/tools/bill", json={"total_kwh": 1, "start": "2025-01-01", "end": "2025-01-31"})
    assert error(response, 404)["message"] == "No hay precios entre el 2025-01-01 y el 2025-01-31"


# --- Uso interno ---


def test_tools_are_not_open_to_other_origins(client):
    preflight = client.options(
        "/api/tools/simulate",
        headers={"Origin": "https://otra-web.example", "Access-Control-Request-Method": "POST"},
    )
    assert preflight.status_code == 400


def test_tools_are_documented_under_their_own_tag(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert paths["/api/tools/plan"]["post"]["tags"] == ["Herramientas"]
    assert {"404", "422"} <= set(paths["/api/tools/simulate"]["post"]["responses"])


def test_partial_day_with_a_gap(client, db_session):
    """Si falta una hora en medio, el simulador no puede calcular el coste a esa hora: 422 con el motivo."""
    repository.upsert_prices(db_session, [(ts, 50.0) for ts in local_day_hours(TOMORROW)[:10]])
    repository.upsert_prices(db_session, [(ts, 50.0) for ts in local_day_hours(TOMORROW)[12:]])
    response = client.post("/api/tools/simulate", json={"date": "2026-10-07", "appliance": "horno", "start_hour": 10})
    assert error(response)["message"].startswith("No hay precio para las 1 hora(s)")
