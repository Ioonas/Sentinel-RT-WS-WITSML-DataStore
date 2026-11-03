"""mud log storage

Revision ID: d9e3c4f5a6b7
Revises: c8d2b3e4f5a6
Create Date: 2026-11-03 00:00:00.000000

Crea ``mud_logs`` para el objeto WITSML ``mudLog``. El documento XML canonico
(con ``parameter`` y ``geologyInterval``) se guarda en la columna ``xml``; el
rango MD declarado por ``startMd``/``endMd`` se proyecta en columnas para las
consultas estructurales.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd9e3c4f5a6b7'
down_revision: Union[str, Sequence[str], None] = 'c8d2b3e4f5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'mud_logs',
        sa.Column('md_min', sa.Numeric(precision=38, scale=15), nullable=True),
        sa.Column('md_max', sa.Numeric(precision=38, scale=15), nullable=True),
        sa.Column('md_uom', sa.String(length=32), nullable=True),
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('uid', sa.String(length=128), nullable=False),
        sa.Column('uid_well', sa.String(length=128), nullable=True),
        sa.Column('uid_wellbore', sa.String(length=128), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=True),
        sa.Column('identity_key', sa.String(length=640), nullable=False),
        sa.Column('xml', sa.Text(), nullable=False),
        sa.Column('fields', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('d_tim_creation', sa.DateTime(timezone=True), nullable=False),
        sa.Column('d_tim_last_change', sa.DateTime(timezone=True), nullable=False),
        sa.Column('growing_until', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('identity_key'),
    )
    op.create_index(
        'ix_mud_logs_uid', 'mud_logs', ['uid'], unique=False
    )
    op.create_index(
        'ix_mud_logs_uid_well_wellbore',
        'mud_logs',
        ['uid_well', 'uid_wellbore'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_mud_logs_uid_well_wellbore', table_name='mud_logs')
    op.drop_index('ix_mud_logs_uid', table_name='mud_logs')
    op.drop_table('mud_logs')
