import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from src.api.main import API_VERSION, create_app


@pytest.fixture
def client():
    return TestClient(create_app())


def test_root_describes_the_api(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"name": "luzPreddict API", "version": API_VERSION, "docs": "/docs"}


def test_interactive_documentation_is_available(client):
    response = client.get("/docs")

    assert response.status_code == 200
    assert "swagger" in response.text.lower()


def test_openapi_schema_describes_the_api_in_spanish(client):
    schema = client.get("/openapi.json").json()

    assert schema["info"]["title"] == "luzPreddict API"
    assert schema["info"]["version"] == API_VERSION
    assert "€/MWh" in schema["info"]["description"]
    assert {tag["name"] for tag in schema["tags"]} == {"Precios", "Previsión", "Mercado", "Herramientas", "Estado"}


def test_each_call_creates_an_independent_app():
    assert create_app() is not create_app()


def test_unknown_routes_return_404(client):
    assert client.get("/no-existe").status_code == 404


def test_the_api_does_not_import_pandas_or_the_model():
    """La API se despliega en Vercel: debe arrancar sin librerías pesadas."""
    code = "import sys, src.api.main; print({'pandas', 'numpy', 'lightgbm', 'sklearn'} & set(sys.modules))"
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert result.stdout.strip() == "set()"
