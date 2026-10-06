import logging

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from src.api.main import GZIP_MINIMUM_BYTES, create_app
from src.api.middleware import REQUEST_ID_HEADER
from src.utils.config import Settings

FRONTEND = "https://luzpreddict.vercel.app"


@pytest.fixture
def app():
    app = create_app(Settings(_env_file=None, cors_origins=[FRONTEND]))

    @app.get("/test/large")
    def large() -> dict[str, str]:
        return {"data": "x" * (GZIP_MINIMUM_BYTES * 2)}

    @app.get("/test/request-id")
    def request_id(request: Request) -> dict[str, str]:
        return {"request_id": request.state.request_id}

    @app.get("/test/boom")
    def boom() -> None:
        raise RuntimeError("fallo de prueba")

    return app


@pytest.fixture
def client(app):
    return TestClient(app)


# --- Id de petición ---


def test_every_response_has_a_request_id(client):
    first = client.get("/").headers[REQUEST_ID_HEADER]
    second = client.get("/").headers[REQUEST_ID_HEADER]

    assert len(first) == 32
    assert first != second


def test_a_valid_incoming_request_id_is_reused(client):
    response = client.get("/", headers={REQUEST_ID_HEADER: "web-1234.abc_9"})
    assert response.headers[REQUEST_ID_HEADER] == "web-1234.abc_9"


@pytest.mark.parametrize("bad", ["con espacios", "a" * 65, "id%0Afalso", "<script>", "id;otro"])
def test_an_unsafe_incoming_request_id_is_replaced(client, bad):
    response = client.get("/", headers={REQUEST_ID_HEADER: bad})
    assert response.headers[REQUEST_ID_HEADER] != bad
    assert len(response.headers[REQUEST_ID_HEADER]) == 32


def test_routes_can_read_the_request_id(client):
    response = client.get("/test/request-id")
    assert response.json()["request_id"] == response.headers[REQUEST_ID_HEADER]


def test_errors_also_get_a_request_id(client):
    assert REQUEST_ID_HEADER in client.get("/no-existe").headers


# --- Logging ---


def test_each_request_is_logged_with_its_id(client, caplog):
    with caplog.at_level(logging.INFO, logger="src.api.requests"):
        response = client.get("/no-existe")

    [record] = caplog.records
    assert record.levelno == logging.INFO
    assert record.getMessage().startswith("GET /no-existe 404 ")
    assert record.getMessage().endswith(f"id={response.headers[REQUEST_ID_HEADER]}")


def test_unhandled_errors_are_logged_as_500(app, caplog):
    client = TestClient(app, raise_server_exceptions=False)
    with caplog.at_level(logging.INFO, logger="src.api.requests"):
        assert client.get("/test/boom").status_code == 500

    [record] = [r for r in caplog.records if r.name == "src.api.requests"]
    assert record.levelno == logging.ERROR
    assert record.getMessage().startswith("GET /test/boom 500 ")


# --- CORS ---


def test_cors_allows_the_frontend(client):
    response = client.get("/", headers={"Origin": FRONTEND})

    assert response.headers["access-control-allow-origin"] == FRONTEND
    assert REQUEST_ID_HEADER in response.headers["access-control-expose-headers"]
    assert "access-control-allow-credentials" not in response.headers


def test_cors_ignores_other_origins(client):
    response = client.get("/", headers={"Origin": "https://otra-web.example"})

    assert response.status_code == 200  # la petición se atiende; es el navegador quien la bloquea
    assert "access-control-allow-origin" not in response.headers


def test_cors_preflight_only_allows_get(client):
    allowed = client.options("/", headers={"Origin": FRONTEND, "Access-Control-Request-Method": "GET"})
    denied = client.options("/", headers={"Origin": FRONTEND, "Access-Control-Request-Method": "DELETE"})

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-methods"] == "GET"
    assert REQUEST_ID_HEADER in allowed.headers  # el preflight también se registra
    assert denied.status_code == 400


# --- GZip ---


def test_large_responses_are_compressed(client):
    response = client.get("/test/large", headers={"Accept-Encoding": "gzip"})

    assert response.headers["content-encoding"] == "gzip"
    assert response.json()["data"] == "x" * (GZIP_MINIMUM_BYTES * 2)  # el cliente la descomprime
    assert REQUEST_ID_HEADER in response.headers


def test_small_responses_are_not_compressed(client):
    response = client.get("/", headers={"Accept-Encoding": "gzip"})
    assert "content-encoding" not in response.headers


def test_no_compression_if_the_client_does_not_accept_it(client):
    response = client.get("/test/large", headers={"Accept-Encoding": "identity"})
    assert "content-encoding" not in response.headers
