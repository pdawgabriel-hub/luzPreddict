"""Las migraciones de Alembic deben crear exactamente las tablas de src/db/models.py."""

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text

from src.db.models import Base
from src.utils.config import ROOT_DIR, get_settings


@pytest.fixture
def alembic_config(db_engine):
    config = Config(ROOT_DIR / "alembic.ini")
    config.attributes["url"] = get_settings().test_database_url
    config.attributes["configure_logger"] = False
    return config


@pytest.fixture
def empty_database(db_engine):
    """Base de datos vacía; al terminar se dejan las tablas creadas para el resto de tests."""
    Base.metadata.drop_all(db_engine)
    with db_engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
    yield db_engine
    Base.metadata.create_all(db_engine)


def test_upgrade_creates_the_same_schema_as_the_models(alembic_config, empty_database):
    command.upgrade(alembic_config, "head")

    with empty_database.connect() as connection:
        context = MigrationContext.configure(connection, opts={"compare_type": True})
        differences = compare_metadata(context, Base.metadata)

    assert differences == [], f"Los modelos y las migraciones no coinciden: falta una migración ({differences})"


def test_database_is_at_the_latest_revision_after_upgrade(alembic_config, empty_database):
    command.upgrade(alembic_config, "head")

    head = ScriptDirectory.from_config(alembic_config).get_current_head()
    with empty_database.connect() as connection:
        assert MigrationContext.configure(connection).get_current_revision() == head


def test_downgrade_removes_every_table(alembic_config, empty_database):
    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, "base")

    assert set(inspect(empty_database).get_table_names()) <= {"alembic_version"}


def test_migrations_form_a_single_line():
    """Una sola cabeza: dos migraciones que parten de la misma darían conflictos al desplegar."""
    script = ScriptDirectory.from_config(Config(ROOT_DIR / "alembic.ini"))
    assert len(script.get_heads()) == 1
