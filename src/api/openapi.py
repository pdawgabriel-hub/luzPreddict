"""Exporta el esquema OpenAPI de la API a un fichero.

La web genera sus tipos de TypeScript a partir de él (`make api-types`), así que
los datos de ejemplo y las páginas usan los mismos esquemas que FastAPI. Un
test comprueba que el fichero del repositorio está al día.

    python -m src.api.openapi frontend/src/api/openapi.json
"""

import json
import sys
from pathlib import Path
from typing import Any

from src.api.main import create_app
from src.utils.config import Settings

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "frontend" / "src" / "api" / "openapi.json"


def openapi_schema() -> dict[str, Any]:
    # Sin .env: el esquema no debe depender de la configuración de quien lo genera
    return create_app(Settings(_env_file=None)).openapi()


def render(schema: dict[str, Any]) -> str:
    return json.dumps(schema, ensure_ascii=False, indent=2) + "\n"


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    path = Path(args[0]) if args else DEFAULT_PATH
    path.write_text(render(openapi_schema()), encoding="utf-8")
    print(f"Esquema OpenAPI guardado en {path}")


if __name__ == "__main__":
    main()
