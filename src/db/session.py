"""Conexión a PostgreSQL.

Se usa `NullPool`: cada sesión abre su conexión y la cierra al terminar, sin
mantener conexiones abiertas entre peticiones. Es lo adecuado para la API en
Vercel (funciones serverless) junto con la cadena "pooled" de Neon, que ya
reutiliza conexiones en su lado.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine, make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from src.utils.config import get_settings


def make_engine(url: str | None = None) -> Engine:
    url = url or get_settings().database_url
    if not url:
        raise RuntimeError("Falta DATABASE_URL: defínela en .env (ver .env.example)")
    return create_engine(url, poolclass=NullPool)


@lru_cache
def get_engine() -> Engine:
    """Motor de la base de datos configurada, creado una sola vez por proceso."""
    return make_engine()


@contextmanager
def session_scope(engine: Engine | None = None) -> Iterator[Session]:
    """Sesión que confirma los cambios al terminar y los deshace si hay un error."""
    session = sessionmaker(bind=engine or get_engine(), expire_on_commit=False)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def check_test_database_url(test_url: str, database_url: str | None = None) -> None:
    """Impide que los tests, que vacían su base de datos, apunten a la de trabajo."""
    test = make_url(test_url)
    if not (test.database or "").endswith("_test"):
        raise RuntimeError(f"La base de datos de tests debe terminar en _test (es {test.database!r})")
    if database_url:
        real = make_url(database_url)
        if (test.host, test.port, test.database) == (real.host, real.port, real.database):
            raise RuntimeError("TEST_DATABASE_URL apunta a la misma base de datos que DATABASE_URL")
