"""Separa la API en dos servicios: WITSML y administrativa.

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-11-27
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c9d0e1f2a3b4"
down_revision: str | Sequence[str] | None = "b8c9d0e1f2a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "INSERT INTO service_status (name) VALUES ('witsml'), ('admin') "
        "ON CONFLICT (name) DO NOTHING"
    )
    op.execute("DELETE FROM service_status WHERE name = 'api'")


def downgrade() -> None:
    op.execute("INSERT INTO service_status (name) VALUES ('api') ON CONFLICT (name) DO NOTHING")
    op.execute("DELETE FROM service_status WHERE name IN ('witsml', 'admin')")
