"""Fixtures compartidas: base de datos de pruebas.

Los tests de base de datos usan TEST_DATABASE_URL (ver .env.example). Si no
está definida o el servidor no responde, se saltan en lugar de fallar.
"""

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from src.db.models import Base
from src.db.session import check_test_database_url, make_engine
from src.utils.config import get_settings


@pytest.fixture(scope="session")
def db_engine():
    settings = get_settings()
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL no está definida")
    check_test_database_url(settings.test_database_url, settings.database_url)

    engine = make_engine(settings.test_database_url)
    try:
        engine.connect().close()
    except OperationalError as exc:
        pytest.skip(f"No se puede conectar a la base de datos de pruebas: {exc.orig}")

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture
def db_session(db_engine):
    """Sesión dentro de una transacción que se deshace al acabar cada test."""
    connection = db_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    yield session
    session.close()
    transaction.rollback()
    connection.close()
