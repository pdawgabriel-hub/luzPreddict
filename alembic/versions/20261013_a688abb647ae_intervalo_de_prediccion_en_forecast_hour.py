"""intervalo de predicción en forecast_hour

Revisión: a688abb647ae
Anterior: 2d830440ab41
Fecha: 2026-10-13 16:24:16.482159+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a688abb647ae"
down_revision: str | Sequence[str] | None = "2d830440ab41"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("forecast_hour", sa.Column("lower", sa.Float(), nullable=True))
    op.add_column("forecast_hour", sa.Column("upper", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("forecast_hour", "upper")
    op.drop_column("forecast_hour", "lower")
