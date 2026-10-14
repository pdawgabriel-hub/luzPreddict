# Datos

## La fuente: la API pública de REE

Todos los datos proceden de [apidatos.ree.es](https://www.ree.es/es/apidatos), la API pública
de Red Eléctrica, que no pide clave:

| Serie | Ruta de la API | Resolución | Desde |
|---|---|---|---|
| **PVPC 2.0TD** (precio de la luz del mercado regulado) | `mercados/precios-mercados-tiempo-real`, serie `PVPC` | horaria | 1 de junio de 2021 |
| **Estructura de la generación** (eólica, solar, nuclear, ciclo combinado…) | `generacion/estructura-generacion` | diaria | 1 de junio de 2021 |

La fecha de inicio es la de la tarifa 2.0TD: antes de junio de 2021 el PVPC tenía otra
estructura y no es comparable.

REE publica el PVPC del día siguiente **hacia las 20:15** (hora de Madrid). Los datos de
generación del día llegan durante el día siguiente.

## Ingesta

`src/ingestion/ree_client.py` es un cliente genérico:

- **Por tramos:** la API rechaza rangos de más de un mes natural, así que divide las fechas
  en tramos de 28 días como máximo (`REE_MAX_DAYS_PER_REQUEST`).
- **Reintentos:** reintenta los errores temporales (429 y 5xx) con espera creciente.
- **Fechas en UTC:** convierte cada punto a UTC y devuelve las series indexadas por tipo,
  tanto las simples como las agrupadas que REE devuelve con `content`.

Encima, `prices.py` y `generation.py` deciden qué pedir y cómo normalizarlo, y
`src/pipeline.py backfill` descarga **solo lo que falta**: desde el último día guardado
hasta mañana (o todo el histórico con `--full`). Repetirlo no duplica nada.

!!! note "Generación total"
    No se guarda la serie "Generación total" de REE: es la suma de las tecnologías y se
    puede calcular cuando haga falta.

## Cambios de hora

En hora de Madrid hay días de **23 horas** (último domingo de marzo) y de **25 horas**
(último domingo de octubre, con dos 2:00). Es la fuente de errores más típica en series
horarias, así que el proyecto sigue tres reglas:

1. **Todo se guarda en UTC**, donde la serie es siempre una hora tras otra.
2. Los días se calculan con `local_day_hours()` (`src/utils/calendar.py`), que devuelve las
   23, 24 o 25 horas de un día local.
3. Las variables del modelo comparan "la misma hora de hace k días" por **día y hora
   locales**, nunca desplazando filas: con `shift(24)`, la última hora de un día de 25 horas
   apuntaría a una hora del propio día, que todavía no se conoce.

Hay tests específicos para los días de 23 y 25 horas en la ingesta, las variables, la
previsión, las herramientas y la API.

## Limpieza

`clean_prices()` (`src/processing/clean.py`) convierte la tabla bruta en una serie horaria
continua en UTC:

- elimina duplicados (gana el último en llegar, por si REE corrige un precio);
- crea una fila por cada hora entre la primera y la última;
- **interpola solo los huecos de 3 horas o menos** y los marca en `is_interpolated`; los
  huecos más largos se quedan vacíos para no inventar datos.

## Base de datos

PostgreSQL con SQLAlchemy 2 (`src/db/models.py`). Todas las fechas se guardan como
`timestamptz` mediante un tipo propio, `UTCDateTime`, que **rechaza las fechas sin zona
horaria**: PostgreSQL las interpretaría con la zona del servidor y las desplazaría sin avisar.

| Tabla | Clave | Contenido |
|---|---|---|
| `price_hour` | `datetime` | PVPC de cada hora (€/MWh) |
| `generation_day` | `date`, `technology` | MWh generados por cada tecnología cada día |
| `model_artifact` | `version` | Modelo entrenado (binario) y sus metadatos: fechas, variables, parámetros y métricas |
| `model_run` | `id` (único por día previsto y momento) | Una ejecución de la previsión: día, modelo, versión y motivo del respaldo si lo hubo |
| `forecast_hour` | `run_id`, `datetime` | Previsión de cada hora y su intervalo (`lower`, `upper`) |
| `daily_error` | `day`, `model` | Error de la previsión de cada día frente al precio real (MAE, RMSE, sesgo) |

### Escrituras idempotentes

El repositorio (`src/db/repository.py`) escribe con `INSERT … ON CONFLICT DO UPDATE` y solo
toca las filas cuyo valor cambia (`IS DISTINCT FROM`). Guardar los mismos datos dos veces deja
la base igual que una sola vez, así que cualquier tarea se puede repetir sin miedo. Las
funciones devuelven cuántas filas eran nuevas o distintas, y así se sabe si la ejecución
cambió algo.

### Sin pandas en la base de datos

`src/db` recibe y devuelve tuplas y objetos de SQLAlchemy, porque la API lo importa y debe
seguir siendo ligera. La conversión a pandas para el modelo está en
`src/processing/dataset.py`, que solo usa el pipeline.

### Conexiones

`src/db/session.py` usa `NullPool`: cada sesión abre su conexión y la cierra al terminar. Es
lo adecuado para funciones serverless junto con la cadena *pooled* de Neon, que ya reutiliza
conexiones en su lado.

### Migraciones

Las migraciones están en `alembic/versions/` y se aplican con `make migrate` en local y con
el workflow **Migraciones** en Neon (ver [Automatización](automatizacion.md)).

- Los nombres de restricciones e índices siguen una convención fija (`NAMING_CONVENTION`),
  para que las migraciones generadas sean predecibles.
- Un test comprueba que las migraciones crean exactamente el mismo esquema que los modelos de
  SQLAlchemy y que forman una única línea.
- **Regla:** las migraciones son **aditivas** (columnas o tablas nuevas que admiten nulos).
  Así la versión anterior de la API sigue funcionando con la base ya migrada mientras Vercel
  termina de desplegar la nueva.
