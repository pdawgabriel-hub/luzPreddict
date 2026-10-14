# API

FastAPI (`src/api/`), desplegada como función de Python en Vercel. Es de **solo lectura**,
sin claves ni usuarios. La documentación interactiva está en
[/docs](https://luzpreddict.vercel.app/docs) y el esquema, en
[/openapi.json](https://luzpreddict.vercel.app/openapi.json).

## Endpoints

### API pública (`/v1`)

| Endpoint | Para qué | Parámetros |
|---|---|---|
| `GET /v1/prices` | PVPC de un día o de un rango, con el periodo de la tarifa de cada hora | `date`, o `start` y `end` (31 días como máximo) |
| `GET /v1/forecast` | Previsión de un día con su rango probable y, si ya se publicó, el precio real y el error | `date` (por defecto, la más reciente) |
| `GET /v1/best-hours` | Las horas seguidas más baratas para consumir y las más baratas sueltas | `hours`, `date`, `from_hour`, `to_hour` |
| `GET /v1/history` | Resumen de cada día: media, mínimo, máximo y error de la previsión | `start`, `end` (366 días como máximo, 30 por defecto) |
| `GET /v1/market` | Mix de generación diario y peso de las renovables | `start`, `end` |

Ejemplo:

```bash
curl -s "https://luzpreddict.vercel.app/v1/best-hours?hours=3&from_hour=8&to_hour=22"
```

### Rutas internas de la web (`/api`)

| Endpoint | Para qué |
|---|---|
| `GET /api/tools/catalog` | Aparatos, perfiles de consumo y potencias para los formularios |
| `POST /api/tools/simulate` | Coste de un aparato a una hora y ahorro moviéndolo a la mejor |
| `POST /api/tools/plan` | Reparto de varios aparatos en las horas baratas sin superar la potencia contratada |
| `POST /api/tools/bill` | Coste de la energía con PVPC frente a un precio fijo |
| `GET /api/model` | Modelo en uso, backtest y error real de los últimos días |

### Estado

`GET /health` devuelve el último precio, la última previsión y el modelo en uso, con avisos si
algo está desactualizado (`status: degraded`). Responde 200 aunque haya avisos, para que la web
los pueda mostrar, y 503 si la base de datos no responde.

## Convenciones de las respuestas

- Precios en **€/MWh** y horas en **hora de Madrid**, en ISO 8601 con desfase
  (`2026-10-14T20:00:00+02:00`). Los días de cambio de hora tienen 23 o 25 entradas.
- Cada respuesta de `/v1` incluye `source`, con la serie de REE de la que salen los datos, y
  la previsión incluye `disclaimer`: es orientativa.
- **Errores uniformes:** cualquier error, sea un 404, un 422 o un fallo interno, tiene la misma
  forma:

```json
{"error": {"code": "not_found", "message": "REE aún no ha publicado los precios del 2026-10-15 (lo hace hacia las 20:15)", "request_id": "3ff3…", "details": []}}
```

`request_id` coincide con la cabecera `X-Request-ID` y con la línea del log, y sirve para
encontrar una petición concreta en los logs de Vercel. Si la base de datos no responde (por
ejemplo, Neon despertando), la respuesta es un **503 con `Retry-After`**.

## Caché

Los datos solo cambian cuando corre la tarea diaria, así que las respuestas de `/v1` y de
`/api/model` llevan `Cache-Control` hasta la siguiente ejecución (19:50 o 21:50 UTC, con
margen para que termine). El navegador y la **CDN de Vercel** no las vuelven a pedir antes, y
la mayoría de las visitas no llegan ni a la función ni a Neon. Los errores llevan `no-store`:
un "aún no publicado" no debe quedarse en caché.

## Límite de peticiones

`src/api/rate_limit.py`: **60 peticiones por minuto e IP** en `/v1` y `/api`, con un contador
por minuto en Upstash Redis (`INCR` + `EXPIRE` en una sola petición REST, sin dependencias
nuevas).

- Las respuestas llevan `X-RateLimit-Limit`, `X-RateLimit-Remaining` y `X-RateLimit-Reset`. Al
  superarlo, la respuesta es un **429** con el formato de error común y `Retry-After`.
- **Privacidad:** la clave en Redis es un HMAC de la IP con el token como secreto, y caduca al
  minuto. No se guardan IPs.
- **Si Upstash falla o tarda más de 1 s, la petición pasa:** es preferible no limitar a dejar
  la API sin servicio.
- Sin las variables de Upstash (tests, CI, Docker) el límite está desactivado.
- `/health`, `/docs` y `/openapi.json` no están limitados. Las respuestas que sirve la CDN
  tampoco cuentan, porque no llegan a la API.

## Estructura del código

```text
src/api/
├── main.py         # create_app(): middlewares, routers, CORS y GZip
├── middleware.py   # id de petición y una línea de log por petición
├── errors.py       # formato de error común y manejadores
├── deps.py         # sesión, hora actual y validación de fechas y rangos
├── cache.py        # Cache-Control hasta la siguiente actualización
├── rate_limit.py   # límite por IP con Upstash
├── queries.py      # consultas compartidas por varios routers
├── openapi.py      # genera frontend/src/api/openapi.json
├── schemas/        # modelos de Pydantic de las respuestas
└── routers/
    ├── health.py
    ├── v1/         # API pública
    └── web/        # herramientas y modelo, para la web
```

La lógica de negocio (mejores horas, simulador, planificador, tarifa y mix) está en
`src/services/`, en Python puro sin pandas. La usan la API y el pipeline, y se prueba sin
levantar ningún servidor.

!!! warning "Ninguna carpeta llamada `public`"
    Vercel trata las carpetas `public/` como ficheros estáticos y las deja fuera de la función.
    Por eso los routers de la API pública están en `routers/v1/`, y un test impide volver a
    usar ese nombre.

## Tipos para la web

`make api-types` genera `frontend/src/api/openapi.json` desde la app y, con
`openapi-typescript`, `frontend/src/api/schema.d.ts`. La web usa esos tipos, así que si la API
cambia y no se regeneran, falla el typecheck. Además, un test de Python y un paso del CI
comprueban que los ficheros generados están al día.
