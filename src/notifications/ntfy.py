"""Envío de notificaciones a ntfy (https://ntfy.sh), sin cuentas.

Un tema de ntfy es solo un nombre: quien lo conoce puede leerlo y publicar en él. Por eso
se usa un único tema privado, de nombre aleatorio, solo para el desarrollador: le llegan
el resumen diario (señal de que la tarea ha funcionado) y los avisos de fallo, que envían
los workflows de GitHub con curl.

Se publica en JSON en lugar de con cabeceras, que no admiten bien las tildes del título.
"""

import json
import urllib.request

TIMEOUT_SECONDS = 10


def publish(
    server: str,
    topic: str,
    title: str,
    message: str,
    click: str | None = None,
    timeout: float = TIMEOUT_SECONDS,
) -> str:
    """Publica un mensaje y devuelve su id en ntfy. Lanza una excepción si ntfy lo rechaza."""
    payload = {"topic": topic, "title": title, "message": message}
    if click:
        payload["click"] = click  # al tocar la notificación se abre esta dirección
    request = urllib.request.Request(
        server.rstrip("/"),
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)["id"]
