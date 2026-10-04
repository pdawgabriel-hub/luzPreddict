from datetime import date

import pytest
from pydantic import ValidationError

from src.utils.config import ROOT_DIR, Settings, get_settings


def test_defaults():
    settings = Settings(_env_file=None)
    assert settings.timezone == "Europe/Madrid"
    assert settings.ree_max_days_per_request == 28
    assert settings.history_start == date(2021, 6, 1)
    assert settings.raw_dir == ROOT_DIR / "data" / "raw"
    assert settings.processed_dir == ROOT_DIR / "data" / "processed"


def test_environment_overrides_defaults(monkeypatch):
    monkeypatch.setenv("REE_TIMEOUT_SECONDS", "10")
    monkeypatch.setenv("HISTORY_START", "2023-01-01")
    settings = Settings(_env_file=None)
    assert settings.ree_timeout_seconds == 10
    assert settings.history_start == date(2023, 1, 1)


def test_rejects_unknown_timezone(monkeypatch):
    monkeypatch.setenv("TIMEZONE", "Europe/Atlantida")
    with pytest.raises(ValidationError, match="Zona horaria desconocida"):
        Settings(_env_file=None)


def test_rejects_chunks_longer_than_ree_allows(monkeypatch):
    monkeypatch.setenv("REE_MAX_DAYS_PER_REQUEST", "31")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_get_settings_is_cached():
    assert get_settings() is get_settings()
