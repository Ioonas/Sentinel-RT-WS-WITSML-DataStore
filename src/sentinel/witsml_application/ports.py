"""Puertos del núcleo WITSML.

Los adaptadores de salida implementan estos protocolos. El servicio recibe las
implementaciones ya ligadas a la transacción de la solicitud.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from sentinel.witsml_application.domain.models import (
    ChangeLogRecord,
    LogCurve,
    LogRecord,
    LogSample,
    TrajectoryRecord,
    TrajectoryStation,
    WellboreRecord,
    WellRecord,
)


@dataclass(frozen=True)
class StoreResult:
    code: int
    xml_out: str | None = None
    supp_msg: str | None = None
    message: str | None = None


@dataclass(frozen=True)
class ListFilter:
    uid: str | None = None
    uid_well: str | None = None
    uid_wellbore: str | None = None
    name: str | None = None
    text_filters: dict[str, str] = field(default_factory=dict)
    allowed_wells: frozenset[str] | None = None
    limit: int | None = None
    created_after: datetime | None = None
    changed_after: datetime | None = None


class WellRepositoryPort(Protocol):
    async def get(self, uid: str, uid_well: str | None = None) -> WellRecord | None: ...

    async def list(self, filters: ListFilter) -> list[WellRecord]: ...

    async def add(self, record: WellRecord) -> None: ...

    async def update(self, record: WellRecord) -> None: ...

    async def delete(self, uid: str) -> None: ...

    async def has_children(self, uid: str) -> bool: ...


class WellboreRepositoryPort(Protocol):
    async def get(
        self, uid: str, uid_well: str | None = None
    ) -> WellboreRecord | None: ...

    async def list(self, filters: ListFilter) -> list[WellboreRecord]: ...

    async def add(self, record: WellboreRecord) -> None: ...

    async def update(self, record: WellboreRecord) -> None: ...

    async def delete(self, uid: str, uid_well: str | None = None) -> None: ...

    async def has_children(self, uid: str, uid_well: str | None = None) -> bool: ...


class LogRepositoryPort(Protocol):
    async def get(
        self, uid: str, uid_well: str | None = None, uid_wellbore: str | None = None
    ) -> LogRecord | None: ...

    async def list(self, filters: ListFilter) -> list[LogRecord]: ...

    async def add(self, record: LogRecord) -> None: ...

    async def update(self, record: LogRecord) -> None: ...

    async def delete(
        self, uid: str, uid_well: str | None = None, uid_wellbore: str | None = None
    ) -> None: ...

    async def list_samples(
        self,
        log_uid: str,
        *,
        start: datetime | Decimal | None = None,
        end: datetime | Decimal | None = None,
        latest: int | None = None,
        limit: int | None = None,
    ) -> list[LogSample]: ...

    async def count_samples(
        self,
        log_uid: str,
        *,
        start: datetime | Decimal | None = None,
        end: datetime | Decimal | None = None,
    ) -> int: ...

    async def sample_range(
        self, log_uid: str
    ) -> tuple[datetime | Decimal | None, datetime | Decimal | None]: ...

    async def delete_samples(
        self,
        log_uid: str,
        *,
        start: datetime | Decimal | None = None,
        end: datetime | Decimal | None = None,
    ) -> int: ...

    async def remove_curve_values(
        self,
        log_uid: str,
        mnemonic: str,
        *,
        start: datetime | Decimal | None = None,
        end: datetime | Decimal | None = None,
    ) -> int: ...

    async def upsert_samples(
        self, log_uid: str, samples: list[LogSample], index_type: str
    ) -> tuple[int, int]:
        """Devuelve ``(insertadas, actualizadas)``."""

    async def replace_curves(self, log_uid: str, curves: list[LogCurve]) -> None: ...


class TrajectoryRepositoryPort(Protocol):
    async def get(
        self, uid: str, uid_well: str | None = None, uid_wellbore: str | None = None
    ) -> TrajectoryRecord | None: ...

    async def list(self, filters: ListFilter) -> list[TrajectoryRecord]: ...

    async def add(self, record: TrajectoryRecord) -> None: ...

    async def update(self, record: TrajectoryRecord) -> None: ...

    async def delete(
        self, uid: str, uid_well: str | None = None, uid_wellbore: str | None = None
    ) -> None: ...

    async def list_stations(
        self,
        trajectory_uid: str,
        *,
        md_min: Decimal | None = None,
        md_max: Decimal | None = None,
    ) -> list[TrajectoryStation]: ...

    async def replace_stations(
        self, trajectory_uid: str, stations: list[TrajectoryStation]
    ) -> None: ...


class ChangeLogRepositoryPort(Protocol):
    async def add(self, record: ChangeLogRecord) -> None: ...

    async def search(
        self,
        *,
        object_type: str | None = None,
        uid: str | None = None,
        uid_well: str | None = None,
        uid_wellbore: str | None = None,
        change_type: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        allowed_wells: frozenset[str] | None = None,
        limit: int = 1000,
    ) -> list[ChangeLogRecord]: ...


class SchemaValidatorPort(Protocol):
    @property
    def available(self) -> bool: ...

    def validate_document(
        self, object_type: str, document: object, *, operation: str = "write"
    ) -> None: ...
