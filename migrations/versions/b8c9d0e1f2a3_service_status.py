"""Estado y reinicio independiente por servicio (API y worker de correo).

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-11-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b8c9d0e1f2a3"
down_revision: str | Sequence[str] | None = "a7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "service_status",
        sa.Column("name", sa.String(length=32), primary_key=True),
        sa.Column("requested_generation", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("requested_by", sa.String(length=255), nullable=True),
        sa.Column("pid", sa.Integer(), nullable=True),
        sa.Column("state", sa.String(length=16), nullable=False, server_default="stopped"),
        sa.Column("in_flight", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
    )
    op.execute("INSERT INTO service_status (name) VALUES ('api'), ('mail-worker')")
    op.drop_column("server_config", "restart_generation")


def downgrade() -> None:
    op.add_column(
        "server_config",
        sa.Column("restart_generation", sa.Integer(), nullable=False, server_default="0"),
    )
    op.drop_table("service_status")
