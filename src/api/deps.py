"""Dependencias comunes de las rutas.

En los tests se sustituyen con `app.dependency_overrides` (sesión de la base de
pruebas, hora fija).
"""

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from src.db.session import session_scope


def get_session() -> Iterator[Session]:
    """Una sesión por petición, con su propia conexión (NullPool)."""
    with session_scope() as session:
        yield session


def get_now() -> datetime:
    """Hora actual en UTC."""
    return datetime.now(UTC)


SessionDep = Annotated[Session, Depends(get_session)]
NowDep = Annotated[datetime, Depends(get_now)]
