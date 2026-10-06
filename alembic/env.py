"""Entorno de Alembic.

- La conexión sale de DATABASE_URL, o de `config.attributes["url"]` cuando se
  llama desde código (los tests apuntan así a la base de datos de pruebas).
- Las tablas de referencia son las de `src/db/models.py`.
- `UTCDateTime` se escribe en las migraciones como `sa.DateTime(timezone=True)`:
  así las migraciones no dependen del código de la aplicación.
"""

from logging.config import fileConfig

import sqlalchemy as sa
from alembic import context
from sqlalchemy.pool import NullPool

from src.db.models import Base, UTCDateTime
from src.utils.config import get_settings

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def database_url() -> str:
    url = config.attributes.get("url") or get_settings().database_url
    if not url:
        raise RuntimeError("Falta DATABASE_URL: defínela en .env (ver .env.example)")
    return url


def render_item(type_: str, obj, autogen_context):
    """Escribe los tipos propios como tipos estándar de SQLAlchemy."""
    if type_ == "type" and isinstance(obj, UTCDateTime):
        return "sa.DateTime(timezone=True)"
    return False


def run_migrations_offline() -> None:
    """Genera el SQL sin conectarse (alembic upgrade head --sql)."""
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_item=render_item,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = sa.create_engine(database_url(), poolclass=NullPool)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_item=render_item,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
