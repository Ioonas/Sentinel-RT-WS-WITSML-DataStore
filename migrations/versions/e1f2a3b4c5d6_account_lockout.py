"""account lockout counters

Revision ID: e1f2a3b4c5d6
Revises: d9e3c4f5a6b7
Create Date: 2026-11-05 00:00:00.000000

Añade contadores de intentos fallidos y ``locked_until`` a ``admin_users`` y
``service_accounts`` para el bloqueo temporal tras varias contraseñas
incorrectas seguidas (login administrativo y autenticación HTTP Basic WMLS).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e1f2a3b4c5d6'
down_revision: Union[str, Sequence[str], None] = 'd9e3c4f5a6b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    for table in ('admin_users', 'service_accounts'):
        op.add_column(
            table,
            sa.Column('failed_attempts', sa.Integer(), nullable=False, server_default='0'),
        )
        op.add_column(
            table,
            sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    """Downgrade schema."""
    for table in ('service_accounts', 'admin_users'):
        op.drop_column(table, 'locked_until')
        op.drop_column(table, 'failed_attempts')
