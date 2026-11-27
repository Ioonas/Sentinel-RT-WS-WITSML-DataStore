"""Quita los límites operativos de datos (maxDataNodes / maxDataPoints) para pruebas.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-11-27
"""

from collections.abc import Sequence

from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: str | Sequence[str] | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UNLIMITED = 2_147_483_647
PREVIOUS_NODES = 10_000
PREVIOUS_POINTS = 3_000_000


def upgrade() -> None:
    op.execute(
        f"UPDATE server_config SET max_data_nodes = {UNLIMITED}, "
        f"max_data_points = {UNLIMITED}"
    )


def downgrade() -> None:
    op.execute(
        f"UPDATE server_config SET max_data_nodes = {PREVIOUS_NODES}, "
        f"max_data_points = {PREVIOUS_POINTS}"
    )
