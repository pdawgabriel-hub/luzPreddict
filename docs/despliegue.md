# Despliegue y operación

## Vercel

`vercel.json` usa **Services**: dos servicios en el mismo proyecto y el mismo dominio, en la
región de Frankfurt (`fra1`).

| Servicio | Raíz | Qué es |
|---|---|---|
| `web` | `frontend/` | Build de Vite (`npm ci` y `npm run build`), servido como estático. Los ficheros de `/assets/` llevan caché de un año, porque su nombre incluye un hash, y cualquier otra ruta devuelve `index.html`. |
| `api` | raíz | FastAPI desde `src.api.main:app`, con `requirements.txt`. La función excluye `frontend/`, `tests/` y `notebooks/`. |

Las reglas de `rewrites` envían `/v1/*`, `/api/*`, `/health`, `/docs` y `/openapi.json` a la API,
que recibe la ruta completa, y todo lo demás a la web. Es el mismo reparto que hacen el proxy de
Vite y el nginx de Docker en local.

Cada push a `main` despliega producción. Cada PR, por ejemplo las de Dependabot, tiene su propio
despliegue de prueba, que no afecta a `luzpreddict.vercel.app`.

**Variables de entorno en Vercel:** `DATABASE_URL`, `UPSTASH_REDIS_REST_URL`,
`UPSTASH_REDIS_REST_TOKEN` y `CORS_ORIGINS`. Un cambio de variables solo se aplica en un
despliegue nuevo: hay que usar **Redeploy**.

!!! warning "Dos trampas de Vercel"
    - **`pyproject.toml`:** si Vercel lo ve, lo prefiere a `requirements.txt` para instalar
      las dependencias de Python. El nuestro solo configura pytest y ruff, así que la API se
      quedaría sin FastAPI. Por eso está en `.vercelignore`.
    - **Carpetas `public/`:** Vercel las trata como estáticos y las saca de la función. Ninguna
      carpeta de `src/` puede llamarse así, y un test lo vigila.

## Neon

PostgreSQL 16 en Frankfurt, plan gratuito (0,5 GB; la base ocupa unos 16 MB). Se usa la cadena
**pooled** (el host contiene `-pooler`), adecuada para funciones serverless. Neon se suspende a
los 5 minutos sin uso y la primera consulta tarda un segundo en despertarla; si tardara más, la
API responde 503 con `Retry-After` y la web ofrece reintentar.

## Upstash

Redis en Frankfurt, plan gratuito, solo para el contador del límite de peticiones. Las claves
caducan al minuto, así que no crece.

## Dependabot

Cada lunes a las 7:00 (hora de Madrid) abre PRs con versiones nuevas de:

- **GitHub Actions, npm y pip:** las versiones menores y los parches llegan juntos en una sola
  PR por ecosistema; las mayores, en PRs aparte.
- **Imágenes de Docker:** solo parches de las versiones actuales. Nunca propone versiones
  mayores (PostgreSQL 16, Node 22, nginx 1) ni otro Python: la imagen de la API sigue en el 3.12
  del CI y de Vercel.

Nada cambia en producción hasta fusionar una PR, y cada PR pasa el CI y tiene su despliegue de
prueba.

## Coste

| Servicio | Plan | Coste |
|---|---|---|
| GitHub Actions | Gratuito (repositorio público) | 0 € |
| Neon | Gratuito: 0,5 GB y horas de cómputo suficientes para una base que se suspende sola | 0 € |
| Vercel | Hobby | 0 € |
| Upstash | Gratuito | 0 € |
| ntfy.sh | Gratuito | 0 € |
| GitHub Pages (esta guía) | Gratuito | 0 € |

La caché de la CDN es lo que mantiene el consumo bajo: las respuestas de la API se sirven desde
Vercel sin ejecutar la función ni consultar Neon hasta la siguiente actualización.

## Qué hacer si…

**…la web dice "No se han podido cargar los datos".** Abre `/health`. Si responde 503, la base de
datos no está disponible: revisa en Vercel que `DATABASE_URL` sea la de Neon (con `-pooler`) y
no la local. Si responde con avisos, la tarea diaria no ha guardado datos: mira la última
ejecución en Actions.

**…llega un aviso de fallo por ntfy.** Toca la notificación: abre la ejecución fallida. Los
fallos de red con REE se suelen arreglar solos en el reintento de las 21:30 UTC o al día
siguiente; la tarea es idempotente y recoge lo que falte.

**…REE no publica.** La web muestra la previsión hasta que publique, el resumen interno de ntfy
llega con la previsión en el último intento del día y la tarea siguiente recoge los precios.

**…el modelo se ha quedado anticuado.** `/health` avisa si tiene más de 14 días. Lanza a mano
**Reentrenamiento semanal**; mientras tanto, la previsión sigue funcionando con el último modelo
o, si no se puede usar, con el respaldo "precio de ayer".

**…hay que rellenar un hueco de datos.** Lanza **Carga del histórico**: sin marcar "todo de
nuevo", solo descarga lo que falta.
