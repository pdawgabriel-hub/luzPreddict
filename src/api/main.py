"""Aplicación FastAPI de luzPreddict.

En local: `make api` (http://localhost:8000, documentación en /docs).
La API solo lee de la base de datos y usa `src.services`: no importa pandas ni
el modelo, para que sea ligera en Vercel.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from src.api.errors import error_responses, register_error_handlers
from src.api.middleware import REQUEST_ID_HEADER, RequestContextMiddleware
from src.utils.config import Settings, get_settings
from src.utils.logging import configure_logging

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

# Las respuestas pequeñas no compensan comprimirlas
GZIP_MINIMUM_BYTES = 1000


def create_app(settings: Settings | None = None) -> FastAPI:
    """Construye la aplicación. Los tests crean una nueva en cada caso."""
    settings = settings or get_settings()
    configure_logging()
    app = FastAPI(
        title="luzPreddict API",
        version=API_VERSION,
        description=DESCRIPTION,
        openapi_tags=TAGS,
        docs_url="/docs",
        redoc_url=None,
        responses=error_responses(500),
    )
    register_error_handlers(app)

    # El último que se añade es el primero en recibir la petición:
    # id y logging -> CORS -> GZip -> rutas
    app.add_middleware(GZipMiddleware, minimum_size=GZIP_MINIMUM_BYTES)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET"],  # API de solo lectura
        allow_headers=[REQUEST_ID_HEADER],
        expose_headers=[REQUEST_ID_HEADER],
        allow_credentials=False,  # sin usuarios ni cookies
        max_age=3600,
    )
    app.add_middleware(RequestContextMiddleware)

    @app.get("/", tags=["Estado"], summary="Información de la API")
    def root() -> dict[str, str]:
        return {"name": "luzPreddict API", "version": API_VERSION, "docs": "/docs"}

    return app


app = create_app()
