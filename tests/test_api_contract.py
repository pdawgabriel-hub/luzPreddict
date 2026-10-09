"""Reglas comunes a todas las rutas de la API.

Las rutas salen del esquema OpenAPI de la app: si se añade una ruta sin incluirla en ROUTES,
`test_every_route_is_covered` falla, y con ella entran en todas las comprobaciones.
"""

from datetime import timedelta

import pytest

from src.api import deps
from src.api.cache import seconds_until_refresh
from src.api.main import TAGS
from src.api.middleware import REQUEST_ID_HEADER
from src.db import repository
from src.db.session import make_engine, session_scope
from tests.api_helpers import NOW, TODAY, make_client, save_artifact, save_profile, save_run

FRONTEND = "http://localhost:5173"
UNTIL_REFRESH = f"public, max-age={seconds_until_refresh(NOW)}, s-maxage={seconds_until_refresh(NOW)}"
TASK = {"id": "lavadora", "appliance": "lavadora", "habitual_hour": 20}

# (método, ruta) -> (cuerpo JSON de una petición válida, Cache-Control esperado, usa la base de datos)
ROUTES = {
    ("GET", "/"): (None, None, False),
    ("GET", "/health"): (None, "no-store", True),
    ("GET", "/v1/prices"): (None, UNTIL_REFRESH, True),
    ("GET", "/v1/forecast"): (None, UNTIL_REFRESH, True),
    ("GET", "/v1/best-hours"): (None, UNTIL_REFRESH, True),
    ("GET", "/v1/history"): (None, UNTIL_REFRESH, True),
    ("GET", "/v1/market"): (None, UNTIL_REFRESH, True),
    ("GET", "/api/model"): (None, UNTIL_REFRESH, True),
    ("GET", "/api/tools/catalog"): (None, "public, max-age=3600", False),
    ("POST", "/api/tools/simulate"): ({}, None, True),
    ("POST", "/api/tools/plan"): ({"tasks": [TASK]}, None, True),
    ("POST", "/api/tools/bill"): ({"total_kwh": 100}, None, True),
}
DB_ROUTES = [route for route, (_, _, uses_db) in ROUTES.items() if uses_db]


def call(client, method, path, body=None, **kwargs):
    return client.request(method, path, json=body, **kwargs)


@pytest.fixture
def client(db_session):
    save_profile(db_session, TODAY)
    save_run(db_session, TODAY + timedelta(days=1))
    repository.upsert_generation(db_session, [(TODAY, "Eólica", 100.0), (TODAY, "Nuclear", 50.0)])
    save_artifact(db_session)
    repository.upsert_daily_errors(db_session, [(TODAY, "lightgbm", 12.0, 15.0, -1.0, 24)])
    return make_client(db_session)


@pytest.fixture
def unreachable_client():
    """App cuya base de datos no responde."""
    engine = make_engine("postgresql+psycopg://luz:luz@127.0.0.1:1/nada?connect_timeout=1")

    def session():
        with session_scope(engine) as s:
            yield s

    client = make_client(None)
    client.app.dependency_overrides[deps.get_session] = session
    return client


def operations(client):
    """(método, ruta) -> operación de OpenAPI, para todas las rutas publicadas."""
    schema = client.get("/openapi.json").json()
    return {(method.upper(), path): op for path, item in schema["paths"].items() for method, op in item.items()}


def test_every_route_is_covered(client):
    assert set(operations(client)) == set(ROUTES)


# --- Respuestas correctas ---


@pytest.mark.parametrize(("method", "path"), list(ROUTES))
def test_success_has_request_id_and_its_cache_policy(client, method, path):
    body, cache_control, _ = ROUTES[method, path]

    response = call(client, method, path, body)

    assert response.status_code == 200, response.json()
    assert response.headers["content-type"] == "application/json"
    assert len(response.headers[REQUEST_ID_HEADER]) == 32
    assert response.headers.get("cache-control") == cache_control


@pytest.mark.parametrize("path", [path for method, path in ROUTES if path.startswith("/v1/")])
def test_public_api_is_open_to_the_frontend(client, path):
    response = client.get(path, headers={"Origin": FRONTEND})
    assert response.headers["access-control-allow-origin"] == FRONTEND


# --- Errores ---


def assert_uniform_error(response, status, code):
    assert response.status_code == status
    error = response.json()["error"]
    assert error["code"] == code
    assert error["request_id"] == response.headers[REQUEST_ID_HEADER]
    assert response.headers["cache-control"] == "no-store"
    return error


@pytest.mark.parametrize(("method", "path"), DB_ROUTES)
def test_database_down_is_a_uniform_503(unreachable_client, method, path):
    body, _, _ = ROUTES[method, path]

    response = call(unreachable_client, method, path, body)

    assert_uniform_error(response, 503, "service_unavailable")
    assert response.headers["retry-after"] == "30"
    assert "luz:luz" not in response.text


@pytest.mark.parametrize(("method", "path"), list(ROUTES))
def test_wrong_method_is_a_uniform_405(client, method, path):
    wrong = "DELETE"
    assert_uniform_error(call(client, wrong, path), 405, "method_not_allowed")


@pytest.mark.parametrize(
    ("method", "path", "params", "body"),
    [
        ("GET", "/v1/prices", {"date": "ayer"}, None),
        ("GET", "/v1/forecast", {"date": "2026-13-01"}, None),
        ("GET", "/v1/best-hours", {"hours": "dos"}, None),
        ("GET", "/v1/history", {"start": "2026-10-01"}, None),
        ("GET", "/v1/market", {"end": "2026-10-01"}, None),
        ("GET", "/api/model", {"days": "-1"}, None),
        ("POST", "/api/tools/simulate", None, {"uses_per_week": -1}),
        ("POST", "/api/tools/plan", None, {"tasks": "lavadora"}),
        ("POST", "/api/tools/bill", None, {}),
    ],
)
def test_invalid_input_is_a_uniform_422(client, method, path, params, body):
    error = assert_uniform_error(client.request(method, path, params=params, json=body), 422, "validation_error")
    assert error["details"] and all(d["field"] and d["message"] for d in error["details"])


# --- Documentación ---


def test_every_operation_is_documented(client):
    tags = {tag["name"] for tag in TAGS}

    for (_, path), operation in operations(client).items():
        assert operation["summary"], path
        assert set(operation["tags"]) <= tags, path
        assert operation["responses"]["500"]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/ErrorResponse"
        }
        if operation.get("parameters") or operation.get("requestBody"):
            assert operation["responses"]["422"]["content"]["application/json"]["schema"] == {
                "$ref": "#/components/schemas/ErrorResponse"
            }, path

    assert "HTTPValidationError" not in client.get("/openapi.json").json()["components"]["schemas"]
