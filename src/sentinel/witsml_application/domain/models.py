"""Modelos de dominio del Store WITSML.

Son estructuras independientes de SQLAlchemy y de HTTP. La persistencia las
convierte desde/hacia sus tablas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any


@dataclass
class StoredObject:
    uid: str
    uid_well: str | None
    uid_wellbore: str | None
    name: str | None
    xml: str
    fields: dict[str, Any]
    created_at: datetime
    changed_at: datetime
    growing_until: datetime | None = None
    db_id: int | None = None

    @property
    def growing(self) -> bool:
        return self.growing_until is not None


@dataclass
class WellRecord(StoredObject):
    object_type: str = "well"


@dataclass
class WellboreRecord(StoredObject):
    object_type: str = "wellbore"


@dataclass
class LogCurve:
    mnemonic: str
    unit: str | None
    curve_type: str | None
    is_index: bool
    description: str | None = None
    uid: str | None = None
    ordering: int = 0


@dataclass
class LogRecord(StoredObject):
    index_type: str = "time"
    index_curve: str = "index"
    direction: str = "increasing"
    start_index_time: datetime | None = None
    start_index_value: Decimal | None = None
    end_index_time: datetime | None = None
    end_index_value: Decimal | None = None
    index_uom: str | None = None
    curves: list[LogCurve] = field(default_factory=list)
    object_type: str = "log"

    @property
    def start_index(self) -> datetime | Decimal | None:
        return self.start_index_time if self.index_type == "time" else self.start_index_value

    @property
    def end_index(self) -> datetime | Decimal | None:
        return self.end_index_time if self.index_type == "time" else self.end_index_value


@dataclass
class LogSample:
    order: int
    index_time: datetime | None
    index_value: Decimal | None
    values: dict[str, str | None]


@dataclass
class TrajectoryRecord(StoredObject):
    md_min: Decimal | None = None
    md_max: Decimal | None = None
    md_uom: str | None = None
    object_type: str = "trajectory"


@dataclass
class TrajectoryStation:
    order: int
    md: Decimal | None
    incl: Decimal | None
    azi: Decimal | None
    tvd: Decimal | None
    xml: str


@dataclass
class MudLogRecord(StoredObject):
    """Mud log completo.

    ``mudLog`` es un objeto de crecimiento aleatorio: los nodos de datos
    (``parameter`` y ``geologyInterval``) viven dentro del XML canónico, por lo
    que no requieren una tabla hija. El rango MD se guarda para las consultas
    estructurales.
    """

    md_min: Decimal | None = None
    md_max: Decimal | None = None
    md_uom: str | None = None
    object_type: str = "mudLog"


@dataclass(frozen=True)
class ChangeLogRecord:
    uid: str
    object_type: str
    change_type: str
    change_date: datetime
    uid_well: str | None = None
    uid_wellbore: str | None = None
    name_object: str | None = None
    name_well: str | None = None
    name_wellbore: str | None = None
    #: Contexto detallado del cambio (``cs_changeHistory``).
    change_info: str | None = None
    mnemonics: str | None = None
    start_index: str | None = None
    end_index: str | None = None
