"""Implementaciones SQLAlchemy de los puertos de persistencia."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from sentinel.audit_config.domain import (
    AuditChannel,
    AuditEvent,
    AuditResult,
    MailJob,
    ServerConfig,
)
from sentinel.identity_access.domain import Grant, HumanRole, ServiceRole, WitsmlAction
from sentinel.identity_access.ports import (
    AdminUserRecord,
    InvitationRecord,
    PasswordResetRecord,
    ServiceAccountRecord,
    SessionRecord,
)
from sentinel.persistence.tables import (
    AdminSessionRow,
    AdminUserRow,
    AuditEventRow,
    ChangeLogRow,
    InvitationRow,
    LogCurveRow,
    LogRow,
    LogSampleRow,
    MailOutboxRow,
    MudLogRow,
    PasswordResetRow,
    ServerConfigRow,
    ServiceAccountRow,
    TrajectoryRow,
    TrajectoryStationRow,
    WellboreRow,
    WellRow,
)
from sentinel.witsml_application.domain.models import (
    ChangeLogRecord,
    LogCurve,
    LogRecord,
    LogSample,
    MudLogRecord,
    TrajectoryRecord,
    TrajectoryStation,
    WellboreRecord,
    WellRecord,
)
from sentinel.witsml_application.ports import ListFilter


def identity_key(
    object_type: str,
    uid: str,
    uid_well: str | None = None,
    uid_wellbore: str | None = None,
) -> str:
    return f"{object_type}|{uid_well or ''}|{uid_wellbore or ''}|{uid}"


def _apply_common(row: Any, record: Any) -> None:
    row.uid = record.uid
    row.uid_well = record.uid_well
    row.uid_wellbore = record.uid_wellbore
    row.name = record.name
    row.xml = record.xml
    row.fields = record.fields
    row.d_tim_creation = record.created_at
    row.d_tim_last_change = record.changed_at
    row.growing_until = record.growing_until


def _to_well(row: WellRow) -> WellRecord:
    return WellRecord(
        uid=row.uid,
        uid_well=row.uid_well,
        uid_wellbore=row.uid_wellbore,
        name=row.name,
        xml=row.xml,
        fields=row.fields or {},
        created_at=row.d_tim_creation,
        changed_at=row.d_tim_last_change,
        growing_until=row.growing_until,
        db_id=row.id,
    )


def _to_wellbore(row: WellboreRow) -> WellboreRecord:
    return WellboreRecord(
        uid=row.uid,
        uid_well=row.uid_well,
        uid_wellbore=row.uid_wellbore,
        name=row.name,
        xml=row.xml,
        fields=row.fields or {},
        created_at=row.d_tim_creation,
        changed_at=row.d_tim_last_change,
        growing_until=row.growing_until,
        db_id=row.id,
    )


def _to_log(row: LogRow) -> LogRecord:
    return LogRecord(
        uid=row.uid,
        uid_well=row.uid_well,
        uid_wellbore=row.uid_wellbore,
        name=row.name,
        xml=row.xml,
        fields=row.fields or {},
        created_at=row.d_tim_creation,
        changed_at=row.d_tim_last_change,
        growing_until=row.growing_until,
        db_id=row.id,
        index_type=row.index_type,
        index_curve=row.index_curve,
        direction=row.direction,
        start_index_time=row.start_index_time,
        start_index_value=row.start_index_value,
        end_index_time=row.end_index_time,
        end_index_value=row.end_index_value,
        index_uom=row.index_uom,
        curves=[
            LogCurve(
                mnemonic=curve.mnemonic,
                unit=curve.unit,
                curve_type=curve.curve_type,
                is_index=curve.is_index,
                description=curve.description,
                uid=curve.curve_uid,
                ordering=curve.ordering,
            )
            for curve in row.curves
        ],
    )


def _to_trajectory(row: TrajectoryRow) -> TrajectoryRecord:
    return TrajectoryRecord(
        uid=row.uid,
        uid_well=row.uid_well,
        uid_wellbore=row.uid_wellbore,
        name=row.name,
        xml=row.xml,
        fields=row.fields or {},
        created_at=row.d_tim_creation,
        changed_at=row.d_tim_last_change,
        growing_until=row.growing_until,
        db_id=row.id,
        md_min=row.md_min,
        md_max=row.md_max,
        md_uom=row.md_uom,
    )


def _to_mudlog(row: MudLogRow) -> MudLogRecord:
    return MudLogRecord(
        uid=row.uid,
        uid_well=row.uid_well,
        uid_wellbore=row.uid_wellbore,
        name=row.name,
        xml=row.xml,
        fields=row.fields or {},
        created_at=row.d_tim_creation,
        changed_at=row.d_tim_last_change,
        growing_until=row.growing_until,
        db_id=row.id,
        md_min=row.md_min,
        md_max=row.md_max,
        md_uom=row.md_uom,
    )


def _apply_text_filters(stmt: Any, model: Any, filters: ListFilter) -> Any:
    if filters.uid:
        stmt = stmt.where(func.lower(model.uid) == filters.uid.lower())
    if filters.uid_well:
        stmt = stmt.where(func.lower(model.uid_well) == filters.uid_well.lower())
    if filters.uid_wellbore:
        stmt = stmt.where(
            func.lower(model.uid_wellbore) == filters.uid_wellbore.lower()
        )
    if filters.name:
        stmt = stmt.where(func.lower(model.name) == filters.name.lower())
    for key, value in filters.text_filters.items():
        if key == "name":
            continue
        stmt = stmt.where(func.lower(model.fields[key].astext) == value.lower())
    if filters.created_after is not None:
        stmt = stmt.where(model.d_tim_creation > filters.created_after)
    if filters.changed_after is not None:
        stmt = stmt.where(model.d_tim_last_change > filters.changed_after)
    if filters.allowed_wells is not None:
        if model is WellRow:
            stmt = stmt.where(
                func.lower(model.uid).in_(
                    {value.lower() for value in filters.allowed_wells}
                )
            )
        else:
            stmt = stmt.where(
                func.lower(model.uid_well).in_(
                    {value.lower() for value in filters.allowed_wells}
                )
            )
    return stmt


class SqlAlchemyWellRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(
        self, uid: str, uid_well: str | None = None, *, for_update: bool = False
    ) -> WellRecord | None:
        stmt = select(WellRow).where(func.lower(WellRow.uid) == uid.lower())
        if for_update:
            stmt = stmt.with_for_update()
        row = await self._session.scalar(stmt)
        return _to_well(row) if row else None

    async def list(self, filters: ListFilter) -> list[WellRecord]:
        stmt = _apply_text_filters(select(WellRow), WellRow, filters)
        stmt = stmt.order_by(WellRow.id)
        if filters.limit:
            stmt = stmt.limit(filters.limit)
        rows = (await self._session.scalars(stmt)).all()
        return [_to_well(row) for row in rows]

    async def add(self, record: WellRecord) -> None:
        row = WellRow(identity_key=identity_key("well", record.uid, record.uid, None))
        _apply_common(row, record)
        self._session.add(row)
        await self._session.flush()

    async def update(self, record: WellRecord) -> None:
        row = await self._session.get(WellRow, record.db_id)
        if row is None:
            raise LookupError("well no encontrado para actualizar")
        _apply_common(row, record)

    async def delete(self, uid: str) -> None:
        await self._session.execute(
            delete(WellRow).where(func.lower(WellRow.uid) == uid.lower())
        )

    async def has_children(self, uid: str) -> bool:
        exists = await self._session.scalar(
            select(WellboreRow.id)
            .where(func.lower(WellboreRow.uid_well) == uid.lower())
            .limit(1)
        )
        return exists is not None


class SqlAlchemyWellboreRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(
        self, uid: str, uid_well: str | None = None, *, for_update: bool = False
    ) -> WellboreRecord | None:
        stmt = select(WellboreRow).where(func.lower(WellboreRow.uid) == uid.lower())
        if uid_well:
            stmt = stmt.where(func.lower(WellboreRow.uid_well) == uid_well.lower())
        if for_update:
            stmt = stmt.with_for_update()
        row = await self._session.scalar(stmt)
        return _to_wellbore(row) if row else None

    async def list(self, filters: ListFilter) -> list[WellboreRecord]:
        stmt = _apply_text_filters(select(WellboreRow), WellboreRow, filters)
        stmt = stmt.order_by(WellboreRow.id)
        if filters.limit:
            stmt = stmt.limit(filters.limit)
        rows = (await self._session.scalars(stmt)).all()
        return [_to_wellbore(row) for row in rows]

    async def add(self, record: WellboreRecord) -> None:
        row = WellboreRow(
            identity_key=identity_key(
                "wellbore", record.uid, record.uid_well, record.uid_wellbore
            )
        )
        _apply_common(row, record)
        self._session.add(row)
        await self._session.flush()

    async def update(self, record: WellboreRecord) -> None:
        row = await self._session.get(WellboreRow, record.db_id)
        if row is None:
            raise LookupError("wellbore no encontrado para actualizar")
        _apply_common(row, record)

    async def delete(self, uid: str, uid_well: str | None = None) -> None:
        stmt = delete(WellboreRow).where(func.lower(WellboreRow.uid) == uid.lower())
        if uid_well:
            stmt = stmt.where(func.lower(WellboreRow.uid_well) == uid_well.lower())
        await self._session.execute(stmt)

    async def has_children(self, uid: str, uid_well: str | None = None) -> bool:
        for model in (LogRow, TrajectoryRow, MudLogRow):
            stmt = select(model.id).where(
                func.lower(model.uid_wellbore) == uid.lower()
            )
            if uid_well:
                stmt = stmt.where(func.lower(model.uid_well) == uid_well.lower())
            if await self._session.scalar(stmt.limit(1)) is not None:
                return True
        return False


class SqlAlchemyLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(
        self,
        uid: str,
        uid_well: str | None = None,
        uid_wellbore: str | None = None,
        *,
        for_update: bool = False,
    ) -> LogRecord | None:
        stmt = (
            select(LogRow)
            .options(selectinload(LogRow.curves))
            .where(func.lower(LogRow.uid) == uid.lower())
        )
        if uid_well:
            stmt = stmt.where(func.lower(LogRow.uid_well) == uid_well.lower())
        if uid_wellbore:
            stmt = stmt.where(func.lower(LogRow.uid_wellbore) == uid_wellbore.lower())
        if for_update:
            stmt = stmt.with_for_update()
        row = await self._session.scalar(stmt)
        return _to_log(row) if row else None

    async def list(self, filters: ListFilter) -> list[LogRecord]:
        stmt = (
            select(LogRow)
            .options(selectinload(LogRow.curves))
            .where(True)
        )
        stmt = _apply_text_filters(stmt, LogRow, filters)
        stmt = stmt.order_by(LogRow.id)
        if filters.limit:
            stmt = stmt.limit(filters.limit)
        rows = (await self._session.scalars(stmt)).all()
        return [_to_log(row) for row in rows]

    async def add(self, record: LogRecord) -> None:
        row = LogRow(
            identity_key=identity_key(
                "log", record.uid, record.uid_well, record.uid_wellbore
            ),
            index_type=record.index_type,
            index_curve=record.index_curve,
            direction=record.direction,
            start_index_time=record.start_index_time,
            start_index_value=record.start_index_value,
            end_index_time=record.end_index_time,
            end_index_value=record.end_index_value,
            index_uom=record.index_uom,
        )
        _apply_common(row, record)
        self._session.add(row)
        await self._session.flush()
        record.db_id = row.id
        await self._insert_curves(row.id, record.curves)

    async def update(self, record: LogRecord) -> None:
        row = await self._session.get(LogRow, record.db_id)
        if row is None:
            raise LookupError("log no encontrado para actualizar")
        _apply_common(row, record)
        row.index_type = record.index_type
        row.index_curve = record.index_curve
        row.direction = record.direction
        row.start_index_time = record.start_index_time
        row.start_index_value = record.start_index_value
        row.end_index_time = record.end_index_time
        row.end_index_value = record.end_index_value
        row.index_uom = record.index_uom

    async def delete(
        self, uid: str, uid_well: str | None = None, uid_wellbore: str | None = None
    ) -> None:
        stmt = select(LogRow.id).where(func.lower(LogRow.uid) == uid.lower())
        if uid_well:
            stmt = stmt.where(func.lower(LogRow.uid_well) == uid_well.lower())
        if uid_wellbore:
            stmt = stmt.where(func.lower(LogRow.uid_wellbore) == uid_wellbore.lower())
        log_id = await self._session.scalar(stmt)
        if log_id is None:
            return
        await self._session.execute(delete(LogSampleRow).where(LogSampleRow.log_id == log_id))
        await self._session.execute(delete(LogCurveRow).where(LogCurveRow.log_id == log_id))
        await self._session.execute(delete(LogRow).where(LogRow.id == log_id))

    async def _log_id(self, log_uid: str) -> int | None:
        return await self._session.scalar(
            select(LogRow.id).where(func.lower(LogRow.uid) == log_uid.lower())
        )

    def _range_conditions(
        self,
        stmt: Any,
        start: datetime | Decimal | None,
        end: datetime | Decimal | None,
    ) -> Any:
        if start is None and end is None:
            return stmt
        if isinstance(start, datetime) or isinstance(end, datetime):
            lo, hi = self._ordered(start, end)
            if lo is not None:
                stmt = stmt.where(LogSampleRow.index_time >= lo)
            if hi is not None:
                stmt = stmt.where(LogSampleRow.index_time <= hi)
        else:
            lo, hi = self._ordered(start, end)
            if lo is not None:
                stmt = stmt.where(LogSampleRow.index_value >= lo)
            if hi is not None:
                stmt = stmt.where(LogSampleRow.index_value <= hi)
        return stmt

    async def list_samples(
        self,
        log_uid: str,
        *,
        start: datetime | Decimal | None = None,
        end: datetime | Decimal | None = None,
        latest: int | None = None,
        limit: int | None = None,
    ) -> list[LogSample]:
        log_id = await self._log_id(log_uid)
        if log_id is None:
            return []
        stmt = select(LogSampleRow).where(LogSampleRow.log_id == log_id)
        if latest is not None:
            stmt = stmt.order_by(LogSampleRow.sample_order.desc()).limit(latest)
            rows = list((await self._session.scalars(stmt)).all())
            rows.reverse()
            return [self._to_sample(row) for row in rows]
        stmt = self._range_conditions(stmt, start, end)
        stmt = stmt.order_by(LogSampleRow.sample_order)
        if limit is not None:
            stmt = stmt.limit(limit)
        rows = (await self._session.scalars(stmt)).all()
        return [self._to_sample(row) for row in rows]

    async def count_samples(
        self,
        log_uid: str,
        *,
        start: datetime | Decimal | None = None,
        end: datetime | Decimal | None = None,
    ) -> int:
        log_id = await self._log_id(log_uid)
        if log_id is None:
            return 0
        stmt = select(func.count(LogSampleRow.id)).where(
            LogSampleRow.log_id == log_id
        )
        stmt = self._range_conditions(stmt, start, end)
        return int(await self._session.scalar(stmt) or 0)

    async def sample_range(
        self, log_uid: str
    ) -> tuple[datetime | Decimal | None, datetime | Decimal | None]:
        index_type = await self._session.scalar(
            select(LogRow.index_type).where(
                func.lower(LogRow.uid) == log_uid.lower()
            )
        )
        if index_type is None:
            return None, None
        log_id = await self._log_id(log_uid)
        if log_id is None:
            return None, None
        low_column = (
            LogSampleRow.index_time if index_type == "time" else LogSampleRow.index_value
        )
        stmt = select(func.min(low_column), func.max(low_column)).where(
            LogSampleRow.log_id == log_id
        )
        result = (await self._session.execute(stmt)).one()
        low, high = result[0], result[1]
        if low is None or high is None:
            return None, None
        return low, high

    async def delete_samples(
        self,
        log_uid: str,
        *,
        start: datetime | Decimal | None = None,
        end: datetime | Decimal | None = None,
    ) -> int:
        log_id = await self._log_id(log_uid)
        if log_id is None:
            return 0
        stmt = delete(LogSampleRow).where(LogSampleRow.log_id == log_id)
        stmt = self._range_conditions(stmt, start, end)
        result = await self._session.execute(stmt)
        await self._session.flush()
        return int(result.rowcount or 0)

    async def remove_curve_values(
        self,
        log_uid: str,
        mnemonic: str,
        *,
        start: datetime | Decimal | None = None,
        end: datetime | Decimal | None = None,
    ) -> int:
        log_id = await self._log_id(log_uid)
        if log_id is None:
            return 0
        stmt = select(LogSampleRow).where(LogSampleRow.log_id == log_id)
        stmt = self._range_conditions(stmt, start, end)
        rows = (await self._session.scalars(stmt)).all()
        changed = 0
        for row in rows:
            values = dict(row.values or {})
            if mnemonic in values:
                values.pop(mnemonic)
                row.values = values
                changed += 1
        await self._session.flush()
        return changed

    async def upsert_samples(
        self, log_uid: str, samples: list[LogSample], index_type: str
    ) -> tuple[int, int]:
        log_id = await self._log_id(log_uid)
        if log_id is None:
            raise LookupError("log no encontrado para muestras")
        rows = (
            await self._session.scalars(
                select(LogSampleRow).where(LogSampleRow.log_id == log_id)
            )
        ).all()
        existing: dict[Any, LogSampleRow] = {}
        next_order = 0
        for row in rows:
            key = row.index_time if index_type == "time" else row.index_value
            existing[key] = row
            next_order = max(next_order, row.sample_order + 1)
        inserted = 0
        updated = 0
        for sample in samples:
            key = sample.index_time if index_type == "time" else sample.index_value
            current = existing.get(key)
            if current is not None:
                merged = dict(current.values or {})
                # Un valor vacío no borra el dato previamente almacenado.
                merged.update(
                    {
                        mnemonic: value
                        for mnemonic, value in sample.values.items()
                        if value not in (None, "")
                    }
                )
                current.values = merged
                updated += 1
                continue
            row = LogSampleRow(
                log_id=log_id,
                sample_order=next_order,
                index_time=sample.index_time,
                index_value=sample.index_value,
                values=sample.values,
            )
            self._session.add(row)
            existing[key] = row
            next_order += 1
            inserted += 1
        await self._session.flush()
        return inserted, updated

    async def replace_curves(self, log_uid: str, curves: list[LogCurve]) -> None:
        log_id = await self._log_id(log_uid)
        if log_id is None:
            return
        await self._session.execute(delete(LogCurveRow).where(LogCurveRow.log_id == log_id))
        await self._insert_curves(log_id, curves)
        await self._session.flush()

    async def _insert_curves(self, log_id: int, curves: list[LogCurve]) -> None:
        for curve in curves:
            self._session.add(
                LogCurveRow(
                    log_id=log_id,
                    mnemonic=curve.mnemonic,
                    unit=curve.unit,
                    curve_type=curve.curve_type,
                    is_index=curve.is_index,
                    description=curve.description,
                    curve_uid=curve.uid,
                    ordering=curve.ordering,
                )
            )
        await self._session.flush()

    @staticmethod
    def _to_sample(row: LogSampleRow) -> LogSample:
        return LogSample(
            order=row.sample_order,
            index_time=row.index_time,
            index_value=row.index_value,
            values=row.values or {},
        )

    @staticmethod
    def _ordered(
        start: datetime | Decimal | None, end: datetime | Decimal | None
    ) -> tuple[Any, Any]:
        values = [value for value in (start, end) if value is not None]
        if not values:
            return None, None
        return min(values), max(values)


class SqlAlchemyTrajectoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(
        self,
        uid: str,
        uid_well: str | None = None,
        uid_wellbore: str | None = None,
        *,
        for_update: bool = False,
    ) -> TrajectoryRecord | None:
        stmt = select(TrajectoryRow).where(
            func.lower(TrajectoryRow.uid) == uid.lower()
        )
        if uid_well:
            stmt = stmt.where(func.lower(TrajectoryRow.uid_well) == uid_well.lower())
        if uid_wellbore:
            stmt = stmt.where(
                func.lower(TrajectoryRow.uid_wellbore) == uid_wellbore.lower()
            )
        if for_update:
            stmt = stmt.with_for_update()
        row = await self._session.scalar(stmt)
        return _to_trajectory(row) if row else None

    async def list(self, filters: ListFilter) -> list[TrajectoryRecord]:
        stmt = _apply_text_filters(select(TrajectoryRow), TrajectoryRow, filters)
        stmt = stmt.order_by(TrajectoryRow.id)
        if filters.limit:
            stmt = stmt.limit(filters.limit)
        rows = (await self._session.scalars(stmt)).all()
        return [_to_trajectory(row) for row in rows]

    async def add(self, record: TrajectoryRecord) -> None:
        row = TrajectoryRow(
            identity_key=identity_key(
                "trajectory", record.uid, record.uid_well, record.uid_wellbore
            ),
            md_min=record.md_min,
            md_max=record.md_max,
            md_uom=record.md_uom,
        )
        _apply_common(row, record)
        self._session.add(row)
        await self._session.flush()
        record.db_id = row.id

    async def update(self, record: TrajectoryRecord) -> None:
        row = await self._session.get(TrajectoryRow, record.db_id)
        if row is None:
            raise LookupError("trajectory no encontrado para actualizar")
        _apply_common(row, record)
        row.md_min = record.md_min
        row.md_max = record.md_max
        row.md_uom = record.md_uom

    async def delete(
        self, uid: str, uid_well: str | None = None, uid_wellbore: str | None = None
    ) -> None:
        stmt = select(TrajectoryRow.id).where(
            func.lower(TrajectoryRow.uid) == uid.lower()
        )
        if uid_well:
            stmt = stmt.where(func.lower(TrajectoryRow.uid_well) == uid_well.lower())
        if uid_wellbore:
            stmt = stmt.where(
                func.lower(TrajectoryRow.uid_wellbore) == uid_wellbore.lower()
            )
        trajectory_id = await self._session.scalar(stmt)
        if trajectory_id is None:
            return
        await self._session.execute(
            delete(TrajectoryStationRow).where(
                TrajectoryStationRow.trajectory_id == trajectory_id
            )
        )
        await self._session.execute(
            delete(TrajectoryRow).where(TrajectoryRow.id == trajectory_id)
        )

    async def list_stations(
        self,
        trajectory_uid: str,
        *,
        md_min: Decimal | None = None,
        md_max: Decimal | None = None,
    ) -> list[TrajectoryStation]:
        trajectory_id = await self._session.scalar(
            select(TrajectoryRow.id).where(
                func.lower(TrajectoryRow.uid) == trajectory_uid.lower()
            )
        )
        if trajectory_id is None:
            return []
        stmt = select(TrajectoryStationRow).where(
            TrajectoryStationRow.trajectory_id == trajectory_id
        )
        if md_min is not None:
            stmt = stmt.where(TrajectoryStationRow.md >= md_min)
        if md_max is not None:
            stmt = stmt.where(TrajectoryStationRow.md <= md_max)
        stmt = stmt.order_by(TrajectoryStationRow.station_order)
        rows = (await self._session.scalars(stmt)).all()
        return [
            TrajectoryStation(
                order=row.station_order,
                md=row.md,
                incl=row.incl,
                azi=row.azi,
                tvd=row.tvd,
                xml=row.xml,
            )
            for row in rows
        ]

    async def replace_stations(
        self, trajectory_uid: str, stations: list[TrajectoryStation]
    ) -> None:
        trajectory_id = await self._session.scalar(
            select(TrajectoryRow.id).where(
                func.lower(TrajectoryRow.uid) == trajectory_uid.lower()
            )
        )
        if trajectory_id is None:
            return
        await self._session.execute(
            delete(TrajectoryStationRow).where(
                TrajectoryStationRow.trajectory_id == trajectory_id
            )
        )
        for order, station in enumerate(stations):
            self._session.add(
                TrajectoryStationRow(
                    trajectory_id=trajectory_id,
                    station_order=order,
                    md=station.md,
                    incl=station.incl,
                    azi=station.azi,
                    tvd=station.tvd,
                    xml=station.xml,
                )
            )
        await self._session.flush()


class SqlAlchemyMudLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(
        self,
        uid: str,
        uid_well: str | None = None,
        uid_wellbore: str | None = None,
        *,
        for_update: bool = False,
    ) -> MudLogRecord | None:
        stmt = select(MudLogRow).where(func.lower(MudLogRow.uid) == uid.lower())
        if uid_well:
            stmt = stmt.where(func.lower(MudLogRow.uid_well) == uid_well.lower())
        if uid_wellbore:
            stmt = stmt.where(
                func.lower(MudLogRow.uid_wellbore) == uid_wellbore.lower()
            )
        if for_update:
            stmt = stmt.with_for_update()
        row = await self._session.scalar(stmt)
        return _to_mudlog(row) if row else None

    async def list(self, filters: ListFilter) -> list[MudLogRecord]:
        stmt = _apply_text_filters(select(MudLogRow), MudLogRow, filters)
        stmt = stmt.order_by(MudLogRow.id)
        if filters.limit:
            stmt = stmt.limit(filters.limit)
        rows = (await self._session.scalars(stmt)).all()
        return [_to_mudlog(row) for row in rows]

    async def add(self, record: MudLogRecord) -> None:
        row = MudLogRow(
            identity_key=identity_key(
                "mudLog", record.uid, record.uid_well, record.uid_wellbore
            ),
            md_min=record.md_min,
            md_max=record.md_max,
            md_uom=record.md_uom,
        )
        _apply_common(row, record)
        self._session.add(row)
        await self._session.flush()
        record.db_id = row.id

    async def update(self, record: MudLogRecord) -> None:
        row = await self._session.get(MudLogRow, record.db_id)
        if row is None:
            raise LookupError("mudLog no encontrado para actualizar")
        _apply_common(row, record)
        row.md_min = record.md_min
        row.md_max = record.md_max
        row.md_uom = record.md_uom

    async def delete(
        self, uid: str, uid_well: str | None = None, uid_wellbore: str | None = None
    ) -> None:
        stmt = delete(MudLogRow).where(func.lower(MudLogRow.uid) == uid.lower())
        if uid_well:
            stmt = stmt.where(func.lower(MudLogRow.uid_well) == uid_well.lower())
        if uid_wellbore:
            stmt = stmt.where(
                func.lower(MudLogRow.uid_wellbore) == uid_wellbore.lower()
            )
        await self._session.execute(stmt)


class SqlAlchemyChangeLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, record: ChangeLogRecord) -> None:
        self._session.add(
            ChangeLogRow(
                uid=record.uid,
                object_type=record.object_type,
                change_type=record.change_type,
                change_date=record.change_date,
                uid_well=record.uid_well,
                uid_wellbore=record.uid_wellbore,
                name_object=record.name_object,
                name_well=record.name_well,
                name_wellbore=record.name_wellbore,
                change_info=record.change_info,
                mnemonics=record.mnemonics,
                start_index=record.start_index,
                end_index=record.end_index,
            )
        )
        await self._session.flush()

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
    ) -> list[ChangeLogRecord]:
        stmt = select(ChangeLogRow)
        if object_type:
            stmt = stmt.where(ChangeLogRow.object_type == object_type)
        if uid:
            stmt = stmt.where(func.lower(ChangeLogRow.uid) == uid.lower())
        if uid_well:
            stmt = stmt.where(func.lower(ChangeLogRow.uid_well) == uid_well.lower())
        if uid_wellbore:
            stmt = stmt.where(
                func.lower(ChangeLogRow.uid_wellbore) == uid_wellbore.lower()
            )
        if change_type:
            stmt = stmt.where(ChangeLogRow.change_type == change_type)
        if start:
            stmt = stmt.where(ChangeLogRow.change_date >= start)
        if end:
            stmt = stmt.where(ChangeLogRow.change_date <= end)
        if allowed_wells is not None:
            stmt = stmt.where(
                func.lower(ChangeLogRow.uid_well).in_(
                    {value.lower() for value in allowed_wells}
                )
            )
        stmt = stmt.order_by(ChangeLogRow.change_date, ChangeLogRow.id).limit(limit)
        rows = (await self._session.scalars(stmt)).all()
        return [
            ChangeLogRecord(
                uid=row.uid,
                object_type=row.object_type,
                change_type=row.change_type,
                change_date=row.change_date,
                uid_well=row.uid_well,
                uid_wellbore=row.uid_wellbore,
                name_object=row.name_object,
                name_well=row.name_well,
                name_wellbore=row.name_wellbore,
                change_info=row.change_info,
                mnemonics=row.mnemonics,
                start_index=row.start_index,
                end_index=row.end_index,
            )
            for row in rows
        ]


class SqlAlchemyAuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, event: AuditEvent) -> None:
        self._session.add(
            AuditEventRow(
                occurred_at=event.occurred_at,
                actor_id=event.actor_id,
                actor_name=event.actor_name,
                channel=event.channel.value,
                action=event.action,
                object_type=event.object_type,
                object_uid=event.object_uid,
                result=event.result.value,
                correlation_id=event.correlation_id,
                duration_ms=event.duration_ms,
                details=event.details,
            )
        )
        await self._session.flush()

    async def search(
        self,
        *,
        limit: int = 50,
        cursor: int | None = None,
        actor: str | None = None,
        action: str | None = None,
        object_type: str | None = None,
        object_uid: str | None = None,
        result: str | None = None,
        correlation_id: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> tuple[list[AuditEvent], int | None]:
        stmt = select(AuditEventRow)
        if cursor is not None:
            stmt = stmt.where(AuditEventRow.id < cursor)
        if actor:
            stmt = stmt.where(AuditEventRow.actor_name == actor)
        if action:
            stmt = stmt.where(AuditEventRow.action == action)
        if object_type:
            stmt = stmt.where(AuditEventRow.object_type == object_type)
        if object_uid:
            stmt = stmt.where(AuditEventRow.object_uid == object_uid)
        if result:
            stmt = stmt.where(AuditEventRow.result == result)
        if correlation_id:
            stmt = stmt.where(AuditEventRow.correlation_id == correlation_id)
        if start:
            stmt = stmt.where(AuditEventRow.occurred_at >= start)
        if end:
            stmt = stmt.where(AuditEventRow.occurred_at <= end)
        stmt = stmt.order_by(AuditEventRow.id.desc()).limit(limit + 1)
        rows = (await self._session.scalars(stmt)).all()
        next_cursor = None
        if len(rows) > limit:
            rows = rows[:limit]
            next_cursor = rows[-1].id
        return [self._to_event(row) for row in rows], next_cursor

    @staticmethod
    def _to_event(row: AuditEventRow) -> AuditEvent:
        return AuditEvent(
            id=row.id,
            occurred_at=row.occurred_at,
            actor_id=row.actor_id,
            actor_name=row.actor_name,
            channel=AuditChannel(row.channel),
            action=row.action,
            object_type=row.object_type,
            object_uid=row.object_uid,
            result=AuditResult(row.result),
            correlation_id=row.correlation_id,
            duration_ms=row.duration_ms,
            details=row.details or {},
        )


class SqlAlchemyConfigRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self) -> ServerConfig | None:
        row = await self._session.get(ServerConfigRow, 1)
        return self._to_config(row) if row else None

    async def save(self, config: ServerConfig) -> None:
        row = await self._session.get(ServerConfigRow, 1)
        if row is None:
            row = ServerConfigRow(id=1)
            self._session.add(row)
        for field in (
            "contact_name",
            "contact_email",
            "contact_phone",
            "description",
            "product_name",
            "vendor",
            "version",
            "schema_version",
            "api_version",
            "setup_completed",
            "max_data_nodes",
            "max_data_points",
            "growing_timeout_seconds",
            "change_detection_seconds",
            "max_request_latest_values",
            "cascaded_delete",
            "support_uom_conversion",
            "updated_at",
            "updated_by",
        ):
            setattr(row, field, getattr(config, field))
        await self._session.flush()

    @staticmethod
    def _to_config(row: ServerConfigRow) -> ServerConfig:
        return ServerConfig(
            contact_name=row.contact_name,
            contact_email=row.contact_email,
            contact_phone=row.contact_phone,
            description=row.description,
            product_name=row.product_name,
            vendor=row.vendor,
            version=row.version,
            schema_version=row.schema_version,
            api_version=row.api_version,
            setup_completed=row.setup_completed,
            max_data_nodes=row.max_data_nodes,
            max_data_points=row.max_data_points,
            growing_timeout_seconds=row.growing_timeout_seconds,
            change_detection_seconds=row.change_detection_seconds,
            max_request_latest_values=row.max_request_latest_values,
            cascaded_delete=row.cascaded_delete,
            support_uom_conversion=row.support_uom_conversion,
            updated_at=row.updated_at,
            updated_by=row.updated_by,
        )


class SqlAlchemyIdentityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_service_account_by_name(
        self, name: str
    ) -> ServiceAccountRecord | None:
        row = await self._session.scalar(
            select(ServiceAccountRow).where(ServiceAccountRow.name == name)
        )
        return self._to_service(row) if row else None

    async def get_service_account(self, account_id: str) -> ServiceAccountRecord | None:
        row = await self._session.get(ServiceAccountRow, account_id)
        return self._to_service(row) if row else None

    async def list_service_accounts(self) -> list[ServiceAccountRecord]:
        rows = (await self._session.scalars(select(ServiceAccountRow))).all()
        return [self._to_service(row) for row in rows]

    async def save_service_account(self, account: ServiceAccountRecord) -> None:
        row = await self._session.get(ServiceAccountRow, account.id)
        if row is None:
            row = ServiceAccountRow(id=account.id)
            self._session.add(row)
        row.name = account.name
        row.role = account.role.value
        row.enabled = account.enabled
        row.credential_hash = account.credential_hash
        row.grants = [grant.to_dict() for grant in account.grants]
        row.well_scope = sorted(account.well_scope) if account.well_scope else None
        row.created_at = account.created_at
        row.rotated_at = account.rotated_at
        row.last_used_at = account.last_used_at
        row.failed_attempts = account.failed_attempts
        row.locked_until = account.locked_until
        await self._session.flush()

    async def delete_service_account(self, account_id: str) -> None:
        await self._session.execute(
            delete(ServiceAccountRow).where(ServiceAccountRow.id == account_id)
        )

    async def get_admin_user_by_email(self, email: str) -> AdminUserRecord | None:
        row = await self._session.scalar(
            select(AdminUserRow).where(func.lower(AdminUserRow.email) == email.lower())
        )
        return self._to_admin(row) if row else None

    async def get_admin_user(self, user_id: str) -> AdminUserRecord | None:
        row = await self._session.get(AdminUserRow, user_id)
        return self._to_admin(row) if row else None

    async def list_admin_users(self) -> list[AdminUserRecord]:
        rows = (await self._session.scalars(select(AdminUserRow))).all()
        return [self._to_admin(row) for row in rows]

    async def save_admin_user(self, user: AdminUserRecord) -> None:
        row = await self._session.get(AdminUserRow, user.id)
        if row is None:
            row = AdminUserRow(id=user.id)
            self._session.add(row)
        row.email = user.email
        row.display_name = user.display_name
        row.role = user.role.value
        row.password_hash = user.password_hash
        row.enabled = user.enabled
        row.permissions = sorted(user.permissions)
        row.must_change_password = user.must_change_password
        row.created_at = user.created_at
        row.last_login_at = user.last_login_at
        row.failed_attempts = user.failed_attempts
        row.locked_until = user.locked_until
        await self._session.flush()

    async def count_admin_users(self) -> int:
        return int(
            (await self._session.scalar(select(func.count()).select_from(AdminUserRow)))
            or 0
        )

    async def save_session(self, session: SessionRecord) -> None:
        self._session.add(
            AdminSessionRow(
                token_hash=session.token_hash,
                user_id=session.user_id,
                csrf_token=session.csrf_token,
                created_at=session.created_at,
                expires_at=session.expires_at,
                authenticated_at=session.authenticated_at,
            )
        )
        await self._session.flush()

    async def get_session(self, token_hash: str) -> SessionRecord | None:
        row = await self._session.get(AdminSessionRow, token_hash)
        if row is None:
            return None
        return SessionRecord(
            token_hash=row.token_hash,
            user_id=row.user_id,
            csrf_token=row.csrf_token,
            created_at=row.created_at,
            expires_at=row.expires_at,
            authenticated_at=row.authenticated_at,
            revoked_at=row.revoked_at,
        )

    async def revoke_session(self, token_hash: str, revoked_at: datetime) -> None:
        await self._session.execute(
            update(AdminSessionRow)
            .where(AdminSessionRow.token_hash == token_hash)
            .values(revoked_at=revoked_at)
        )

    async def revoke_user_sessions(self, user_id: str, revoked_at: datetime) -> None:
        await self._session.execute(
            update(AdminSessionRow)
            .where(AdminSessionRow.user_id == user_id, AdminSessionRow.revoked_at.is_(None))
            .values(revoked_at=revoked_at)
        )

    async def save_invitation(self, invitation: InvitationRecord) -> None:
        self._session.add(
            InvitationRow(
                id=invitation.id,
                email=invitation.email,
                role=invitation.role.value,
                token_hash=invitation.token_hash,
                permissions=sorted(invitation.permissions),
                expires_at=invitation.expires_at,
                created_by=invitation.created_by,
                created_at=invitation.created_at,
            )
        )
        await self._session.flush()

    async def get_invitation_by_token_hash(
        self, token_hash: str
    ) -> InvitationRecord | None:
        row = await self._session.scalar(
            select(InvitationRow).where(InvitationRow.token_hash == token_hash)
        )
        if row is None:
            return None
        return InvitationRecord(
            id=row.id,
            email=row.email,
            role=HumanRole(row.role),
            token_hash=row.token_hash,
            expires_at=row.expires_at,
            created_by=row.created_by,
            permissions=frozenset(row.permissions or ()),
            accepted_at=row.accepted_at,
            created_at=row.created_at,
        )

    async def mark_invitation_accepted(
        self, invitation_id: str, accepted_at: datetime
    ) -> None:
        await self._session.execute(
            update(InvitationRow)
            .where(InvitationRow.id == invitation_id)
            .values(accepted_at=accepted_at)
        )

    async def save_password_reset(self, reset: PasswordResetRecord) -> None:
        self._session.add(
            PasswordResetRow(
                token_hash=reset.token_hash,
                user_id=reset.user_id,
                created_at=reset.created_at,
                expires_at=reset.expires_at,
            )
        )
        await self._session.flush()

    async def get_password_reset(
        self, token_hash: str
    ) -> PasswordResetRecord | None:
        row = await self._session.get(PasswordResetRow, token_hash)
        if row is None:
            return None
        return PasswordResetRecord(
            token_hash=row.token_hash,
            user_id=row.user_id,
            expires_at=row.expires_at,
            created_at=row.created_at,
            used_at=row.used_at,
        )

    async def mark_password_reset_used(
        self, token_hash: str, used_at: datetime
    ) -> None:
        await self._session.execute(
            update(PasswordResetRow)
            .where(PasswordResetRow.token_hash == token_hash)
            .values(used_at=used_at)
        )

    @staticmethod
    def _to_service(row: ServiceAccountRow) -> ServiceAccountRecord:
        return ServiceAccountRecord(
            id=row.id,
            name=row.name,
            role=ServiceRole(row.role),
            enabled=row.enabled,
            credential_hash=row.credential_hash,
            grants=tuple(
                Grant(
                    object_type=grant["object_type"],
                    action=WitsmlAction(grant["action"]),
                    uid_well=grant.get("uid_well"),
                )
                for grant in (row.grants or ())
            ),
            well_scope=frozenset(row.well_scope) if row.well_scope else None,
            created_at=row.created_at,
            last_used_at=row.last_used_at,
            rotated_at=row.rotated_at,
            failed_attempts=row.failed_attempts,
            locked_until=row.locked_until,
        )

    @staticmethod
    def _to_admin(row: AdminUserRow) -> AdminUserRecord:
        return AdminUserRecord(
            id=row.id,
            email=row.email,
            display_name=row.display_name,
            role=HumanRole(row.role),
            password_hash=row.password_hash,
            enabled=row.enabled,
            permissions=frozenset(row.permissions or ()),
            must_change_password=row.must_change_password,
            created_at=row.created_at,
            last_login_at=row.last_login_at,
            failed_attempts=row.failed_attempts,
            locked_until=row.locked_until,
        )


class SqlAlchemyMailOutbox:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def enqueue(self, job: MailJob) -> None:
        self._session.add(
            MailOutboxRow(
                id=job.id,
                kind=job.kind,
                recipient=job.recipient,
                subject=job.subject,
                body=job.body,
                status=job.status,
                attempts=job.attempts,
                next_attempt_at=job.next_attempt_at,
                created_at=job.created_at,
            )
        )
        await self._session.flush()

    async def claim_pending(self, now: datetime, limit: int = 10) -> list[MailJob]:
        stmt = (
            select(MailOutboxRow)
            .where(
                MailOutboxRow.status == "pending",
                or_(
                    MailOutboxRow.next_attempt_at.is_(None),
                    MailOutboxRow.next_attempt_at <= now,
                ),
            )
            .order_by(MailOutboxRow.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        rows = (await self._session.scalars(stmt)).all()
        for row in rows:
            row.status = "sending"
            row.attempts += 1
        await self._session.flush()
        return [
            MailJob(
                id=row.id,
                kind=row.kind,
                recipient=row.recipient,
                subject=row.subject,
                body=row.body,
                status=row.status,
                attempts=row.attempts,
                next_attempt_at=row.next_attempt_at,
                last_error=row.last_error,
                created_at=row.created_at,
            )
            for row in rows
        ]

    async def mark_sent(self, job_id: str, sent_at: datetime) -> None:
        await self._session.execute(
            update(MailOutboxRow)
            .where(MailOutboxRow.id == job_id)
            .values(status="sent", sent_at=sent_at, last_error=None)
        )

    async def mark_failed(
        self, job_id: str, error: str, next_attempt_at: datetime
    ) -> None:
        row = await self._session.get(MailOutboxRow, job_id)
        if row is None:
            return
        row.last_error = error[:2000]
        if row.attempts >= 5:
            row.status = "failed"
        else:
            row.status = "pending"
            row.next_attempt_at = next_attempt_at

    async def pending_count(self) -> int:
        return int(
            (
                await self._session.scalar(
                    select(func.count())
                    .select_from(MailOutboxRow)
                    .where(MailOutboxRow.status.in_(("pending", "sending")))
                )
            )
            or 0
        )

    async def oldest_pending_at(self) -> datetime | None:
        return await self._session.scalar(
            select(func.min(MailOutboxRow.created_at)).where(
                MailOutboxRow.status.in_(("pending", "sending"))
            )
        )


class SqlAlchemyRepositories:
    """Contenedor de repositorios ligados a una sesión/transacción."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.wells = SqlAlchemyWellRepository(session)
        self.wellbores = SqlAlchemyWellboreRepository(session)
        self.logs = SqlAlchemyLogRepository(session)
        self.mud_logs = SqlAlchemyMudLogRepository(session)
        self.trajectories = SqlAlchemyTrajectoryRepository(session)
        self.change_log = SqlAlchemyChangeLogRepository(session)
        self.audit = SqlAlchemyAuditRepository(session)
        self.config = SqlAlchemyConfigRepository(session)
        self.identities = SqlAlchemyIdentityRepository(session)
        self.mail = SqlAlchemyMailOutbox(session)

    async def ping(self) -> None:
        await self.session.execute(text("SELECT 1"))
