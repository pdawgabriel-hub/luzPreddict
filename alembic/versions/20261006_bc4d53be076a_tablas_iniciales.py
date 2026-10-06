"""tablas iniciales

Revisión: bc4d53be076a
Anterior:
Fecha: 2026-10-06 17:01:03.251861+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "bc4d53be076a"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "daily_error",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("model", sa.String(length=32), nullable=False),
        sa.Column("mae", sa.Float(), nullable=False),
        sa.Column("rmse", sa.Float(), nullable=False),
        sa.Column("bias", sa.Float(), nullable=False),
        sa.Column("n", sa.Integer(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("day", "model", name=op.f("pk_daily_error")),
    )
    op.create_table(
        "generation_day",
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("technology", sa.String(length=64), nullable=False),
        sa.Column("mwh", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("date", "technology", name=op.f("pk_generation_day")),
    )
    op.create_table(
        "model_artifact",
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("trained_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("train_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("train_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("training_rows", sa.Integer(), nullable=False),
        sa.Column("features", sa.JSON(), nullable=False),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("library_versions", sa.JSON(), nullable=False),
        sa.Column("format_version", sa.Integer(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.PrimaryKeyConstraint("version", name=op.f("pk_model_artifact")),
    )
    op.create_index(op.f("ix_model_artifact_trained_at"), "model_artifact", ["trained_at"], unique=False)
    op.create_table(
        "price_hour",
        sa.Column("datetime", sa.DateTime(timezone=True), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("datetime", name=op.f("pk_price_hour")),
    )
    op.create_table(
        "model_run",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("target_day", sa.Date(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("model", sa.String(length=32), nullable=False),
        sa.Column("model_version", sa.String(length=32), nullable=True),
        sa.Column("fallback_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["model_version"],
            ["model_artifact.version"],
            name=op.f("fk_model_run_model_version_model_artifact"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_model_run")),
    )
    op.create_index(op.f("ix_model_run_target_day"), "model_run", ["target_day"], unique=False)
    op.create_table(
        "forecast_hour",
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("datetime", sa.DateTime(timezone=True), nullable=False),
        sa.Column("prediction", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"], ["model_run.id"], name=op.f("fk_forecast_hour_run_id_model_run"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("run_id", "datetime", name=op.f("pk_forecast_hour")),
    )


def downgrade() -> None:
    op.drop_table("forecast_hour")
    op.drop_index(op.f("ix_model_run_target_day"), table_name="model_run")
    op.drop_table("model_run")
    op.drop_table("price_hour")
    op.drop_index(op.f("ix_model_artifact_trained_at"), table_name="model_artifact")
    op.drop_table("model_artifact")
    op.drop_table("generation_day")
    op.drop_table("daily_error")
