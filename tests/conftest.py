"""Fixtures compartidas: base de datos de pruebas y pipeline.

Los tests de base de datos usan TEST_DATABASE_URL (ver .env.example). Si no
está definida o el servidor no responde, se saltan en lugar de fallar.
"""

from contextlib import contextmanager

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from src.db.models import Base
from src.db.session import check_test_database_url, make_engine
from src.models import lightgbm_model
from src.processing import dataset
from src.utils.config import get_settings
from tests.fakes import FAST_PARAMS, SEEDED_DAYS, synthetic_prices


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


# --- Pipeline ---


@pytest.fixture
def fast_model(monkeypatch):
    monkeypatch.setattr(lightgbm_model, "DEFAULT_PARAMS", {**lightgbm_model.DEFAULT_PARAMS, **FAST_PARAMS})


@pytest.fixture
def seeded(db_session):
    """Base de datos con 40 días de precios, hasta SEEDED_LAST_DAY (9 de febrero de 2026)."""
    dataset.save_prices(db_session, synthetic_prices(n_days=SEEDED_DAYS).reset_index())
    return db_session


@pytest.fixture
def sessions(db_session):
    """Sustituye a session_scope en `daily`: todos los pasos usan la sesión del test."""

    @contextmanager
    def factory():
        yield db_session
        db_session.flush()

    return factory
