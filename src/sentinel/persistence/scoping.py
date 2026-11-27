"""Aislamiento de objetos WITSML por cuenta de servicio.

Cada objeto pertenece a una cuenta de servicio (``owner_id``). Una sesión ligada a una
cuenta solo lee, cambia y borra sus objetos; los demás son invisibles, como si no
existieran. La restricción se aplica aquí, en un solo punto, para que ninguna consulta
pueda olvidarla.

Una sesión sin cuenta ligada (panel administrativo) ve todos los objetos, con su dueño.
Escribir objetos sin cuenta ligada está prohibido.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import event
from sqlalchemy.orm import Session, with_loader_criteria

from sentinel.persistence.tables import (
    ChangeLogRow,
    LogRow,
    MudLogRow,
    TrajectoryRow,
    WellboreRow,
    WellRow,
)

OWNER_SCOPE_KEY = "witsml_owner_scope"

# Tipo WITSML de cada tabla de objetos.
OBJECT_TYPES: dict[type, str] = {
    WellRow: "well",
    WellboreRow: "wellbore",
    LogRow: "log",
    MudLogRow: "mudLog",
    TrajectoryRow: "trajectory",
}
SCOPED_MODELS: tuple[type, ...] = (*OBJECT_TYPES, ChangeLogRow)


def identity_key(
    owner_id: str | None,
    object_type: str,
    uid: str,
    uid_well: str | None,
    uid_wellbore: str | None,
) -> str:
    """Clave única por dueño, tipo y uid. Sin dueño, el prefijo queda vacío."""
    return f"{owner_id or ''}|{object_type}|{uid_well or ''}|{uid_wellbore or ''}|{uid}"


def _row_identity(row: Any) -> str:
    object_type = OBJECT_TYPES[type(row)]
    # Un pozo se identifica por sí mismo; su uid_well es su propio uid.
    uid_well = row.uid if object_type == "well" else row.uid_well
    return identity_key(row.owner_id, object_type, row.uid, uid_well, row.uid_wellbore)


@event.listens_for(Session, "do_orm_execute")
def _filter_by_owner(state: Any) -> None:
    scope = state.session.info.get(OWNER_SCOPE_KEY)
    if scope is None or not (state.is_select or state.is_update or state.is_delete):
        return
    state.statement = state.statement.options(
        *(
            with_loader_criteria(
                model,
                lambda cls: cls.owner_id == scope,
                include_aliases=True,
            )
            for model in SCOPED_MODELS
        )
    )


@event.listens_for(Session, "before_flush")
def _assign_owner(session: Session, flush_context: Any, instances: Any) -> None:
    scope = session.info.get(OWNER_SCOPE_KEY)
    for obj in session.new:
        if type(obj) in OBJECT_TYPES:
            if scope is None:
                raise RuntimeError("Escritura WITSML sin cuenta de servicio ligada.")
            obj.owner_id = scope
            obj.identity_key = _row_identity(obj)
        elif isinstance(obj, ChangeLogRow) and obj.owner_id is None:
            obj.owner_id = scope
    for obj in session.dirty:
        if type(obj) in OBJECT_TYPES:
            obj.identity_key = _row_identity(obj)
