"""change log contextual names

Revision ID: b7c1a2d4e5f6
Revises: fd267c00c5fd
Create Date: 2026-10-31 00:00:00.000000

Añade los nombres contextuales exigidos por ``obj_changeLog.xsd`` para poder
serializar ``changeLog`` en el formato oficial incluso después de que el objeto
cambiado se haya eliminado.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b7c1a2d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'fd267c00c5fd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'change_log', sa.Column('name_object', sa.String(length=255), nullable=True)
    )
    op.add_column(
        'change_log', sa.Column('name_well', sa.String(length=255), nullable=True)
    )
    op.add_column(
        'change_log', sa.Column('name_wellbore', sa.String(length=255), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('change_log', 'name_wellbore')
    op.drop_column('change_log', 'name_well')
    op.drop_column('change_log', 'name_object')
