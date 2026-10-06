from datetime import date

import pytest
from fastapi import HTTPException, Query
from fastapi.testclient import TestClient

from src.api.errors import error_responses
from src.api.main import create_app
from src.api.middleware import REQUEST_ID_HEADER
from src.utils.config import Settings


@pytest.fixture
def app():
    app = create_app(Settings(_env_file=None))

    @app.get("/test/day", responses=error_responses(404, 422))
    def day(day: date, hours: int = Query(default=1, ge=1, le=24)) -> dict[str, str]:
        if day.year < 2021:
            raise HTTPException(404, f"No hay precios para {day}")
        return {"day": day.isoformat()}

    @app.get("/test/limited")
    def limited() -> None:
        raise HTTPException(429, headers={"Retry-After": "60"})

    @app.get("/test/boom")
    def boom() -> None:
        raise RuntimeError("contraseña=secreta")

    return app


@pytest.fixture
def client(app):
    return TestClient(app, raise_server_exceptions=False)


def assert_error(response, status, code):
    assert response.status_code == status
    assert response.headers["content-type"] == "application/json"
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "request_id", "details"}
    assert body["error"]["code"] == code
    assert body["error"]["request_id"] == response.headers[REQUEST_ID_HEADER]
    return body["error"]


# --- 404 y 405 ---


def test_unknown_route_is_a_404_in_spanish(client):
    error = assert_error(client.get("/no-existe"), 404, "not_found")
    assert error["message"] == "No encontrado"
    assert error["details"] == []


def test_route_message_is_kept(client):
    error = assert_error(client.get("/test/day", params={"day": "2020-01-01"}), 404, "not_found")
    assert error["message"] == "No hay precios para 2020-01-01"


def test_wrong_method_is_a_405(client):
    response = client.post("/")
    error = assert_error(response, 405, "method_not_allowed")
    assert error["message"] == "Método no permitido"
    assert response.headers["allow"] == "GET"  # las cabeceras de la excepción se conservan


def test_other_http_errors_keep_their_headers(client):
    response = client.get("/test/limited")
    assert_error(response, 429, "too_many_requests")
    assert response.headers["retry-after"] == "60"


# --- 422 ---


def test_invalid_parameters_list_every_field(client):
    response = client.get("/test/day", params={"day": "mañana", "hours": "30"})

    error = assert_error(response, 422, "validation_error")
    assert error["message"] == "Parámetros no válidos"
    assert {d["field"] for d in error["details"]} == {"query.day", "query.hours"}
    assert all(d["message"] and d["type"] for d in error["details"])


def test_missing_parameter(client):
    error = assert_error(client.get("/test/day"), 422, "validation_error")
    assert error["details"] == [{"field": "query.day", "message": "Field required", "type": "missing"}]


def test_valid_request_is_not_affected(client):
    assert client.get("/test/day", params={"day": "2026-10-07"}).json() == {"day": "2026-10-07"}


# --- 500 ---


def test_internal_errors_do_not_leak_details(client):
    response = client.get("/test/boom")

    error = assert_error(response, 500, "internal_error")
    assert error["message"] == "Error interno del servidor"
    assert "secreta" not in response.text


def test_a_valid_incoming_request_id_appears_in_the_error(client):
    response = client.get("/test/boom", headers={REQUEST_ID_HEADER: "web-42"})
    assert response.json()["error"]["request_id"] == "web-42"


# --- Documentación ---


def test_openapi_documents_the_error_format(app):
    schema = TestClient(app).get("/openapi.json").json()

    day = schema["paths"]["/test/day"]["get"]["responses"]
    for status in ("404", "422", "500"):
        assert day[status]["content"]["application/json"]["schema"] == {"$ref": "#/components/schemas/ErrorResponse"}
    assert "HTTPValidationError" not in schema["components"]["schemas"]
    assert schema["paths"]["/"]["get"]["responses"]["500"]["description"] == "Error interno del servidor"
