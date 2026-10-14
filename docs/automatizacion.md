# Automatización

Todo el trabajo periódico corre en **GitHub Actions** (`.github/workflows/`). El repositorio
es público, así que las máquinas son gratuitas.

## Los workflows

| Workflow | Cuándo | Qué hace |
|---|---|---|
| **CI** (`ci.yml`) | Cada push y PR a `main` | Python: ruff y pytest contra un PostgreSQL de servicio. Web: oxlint, tipos, tipos de la API al día, tests con cobertura, build y que el build no lleve los datos de ejemplo. |
| **Tarea diaria** (`daily.yml`) | 19:30 y 21:30 UTC, y a mano | Migraciones pendientes, ingesta, previsión, error diario y resumen en ntfy |
| **Reentrenamiento semanal** (`weekly-train.yml`) | Domingos a las 3:00 UTC, y a mano | Entrena LightGBM, lo guarda con sus métricas y poda los modelos antiguos |
| **Carga del histórico** (`backfill.yml`) | A mano | Migraciones, descarga desde 2021 (o lo que falte) y, si se marca, entrenamiento |
| **Migraciones** (`migrate.yml`) | Push a `main` que toque `alembic/` o los modelos, y a mano | `alembic upgrade head` en Neon |
| **Lighthouse** (`lighthouse.yml`) | Tras cada despliegue a producción, y a mano | Audita la web publicada (ver [Calidad](calidad.md)) |
| **Guía técnica** (`docs.yml`) | Push a `main` que toque `docs/`, y a mano | Construye esta guía y la publica en GitHub Pages |

Además, **Dependabot** (`.github/dependabot.yml`) abre cada lunes PRs con las dependencias
que tienen versión nueva (ver [Despliegue y operación](despliegue.md#dependabot)).

## La tarea diaria

```text
python -m src.pipeline daily --notify [--last-attempt]
```

Cada paso va en su propia transacción:

1. **Ingesta:** descarga de REE desde el último día guardado hasta mañana.
2. **Previsión:** del primer día sin precio publicado, con el último modelo. Si la última
   previsión de ese día tiene el mismo modelo y los mismos valores, no se duplica.
3. **Error diario:** recalcula el error de los últimos 7 días publicados, por si REE corrige
   algún precio.
4. **Estado:** `completo` si ya están los precios de mañana; `pendiente` si REE aún no los ha
   publicado (entonces se prevé mañana igualmente).

**Horario.** El cron va en UTC: las 19:30 UTC son las 21:30 en verano y las 20:30 en invierno,
siempre después de la publicación de REE (hacia las 20:15). La ejecución de las 21:30 UTC es el
reintento, y si en ella REE sigue sin publicar, la ejecución deja un aviso amarillo. Las horas
de caducidad de la caché de la API (`src/api/cache.py`) dependen de este horario.

**Resumen de la ejecución.** En GitHub, la tarea escribe una tabla en la página de la
ejecución (estado, día previsto, modelo, media, horas más barata y más cara) y deja `status`
como salida del paso.

## Notificaciones por ntfy

[ntfy.sh](https://ntfy.sh) envía notificaciones al móvil sin cuentas: un **tema** es solo un
nombre, y quien lo conoce puede suscribirse.

| Tema | Quién lo conoce | Qué llega |
|---|---|---|
| `luzpreddict` (público) | Cualquiera: lo enlaza la página Alertas | El resumen de mañana: media, franja más barata y más cara, mejores horas y comparación con hoy |
| Privado, de nombre aleatorio | Solo el autor (secreto `NTFY_ADMIN_TOPIC`) | Aviso con enlace a la ejecución si falla la tarea diaria, el reentrenamiento o una migración |

**Una vez al día como mucho.** El resumen se envía cuando la tarea recibe **por primera vez**
los precios de mañana. Para saberlo, compara el último día con precio antes y después de la
ingesta, sin guardar nada más. Si en el último intento REE aún no ha publicado, se envía el de
la **previsión**, indicándolo. En local (`make pipeline`) nunca se envía nada: hace falta la
opción `--notify`, que solo usa el workflow.

**Si ntfy falla,** la tarea no falla: los datos ya están guardados. Queda en el log y como
aviso en la ejecución.

**El aviso de fallo** se envía con `curl` y `jq`, sin Python, para que funcione aunque lo roto
sea el propio entorno de Python.

## Secretos y variables

| Nombre | Dónde | Para qué |
|---|---|---|
| `DATABASE_URL` | Secreto de GitHub y variable de Vercel | Cadena *pooled* de Neon (`postgresql+psycopg://…`) |
| `NTFY_ADMIN_TOPIC` | Secreto de GitHub | Tema privado para los avisos de fallo |
| `NTFY_TOPIC`, `SITE_URL` | `daily.yml` (no son secretos) | Tema público del resumen y web que se abre al tocar la notificación |
| `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN` | Vercel | Límite de peticiones de la API |
| `CORS_ORIGINS` | Vercel | Dominios que pueden llamar a la API desde un navegador |

Ningún secreto se versiona: en local van en `.env` (ver `.env.example`), que está en
`.gitignore`. La carga del histórico comprueba el formato de `DATABASE_URL` antes de usarlo y
explica qué le pasa (comillas, espacios, prefijo incorrecto…) sin mostrar el valor.

## Concurrencia

Los workflows que escriben en la base de datos (tarea diaria, reentrenamiento, carga del
histórico y migraciones) comparten el grupo `neon-database` con `cancel-in-progress: false`:
nunca se solapan, y si coinciden, esperan su turno en lugar de cancelarse.

!!! note "Cron y repositorios inactivos"
    GitHub desactiva los workflows programados de un repositorio público tras 60 días sin
    commits. Fusionar las PRs de Dependabot de vez en cuando lo evita. Si ocurre, GitHub avisa
    por correo y se reactivan con un clic en la pestaña Actions.
