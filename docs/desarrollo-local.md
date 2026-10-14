# Desarrollo local

Hay dos formas de ponerlo en marcha: con Python y Node en tu máquina, para desarrollar, o con
Docker, para verlo funcionando sin instalar nada más.

## Con Python y Node

Requisitos: **Python 3.12**, **Node 22** y un **PostgreSQL 16** al que puedas conectarte.

```bash
python3 -m venv venv
make install          # dependencias de Python y de la web, y hooks de pre-commit
cp .env.example .env  # y define DATABASE_URL y TEST_DATABASE_URL
make migrate          # crea las tablas
make backfill         # descarga el histórico de REE (unos minutos)
make train            # entrena y guarda el modelo
make pipeline         # la tarea diaria: ingesta, previsión y error
make dev              # API en :8000 y web en :5173 a la vez
```

La web queda en <http://localhost:5173>. Vite reenvía `/v1`, `/api`, `/health` y `/docs` a la API,
así que web y API comparten origen, como en Vercel.

!!! tip "Sin backend"
    `make web-mocks` arranca la web con datos de ejemplo, sin API ni base de datos.
    `make web-mocks SCENARIO=stale` (o `error`, o `slow`) muestra los avisos, los errores o las
    cargas.

### Variables de entorno

Todas son opcionales salvo las de la base de datos; `.env.example` las documenta.

| Variable | Para qué |
|---|---|
| `DATABASE_URL` | Base de datos de trabajo (`postgresql+psycopg://usuario:contraseña@host:puerto/base`) |
| `TEST_DATABASE_URL` | Base que vacían los tests: distinta de la anterior y terminada en `_test` |
| `CORS_ORIGINS` | Orígenes que pueden llamar a la API desde un navegador |
| `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN` | Activan el límite de peticiones (sin ellas, desactivado) |
| `NTFY_TOPIC`, `SITE_URL` | Solo para `daily --notify` |
| `REE_API_URL`, `HISTORY_START`, `TIMEZONE`… | Para cambiar la fuente o el periodo, raramente necesarias |

## Con Docker

Solo hace falta Docker con Compose.

```bash
make docker-up     # PostgreSQL, API y web
make docker-seed   # la primera vez: histórico de REE, entrenamiento y previsión de mañana
make docker-down   # para todo (los datos se conservan)
```

La web queda en <http://localhost:8080>, con la API en las mismas rutas que en producción
(<http://localhost:8080/docs>). PostgreSQL escucha en el puerto **5434** para no chocar con otro
servidor local; `WEB_PORT` y `DB_PORT` cambian los puertos.

| Servicio | Imagen | Qué hace |
|---|---|---|
| `db` | `postgres:16-alpine` | Base de datos, con un volumen persistente |
| `migrate` | `Dockerfile`, etapa `pipeline` | Aplica las migraciones y termina |
| `api` | `Dockerfile`, etapa `api` | La API con uvicorn, con lo mismo que instala Vercel |
| `web` | `frontend/Dockerfile` | La web compilada, servida por nginx, que reenvía las rutas de la API |
| `pipeline` | `Dockerfile`, etapa `pipeline` | Bajo demanda: `docker compose run --rm pipeline backfill`, `train` o `daily` |

## Comandos

`make help` los lista todos. Los más usados:

| Comando | Qué hace |
|---|---|
| `make lint` / `make format` | Revisa el código / lo corrige y formatea |
| `make test` | Tests de Python y de la web |
| `make api` / `make web` / `make dev` | La API, la web o las dos |
| `make api-types` | Regenera el OpenAPI y los tipos de TypeScript tras cambiar la API |
| `make backtest` | Compara LightGBM con las referencias desde 2025 |
| `make docs` | Esta guía en <http://localhost:8001>, recargando al guardar |
