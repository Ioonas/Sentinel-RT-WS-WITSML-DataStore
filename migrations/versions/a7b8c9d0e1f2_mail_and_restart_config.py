"""Configuración de correo editable y contador de reinicio de servicios.

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-11-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a7b8c9d0e1f2"
down_revision: str | Sequence[str] | None = "f6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Remitente vacío: el worker usa SENTINEL_SMTP_FROM.
    op.add_column(
        "server_config",
        sa.Column("mail_from", sa.String(length=255), nullable=False, server_default=""),
    )
    op.add_column(
        "server_config",
        sa.Column("mail_max_attempts", sa.Integer(), nullable=False, server_default="5"),
    )
    op.add_column(
        "server_config",
        sa.Column("mail_backoff_base_seconds", sa.Integer(), nullable=False, server_default="30"),
    )
    op.add_column(
        "server_config",
        sa.Column("restart_generation", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    for column in (
        "restart_generation",
        "mail_backoff_base_seconds",
        "mail_max_attempts",
        "mail_from",
    ):
        op.drop_column("server_config", column)
