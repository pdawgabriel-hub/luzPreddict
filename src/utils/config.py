"""Configuración central del proyecto.

Los valores se leen de variables de entorno o del fichero `.env` de la raíz
(ver `.env.example`). Si no existen, se usan los valores por defecto.
"""

from datetime import date
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Rutas de caché local (en producción los datos viven en PostgreSQL)
    data_dir: Path = ROOT_DIR / "data"
    models_dir: Path = ROOT_DIR / "models"

    # Zona horaria del mercado eléctrico peninsular
    timezone: str = "Europe/Madrid"

    # API pública de REE (sin token)
    ree_api_url: str = "https://apidatos.ree.es/es/datos"
    ree_timeout_seconds: float = Field(default=30, gt=0)
    # La API rechaza rangos que superen un mes natural; 28 días nunca lo superan
    ree_max_days_per_request: int = Field(default=28, ge=1, le=28)
    # Primer día con PVPC 2.0TD
    history_start: date = date(2021, 6, 1)

    # PostgreSQL (formato SQLAlchemy: postgresql+psycopg://usuario:contraseña@host:puerto/base)
    database_url: str | None = None
    # Base de datos que vacían los tests: debe ser distinta y su nombre terminar en "_test"
    test_database_url: str | None = None

    @field_validator("timezone")
    @classmethod
    def _check_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"Zona horaria desconocida: {value}") from exc
        return value

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def processed_dir(self) -> Path:
        return self.data_dir / "processed"


@lru_cache
def get_settings() -> Settings:
    """Devuelve la configuración, leída una sola vez por proceso."""
    return Settings()
