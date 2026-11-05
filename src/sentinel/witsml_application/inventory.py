"""Inventario administrativo de objetos WITSML (solo metadatos)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sentinel.shared.errors import NotFoundError
from sentinel.witsml_application.domain.codes import WmlsCode
from sentinel.witsml_application.domain.errors import WitsmlError
from sentinel.witsml_application.domain.models import ChangeLogRecord, StoredObject
from sentinel.witsml_application.ports import (
    ChangeLogRepositoryPort,
    ListFilter,
    LogRepositoryPort,
    MudLogRepositoryPort,
    TrajectoryRepositoryPort,
    WellboreRepositoryPort,
    WellRepositoryPort,
)
from sentinel.xml_schema import documents as xd
from sentinel.xml_schema.objects import SUPPORTED_TYPES, spec_for
from sentinel.xml_schema.parser import parse_xml


@dataclass(frozen=True)
class ObjectSummary:
    object_type: str
    uid: str
    uid_well: str | None
    uid_wellbore: str | None
    name: str | None
    created_at: datetime
    changed_at: datetime
    growing: bool


class InventoryService:
    def __init__(
        self,
        *,
        wells: WellRepositoryPort,
        wellbores: WellboreRepositoryPort,
        logs: LogRepositoryPort,
        mud_logs: MudLogRepositoryPort,
        trajectories: TrajectoryRepositoryPort,
        change_log: ChangeLogRepositoryPort,
    ) -> None:
        self._wells = wells
        self._wellbores = wellbores
        self._logs = logs
        self._mud_logs = mud_logs
        self._trajectories = trajectories
        self._change_log = change_log

    async def search(
        self,
        object_type: str,
        *,
        uid_well: str | None = None,
        uid_wellbore: str | None = None,
        name: str | None = None,
        allowed_wells: frozenset[str] | None = None,
        limit: int = 200,
    ) -> list[ObjectSummary]:
        if object_type not in SUPPORTED_TYPES:
            raise NotFoundError("Tipo de objeto no soportado.")
        repo = self._repository(object_type)
        records = await repo.list(
            ListFilter(
                uid_well=uid_well,
                uid_wellbore=uid_wellbore,
                name=name,
                allowed_wells=allowed_wells,
                limit=limit,
            )
        )
        return [self._summary(object_type, record) for record in records]

    async def get(
        self,
        object_type: str,
        uid: str,
        *,
        uid_well: str | None = None,
        uid_wellbore: str | None = None,
    ) -> ObjectSummary:
        record = await self._get(object_type, uid, uid_well, uid_wellbore)
        if record is None:
            raise NotFoundError("Objeto no encontrado.")
        return self._summary(object_type, record)

    async def dependencies(
        self,
        object_type: str,
        uid: str,
        *,
        uid_well: str | None = None,
        uid_wellbore: str | None = None,
    ) -> list[str]:
        record = await self._get(object_type, uid, uid_well, uid_wellbore)
        if record is None:
            raise NotFoundError("Objeto no encontrado.")
        if object_type == "well":
            children = await self._wellbores.list(ListFilter(uid_well=uid))
            return [f"wellbore:{child.uid}" for child in children]
        if object_type == "wellbore":
            result = [
                f"log:{child.uid}"
                for child in await self._logs.list(
                    ListFilter(uid_well=uid_well, uid_wellbore=uid)
                )
            ]
            result += [
                f"trajectory:{child.uid}"
                for child in await self._trajectories.list(
                    ListFilter(uid_well=uid_well, uid_wellbore=uid)
                )
            ]
            result += [
                f"mudLog:{child.uid}"
                for child in await self._mud_logs.list(
                    ListFilter(uid_well=uid_well, uid_wellbore=uid)
                )
            ]
            return result
        return []

    async def delete(
        self,
        object_type: str,
        uid: str,
        *,
        uid_well: str | None = None,
        uid_wellbore: str | None = None,
        actor: str = "admin",
    ) -> None:
        record = await self._get(object_type, uid, uid_well, uid_wellbore)
        if record is None:
            raise NotFoundError("Objeto no encontrado.")
        if await self.dependencies(
            object_type, uid, uid_well=uid_well, uid_wellbore=uid_wellbore
        ):
            raise WitsmlError(WmlsCode.NOT_BOTTOM_LEVEL)
        element = parse_xml(record.xml)
        xd.ensure_namespace(element)
        if object_type == "well":
            await self._wells.delete(uid)
        elif object_type == "wellbore":
            await self._wellbores.delete(uid, uid_well)
        elif object_type == "log":
            await self._logs.delete(uid, uid_well, uid_wellbore)
        elif object_type == "mudLog":
            await self._mud_logs.delete(uid, uid_well, uid_wellbore)
        else:
            await self._trajectories.delete(uid, uid_well, uid_wellbore)
        await self._change_log.add(
            ChangeLogRecord(
                uid=uid,
                object_type=object_type,
                change_type="delete",
                change_date=record.changed_at,
                uid_well=record.uid_well,
                uid_wellbore=record.uid_wellbore,
                name_object=xd.text_of(element, "name"),
                name_well=xd.text_of(element, "nameWell"),
                name_wellbore=xd.text_of(element, "nameWellbore"),
            )
        )

    async def unknown_wells(self, uids: list[str]) -> list[str]:
        """Devuelve los uid de pozo que no existen en el inventario, sin repetir."""
        missing: list[str] = []
        for uid in dict.fromkeys(uids):
            if await self._wells.get(uid) is None:
                missing.append(uid)
        return missing

    def _repository(self, object_type: str):
        spec_for(object_type)
        return {
            "well": self._wells,
            "wellbore": self._wellbores,
            "log": self._logs,
            "mudLog": self._mud_logs,
            "trajectory": self._trajectories,
        }[object_type]

    async def _get(
        self,
        object_type: str,
        uid: str,
        uid_well: str | None,
        uid_wellbore: str | None,
    ) -> StoredObject | None:
        if object_type == "well":
            return await self._wells.get(uid)
        if object_type == "wellbore":
            return await self._wellbores.get(uid, uid_well)
        if object_type == "log":
            return await self._logs.get(uid, uid_well, uid_wellbore)
        if object_type == "mudLog":
            return await self._mud_logs.get(uid, uid_well, uid_wellbore)
        if object_type == "trajectory":
            return await self._trajectories.get(uid, uid_well, uid_wellbore)
        raise NotFoundError("Tipo de objeto no soportado.")

    @staticmethod
    def _summary(object_type: str, record: StoredObject) -> ObjectSummary:
        return ObjectSummary(
            object_type=object_type,
            uid=record.uid,
            uid_well=record.uid_well,
            uid_wellbore=record.uid_wellbore,
            name=record.name,
            created_at=record.created_at,
            changed_at=record.changed_at,
            growing=record.growing,
        )
