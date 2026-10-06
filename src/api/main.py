"""Aplicación FastAPI de luzPreddict.

En local: `make api` (http://localhost:8000, documentación en /docs).
La API solo lee de la base de datos y usa `src.services`: no importa pandas ni
el modelo, para que sea ligera en Vercel.
"""

from fastapi import FastAPI

API_VERSION = "0.1.0"

DESCRIPTION = """
Precio de la luz (PVPC) en España: precios publicados por Red Eléctrica (REE),
previsión del día siguiente y herramientas para decidir cuándo consumir.

- Los precios se dan en **€/MWh** (1 €/MWh = 0,001 €/kWh).
- Las horas van en **hora local de Madrid**, en formato ISO 8601 con desfase.
- La previsión es **orientativa** y no garantiza el precio final.

Datos: [API pública de REE](https://www.ree.es/es/apidatos).
"""

TAGS = [
    {"name": "Precios", "description": "PVPC publicado por REE"},
    {"name": "Previsión", "description": "Previsión del PVPC del día siguiente"},
    {"name": "Mercado", "description": "Mix de generación y peso renovable"},
    {"name": "Herramientas", "description": "Simulador, planificador y factura (uso interno de la web)"},
    {"name": "Estado", "description": "Estado del servicio y frescura de los datos"},
]


def create_app() -> FastAPI:
    """Construye la aplicación. Los tests crean una nueva en cada caso."""
    app = FastAPI(
        title="luzPreddict API",
        version=API_VERSION,
        description=DESCRIPTION,
        openapi_tags=TAGS,
        docs_url="/docs",
        redoc_url=None,
    )

    @app.get("/", tags=["Estado"], summary="Información de la API")
    def root() -> dict[str, str]:
        return {"name": "luzPreddict API", "version": API_VERSION, "docs": "/docs"}

    return app


app = create_app()
