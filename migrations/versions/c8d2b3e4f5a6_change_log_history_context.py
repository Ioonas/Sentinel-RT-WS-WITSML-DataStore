"""change log history context

Revision ID: c8d2b3e4f5a6
Revises: b7c1a2d4e5f6
Create Date: 2026-11-01 00:00:00.000000

Amplía ``change_log`` con el contexto que exige ``cs_changeHistory``:
``changeInfo``, ``mnemonics``, ``startIndex`` y ``endIndex``. Estos datos
permiten reconstruir qué curvas y qué intervalo modificó cada operación.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c8d2b3e4f5a6'
down_revision: Union[str, Sequence[str], None] = 'b7c1a2d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('change_log', sa.Column('change_info', sa.Text(), nullable=True))
    op.add_column('change_log', sa.Column('mnemonics', sa.Text(), nullable=True))
    op.add_column(
        'change_log', sa.Column('start_index', sa.String(length=64), nullable=True)
    )
    op.add_column(
        'change_log', sa.Column('end_index', sa.String(length=64), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('change_log', 'end_index')
    op.drop_column('change_log', 'start_index')
    op.drop_column('change_log', 'mnemonics')
    op.drop_column('change_log', 'change_info')
