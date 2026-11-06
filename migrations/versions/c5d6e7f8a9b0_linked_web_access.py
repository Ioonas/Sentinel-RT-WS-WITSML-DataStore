"""Acceso web vinculado a cuentas de servicio.

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-11-05
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c5d6e7f8a9b0"
down_revision: Union[str, Sequence[str], None] = "b4c5d6e7f8a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "admin_users",
        sa.Column("linked_service_account_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "invitations",
        sa.Column("linked_service_account_id", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("invitations", "linked_service_account_id")
    op.drop_column("admin_users", "linked_service_account_id")
