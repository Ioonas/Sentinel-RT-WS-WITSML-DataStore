"""Creador de cada objeto WITSML, para alcance por propiedad.

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-11-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d6e7f8a9b0c1"
down_revision: str | Sequence[str] | None = "c5d6e7f8a9b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "witsml_object_owners",
        sa.Column("object_type", sa.String(length=16), nullable=False),
        sa.Column("uid", sa.String(length=128), nullable=False),
        sa.Column("uid_well", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("uid_wellbore", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("owner_id", sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint("object_type", "uid", "uid_well", "uid_wellbore"),
    )
    op.create_index(
        "ix_witsml_object_owners_owner", "witsml_object_owners", ["owner_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_witsml_object_owners_owner", table_name="witsml_object_owners")
    op.drop_table("witsml_object_owners")
