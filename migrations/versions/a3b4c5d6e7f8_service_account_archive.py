"""service account archive

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-11-05 18:30:00.000000

Añade ``archived_at`` a ``service_accounts``. Una cuenta archivada deja de
aparecer en la lista activa y no puede autenticarse, pero su registro y su
auditoría se conservan.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a3b4c5d6e7f8'
down_revision: Union[str, Sequence[str], None] = 'f2a3b4c5d6e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'service_accounts',
        sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('service_accounts', 'archived_at')
