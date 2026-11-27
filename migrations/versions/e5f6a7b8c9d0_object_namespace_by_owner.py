"""Objetos WITSML con dueño: cada cuenta de servicio tiene su propio espacio de uids.

Pasa el dueño de ``witsml_object_owners`` a una columna ``owner_id`` en cada tabla de
objetos y en ``change_log``, y antepone el dueño a ``identity_key`` para que dos cuentas
puedan usar el mismo uid. Los objetos sin dueño registrado quedan con ``owner_id`` NULL:
ninguna cuenta los ve por WMLS hasta que el panel los asigne a una cuenta.

``witsml_object_owners`` se conserva sin uso como respaldo de esta migración.

Revision ID: e5f6a7b8c9d0
Revises: d6e7f8a9b0c1
Create Date: 2026-11-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: str | Sequence[str] | None = "d6e7f8a9b0c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Tabla de objetos y su tipo WITSML tal como se guarda en witsml_object_owners.
OBJECT_TABLES: dict[str, str] = {
    "wells": "well",
    "wellbores": "wellbore",
    "logs": "log",
    "mud_logs": "mudLog",
    "trajectories": "trajectory",
}


def upgrade() -> None:
    for table in (*OBJECT_TABLES, "change_log"):
        op.add_column(table, sa.Column("owner_id", sa.String(length=64), nullable=True))
        op.create_index(f"ix_{table}_owner_id", table, ["owner_id"])

    for table, object_type in OBJECT_TABLES.items():
        if object_type == "well":
            # Un pozo se guarda como su propio uid_well en witsml_object_owners.
            op.execute(
                f"""
                UPDATE {table} t SET owner_id = o.owner_id
                FROM witsml_object_owners o
                WHERE o.object_type = 'well' AND o.uid = t.uid
                """
            )
        else:
            op.execute(
                f"""
                UPDATE {table} t SET owner_id = o.owner_id
                FROM witsml_object_owners o
                WHERE o.object_type = '{object_type}'
                  AND o.uid = t.uid
                  AND o.uid_well = COALESCE(t.uid_well, '')
                  AND o.uid_wellbore = COALESCE(t.uid_wellbore, '')
                """
            )

    op.execute(
        """
        UPDATE change_log c SET owner_id = o.owner_id
        FROM witsml_object_owners o
        WHERE o.object_type = c.object_type
          AND o.uid = c.uid
          AND o.uid_well = CASE WHEN c.object_type = 'well'
                                THEN c.uid ELSE COALESCE(c.uid_well, '') END
          AND o.uid_wellbore = COALESCE(c.uid_wellbore, '')
        """
    )

    # La clave única ahora empieza por el dueño (vacío si no hay).
    for table in OBJECT_TABLES:
        op.alter_column(
            table,
            "identity_key",
            existing_type=sa.String(length=640),
            type_=sa.String(length=720),
            existing_nullable=False,
        )
        op.execute(f"UPDATE {table} SET identity_key = COALESCE(owner_id, '') || '|' || identity_key")


def downgrade() -> None:
    for table in OBJECT_TABLES:
        op.execute(
            f"""
            UPDATE {table} SET identity_key =
                substring(identity_key FROM length(COALESCE(owner_id, '')) + 2)
            """
        )
        op.alter_column(
            table,
            "identity_key",
            existing_type=sa.String(length=720),
            type_=sa.String(length=640),
            existing_nullable=False,
        )

    for table in (*OBJECT_TABLES, "change_log"):
        op.drop_index(f"ix_{table}_owner_id", table_name=table)
        op.drop_column(table, "owner_id")
