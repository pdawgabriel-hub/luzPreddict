"""Vuelve a descargar de REE las respuestas que usan los tests como fixtures.

Solo hace falta si REE cambia el formato de sus respuestas:
    python -m tests.fixtures.update_fixtures
"""

import json
from pathlib import Path

import requests

from src.utils.config import get_settings

FIXTURES_DIR = Path(__file__).parent

# nombre -> (indicador, inicio, fin, time_trunc)
REQUESTS = {
    # 26/10/2025: cambio a horario de invierno, 25 horas
    "pvpc_2025-10-25_26": ("mercados/precios-mercados-tiempo-real", "2025-10-25", "2025-10-26", "hour"),
    # 29/03/2026: cambio a horario de verano, 23 horas
    "pvpc_2026-03-29": ("mercados/precios-mercados-tiempo-real", "2026-03-29", "2026-03-29", "hour"),
    "generation_2026-09-28_10-03": ("generacion/estructura-generacion", "2026-09-28", "2026-10-03", "day"),
    # Más de un mes natural: REE responde 400
    "error_range_too_long": ("mercados/precios-mercados-tiempo-real", "2026-08-01", "2026-09-01", "hour"),
}


def main() -> None:
    base_url = get_settings().ree_api_url
    for name, (path, start, end, time_trunc) in REQUESTS.items():
        response = requests.get(
            f"{base_url}/{path}",
            params={"start_date": f"{start}T00:00", "end_date": f"{end}T23:59", "time_trunc": time_trunc},
            timeout=30,
        )
        fixture = {"status": response.status_code, "body": response.json()}
        target = FIXTURES_DIR / f"{name}.json"
        target.write_text(json.dumps(fixture, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"{target.name}: HTTP {response.status_code}, {target.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
