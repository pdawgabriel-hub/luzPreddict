"""ejecución única por día previsto y momento de generación

Revisión: 2d830440ab41
Anterior: bc4d53be076a
Fecha: 2026-10-06 17:03:44.441514+00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "2d830440ab41"
down_revision: str | Sequence[str] | None = "bc4d53be076a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(op.f("uq_model_run_target_day"), "model_run", ["target_day", "generated_at"])


def downgrade() -> None:
    op.drop_constraint(op.f("uq_model_run_target_day"), "model_run", type_="unique")
