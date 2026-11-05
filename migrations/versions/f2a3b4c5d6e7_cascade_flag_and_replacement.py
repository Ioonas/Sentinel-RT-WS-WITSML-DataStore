"""service account cascade flag and replacement

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-11-05 00:00:00.000000

Añade a ``service_accounts``: ``can_cascade_delete`` (fijo al crear la cuenta)
y el vínculo de reemplazo con su vencimiento (``replaced_by_id`` y
``replacement_expires_at``) para la transición entre cuentas.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f2a3b4c5d6e7'
down_revision: Union[str, Sequence[str], None] = 'e1f2a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'service_accounts',
        sa.Column('can_cascade_delete', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        'service_accounts', sa.Column('replaced_by_id', sa.String(length=64), nullable=True)
    )
    op.add_column(
        'service_accounts',
        sa.Column('replacement_expires_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('service_accounts', 'replacement_expires_at')
    op.drop_column('service_accounts', 'replaced_by_id')
    op.drop_column('service_accounts', 'can_cascade_delete')
