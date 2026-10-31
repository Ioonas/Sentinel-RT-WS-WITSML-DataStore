"""Casos de uso del Store WITSML.

Implementa las siete funciones WMLS sobre los puertos de persistencia. No
conoce SOAP ni HTTP: recibe y devuelve cadenas XML y códigos WMLS.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from lxml import etree

from sentinel import API_VERSION, SCHEMA_VERSION
from sentinel.audit_config.domain import AuditChannel, AuditResult
from sentinel.audit_config.service import AuditService, ConfigService
from sentinel.identity_access.domain import Principal, WitsmlAction
from sentinel.shared.clock import Clock
from sentinel.shared.ids import IdGenerator
from sentinel.witsml_application.domain.codes import WmlsCode, base_message
from sentinel.witsml_application.domain.errors import WitsmlError
from sentinel.witsml_application.domain.models import (
    ChangeLogRecord,
    LogCurve,
    LogRecord,
    LogSample,
    StoredObject,
    TrajectoryRecord,
    TrajectoryStation,
    WellboreRecord,
    WellRecord,
)
from sentinel.witsml_application.ports import (
    ChangeLogRepositoryPort,
    ListFilter,
    LogRepositoryPort,
    SchemaValidatorPort,
    StoreResult,
    TrajectoryRepositoryPort,
    WellboreRepositoryPort,
    WellRepositoryPort,
)
from sentinel.xml_schema import documents as xd
from sentinel.xml_schema.objects import WRITABLE_TYPES, spec_for
from sentinel.xml_schema.parser import parse_xml, serialize
from sentinel.xml_schema.serializer import (
    ChangeLogView,
    build_capabilities,
    build_change_log,
)


class WitsmlStoreService:
    def __init__(
        self,
        *,
        wells: WellRepositoryPort,
        wellbores: WellboreRepositoryPort,
        logs: LogRepositoryPort,
        trajectories: TrajectoryRepositoryPort,
        change_log: ChangeLogRepositoryPort,
        config: ConfigService,
        audit: AuditService,
        clock: Clock,
        ids: IdGenerator,
        validator: SchemaValidatorPort,
    ) -> None:
        self._wells = wells
        self._wellbores = wellbores
        self._logs = logs
        self._trajectories = trajectories
        self._change_log = change_log
        self._config = config
        self._audit = audit
        self._clock = clock
        self._ids = ids
        self._validator = validator

    # ------------------------------------------------------------------
    # Descubrimiento
    # ------------------------------------------------------------------
    async def get_version(self) -> str:
        return SCHEMA_VERSION

    async def get_capabilities(self) -> str:
        return build_capabilities(await self._config.get())

    async def get_base_message(self, code: int) -> str:
        return base_message(code)

    # ------------------------------------------------------------------
    # GetFromStore
    # ------------------------------------------------------------------
    async def get_from_store(
        self,
        principal: Principal,
        *,
        object_type: str,
        query_xml: str,
        options_xml: str | None,
        correlation_id: str,
    ) -> StoreResult:
        started = time.perf_counter()
        try:
            if object_type == "changeLog":
                result = await self._get_change_log(
                    principal,
                    query_xml=query_xml,
                    options_xml=options_xml,
                )
            else:
                result = await self._get_objects(
                    principal,
                    object_type=object_type,
                    query_xml=query_xml,
                    options_xml=options_xml,
                )
        except WitsmlError as exc:
            await self._record_audit(
                principal,
                action=f"wmls.GetFromStore.{object_type}",
                result=AuditResult.ERROR if exc.wmls_code != int(
                    WmlsCode.INSUFFICIENT_RIGHTS
                ) else AuditResult.DENIED,
                correlation_id=correlation_id,
                object_type=object_type,
                started=started,
            )
            raise
        await self._record_audit(
            principal,
            action=f"wmls.GetFromStore.{object_type}",
            result=AuditResult.SUCCESS,
            correlation_id=correlation_id,
            object_type=object_type,
            started=started,
            details={"code": result.code},
        )
        return result

    async def _get_objects(
        self,
        principal: Principal,
        *,
        object_type: str,
        query_xml: str,
        options_xml: str | None,
    ) -> StoreResult:
        spec_for(object_type)
        options = xd.parse_options(options_xml)
        if options.return_elements not in (
            "all",
            "header-only",
            "id-only",
            "data-only",
            "station-location-only",
            "latest-change-only",
        ):
            raise WitsmlError(
                WmlsCode.INVALID_KEYWORD_VALUE,
                f"returnElements no soportado: {options.return_elements}",
            )
        queries = xd.parse_queries(query_xml, object_type)
        config = await self._config.get()
        container = xd.new_container(object_type)
        partial = False
        budget = config.max_data_nodes
        readable_wells = principal.readable_wells

        for query in queries:
            if not principal.allows_witsml(WitsmlAction.READ, object_type, query.uid_well):
                # No se revela la existencia de objetos fuera de alcance.
                if query.uid_well is not None or query.uid is not None:
                    continue
                raise WitsmlError(WmlsCode.INSUFFICIENT_RIGHTS)
            repo = self._repository(object_type)
            records = await repo.list(
                ListFilter(
                    uid=query.uid,
                    uid_well=query.uid_well,
                    uid_wellbore=query.uid_wellbore,
                    name=query.text_filters.get("name"),
                    text_filters=query.text_filters,
                    allowed_wells=readable_wells,
                )
            )
            for record in records:
                if budget <= 0:
                    partial = True
                    break
                element, used, truncated = await self._render_object(
                    record, object_type, options, query, config, budget
                )
                if element is None:
                    partial = partial or truncated
                    continue
                container.append(element)
                budget -= used
                partial = partial or truncated

        code = int(WmlsCode.PARTIAL_SUCCESS if partial else WmlsCode.SUCCESS)
        supp = (
            xd.make_supp_msg(
                [], ["La respuesta fue truncada por maxDataNodes/maxDataPoints."]
            )
            if partial
            else None
        )
        return StoreResult(code=code, xml_out=serialize(container), supp_msg=supp)

    async def _render_object(
        self,
        record: StoredObject,
        object_type: str,
        options: xd.QueryOptions,
        query: xd.ObjectQuery,
        config: Any,
        budget: int,
    ) -> tuple[etree._Element | None, int, bool]:
        element = parse_xml(record.xml)
        xd.ensure_namespace(element)
        growing = record.growing_until is not None and record.growing_until > self._clock.now()
        xd.apply_server_fields(
            element,
            created_at=record.created_at,
            changed_at=record.changed_at,
            growing=growing,
        )
        truncated = False
        used = 1
        wants_data = options.return_elements not in ("header-only", "id-only")

        if isinstance(record, LogRecord) and wants_data:
            latest = query.latest_values or options.request_latest_values
            if latest is not None and (
                latest <= 0 or latest > config.max_request_latest_values
            ):
                raise WitsmlError(
                    WmlsCode.INVALID_REQUEST_LATEST_VALUE,
                    "requestLatestValues debe estar entre 1 y "
                    f"{config.max_request_latest_values}.",
                )
            samples = await self._logs.list_samples(
                record.uid,
                start=query.start_index,
                end=query.end_index,
                latest=latest,
            )
            curve_count = max(1, len(record.curves))
            allowed_by_points = max(0, config.max_data_points // curve_count)
            allowed = min(budget, allowed_by_points)
            if len(samples) > allowed:
                samples = samples[:allowed]
                truncated = True
            used = len(samples) or 1
            log_data = self._build_log_data(record, samples)
            for old in xd.children(element, "logData"):
                element.remove(old)
            xd.append_group_child(element, log_data)
            if truncated and samples:
                last = samples[-1]
                self._set_range_end(element, record, last)
        elif isinstance(record, TrajectoryRecord) and wants_data:
            stations = await self._trajectories.list_stations(
                record.uid, md_min=query.md_min, md_max=query.md_max
            )
            allowed = max(0, budget)
            if len(stations) > allowed:
                stations = stations[:allowed]
                truncated = True
            used = len(stations) or 1
            for old in xd.children(element, "trajectoryStation"):
                element.remove(old)
            for station in stations:
                station_element = parse_xml(station.xml)
                xd.ensure_namespace(station_element)
                xd.append_group_child(element, station_element)

        return xd.apply_return_elements(element, options.return_elements), used, truncated

    @staticmethod
    def _build_log_data(record: LogRecord, samples: list[LogSample]) -> etree._Element:
        curves = list(record.curves)
        if not curves:
            mnemonics = [record.index_curve]
            if samples:
                mnemonics += [key for key in samples[0].values if key != record.index_curve]
            curves = [
                LogCurve(mnemonic=name, unit=None, curve_type=None, is_index=index == 0)
                for index, name in enumerate(mnemonics)
            ]
        index_curve = next(
            (curve for curve in curves if curve.is_index),
            curves[0] if curves else None,
        )
        ordered = (
            [index_curve] + [c for c in curves if c is not index_curve]
            if index_curve is not None
            else curves
        )
        mnemonics = [curve.mnemonic for curve in ordered if curve is not None]
        units = [curve.unit or "" for curve in ordered if curve is not None]
        rows: list[list[str]] = []
        for sample in samples:
            row = []
            for curve in ordered:
                if curve is None:
                    continue
                if curve.is_index:
                    value = (
                        sample.index_time
                        if record.index_type == "time"
                        else sample.index_value
                    )
                    row.append(xd.format_index_value(value))
                else:
                    row.append(sample.values.get(curve.mnemonic) or "")
            rows.append(row)
        return xd.build_log_data(mnemonics, units, rows)

    @staticmethod
    def _set_range_end(
        element: etree._Element, record: LogRecord, sample: LogSample
    ) -> None:
        name = "endDateTimeIndex" if record.index_type == "time" else "endIndex"
        value = sample.index_time if record.index_type == "time" else sample.index_value
        xd.set_child_text(element, name, xd.format_index_value(value))

    async def _get_change_log(
        self,
        principal: Principal,
        *,
        query_xml: str,
        options_xml: str | None,
    ) -> StoreResult:
        if not self._can_read_change_log(principal):
            raise WitsmlError(WmlsCode.INSUFFICIENT_RIGHTS)
        options = xd.parse_options(options_xml)
        queries = xd.parse_queries(query_xml, "changeLog")
        records: list[ChangeLogRecord] = []
        for query in queries:
            records.extend(
                await self._change_log.search(
                    object_type=query.object_type,
                    uid=query.uid,
                    uid_well=query.uid_well,
                    uid_wellbore=query.uid_wellbore,
                    change_type=query.change_type,
                    start=query.start_index if isinstance(query.start_index, datetime) else None,
                    end=query.end_index if isinstance(query.end_index, datetime) else None,
                    allowed_wells=principal.readable_wells,
                )
            )
        if options.return_elements == "latest-change-only":
            latest: dict[tuple[str, str, str | None, str | None], ChangeLogRecord] = {}
            for record in records:
                key = (record.object_type, record.uid, record.uid_well, record.uid_wellbore)
                current = latest.get(key)
                if current is None or record.change_date > current.change_date:
                    latest[key] = record
            records = sorted(latest.values(), key=lambda item: item.change_date)
        views = [
            ChangeLogView(
                uid=record.uid,
                object_type=record.object_type,
                change_type=record.change_type,
                change_date=record.change_date,
                uid_well=record.uid_well,
                uid_wellbore=record.uid_wellbore,
                name_object=record.name_object,
                name_well=record.name_well,
                name_wellbore=record.name_wellbore,
            )
            for record in records
        ]
        return StoreResult(code=int(WmlsCode.SUCCESS), xml_out=build_change_log(views))

    @staticmethod
    def _can_read_change_log(principal: Principal) -> bool:
        if principal.is_superadmin or principal.is_system:
            return True
        return any(grant.action == WitsmlAction.READ for grant in principal.grants)

    # ------------------------------------------------------------------
    # AddToStore
    # ------------------------------------------------------------------
    async def add_to_store(
        self,
        principal: Principal,
        *,
        object_type: str,
        xml_in: str,
        options_xml: str | None,
        correlation_id: str,
    ) -> StoreResult:
        started = time.perf_counter()
        try:
            result = await self._add(principal, object_type=object_type, xml_in=xml_in)
        except WitsmlError as exc:
            await self._record_audit(
                principal,
                action=f"wmls.AddToStore.{object_type}",
                result=AuditResult.DENIED
                if exc.wmls_code == int(WmlsCode.INSUFFICIENT_RIGHTS)
                else AuditResult.ERROR,
                correlation_id=correlation_id,
                object_type=object_type,
                started=started,
            )
            raise
        await self._record_audit(
            principal,
            action=f"wmls.AddToStore.{object_type}",
            result=AuditResult.SUCCESS,
            correlation_id=correlation_id,
            object_type=object_type,
            started=started,
            details={"code": result.code},
        )
        return result

    async def _add(
        self, principal: Principal, *, object_type: str, xml_in: str
    ) -> StoreResult:
        if object_type not in WRITABLE_TYPES:
            raise WitsmlError(WmlsCode.OBJECT_TYPE_NOT_SUPPORTED)
        root = parse_xml(xml_in)
        xd.ensure_namespace(root)
        self._validator.validate_document(object_type, root, operation="write")
        spec = spec_for(object_type)
        elements = [item for item in root if xd.localname(item) == spec.name]
        if not elements:
            raise WitsmlError(
                WmlsCode.MISSING_UID, f"XMLin no contiene elementos <{spec.name}>."
            )
        config = await self._config.get()
        now = self._clock.now()
        uids: list[str] = []

        for element in elements:
            xd.validate_object_element(object_type, element)
            uid_well = xd.attr(element, "uidWell")
            uid_wellbore = xd.attr(element, "uidWellbore")
            if object_type == "well":
                uid_well = xd.attr(element, "uid")
            if not principal.allows_witsml(WitsmlAction.WRITE, object_type, uid_well):
                raise WitsmlError(WmlsCode.INSUFFICIENT_RIGHTS)

            uid = xd.normalize_uid(xd.attr(element, "uid")) or self._ids.new_uid()
            element.set("uid", uid)
            xd.strip_server_fields(element)
            xd.apply_server_fields(
                element, created_at=now, changed_at=now, growing=False
            )

            if object_type == "well":
                xml = serialize(element)
                record: StoredObject = WellRecord(
                    uid=uid,
                    uid_well=uid,
                    uid_wellbore=None,
                    name=xd.text_of(element, "name"),
                    xml=xml,
                    fields=xd.parse_well_fields(element),
                    created_at=now,
                    changed_at=now,
                )
                await self._ensure_unique(self._wells, uid, None)
                await self._wells.add(record)  # type: ignore[arg-type]
            elif object_type == "wellbore":
                await self._require_parent("well", uid_well or "")
                xml = serialize(element)
                record = WellboreRecord(
                    uid=uid,
                    uid_well=uid_well,
                    uid_wellbore=None,
                    name=xd.text_of(element, "name"),
                    xml=xml,
                    fields=xd.parse_wellbore_fields(element),
                    created_at=now,
                    changed_at=now,
                )
                await self._ensure_unique(self._wellbores, uid, uid_well)
                await self._wellbores.add(record)  # type: ignore[arg-type]
            elif object_type == "log":
                await self._require_parent("wellbore", uid_wellbore or "", uid_well)
                header = xd.parse_log_header(element)
                data = xd.parse_log_data(element)
                samples = self._samples_from_rows(header, data, uid)
                self._enforce_write_limits(config, len(samples), max(1, len(header.curves)))
                start_index, end_index = self._range_from_samples(header, samples)
                xd.strip_payload(element)
                xml = serialize(element)
                record = LogRecord(
                    uid=uid,
                    uid_well=uid_well,
                    uid_wellbore=uid_wellbore,
                    name=xd.text_of(element, "name"),
                    xml=xml,
                    fields=header.fields,
                    created_at=now,
                    changed_at=now,
                    index_type=header.index_type,
                    index_curve=header.index_curve,
                    direction=header.direction,
                    start_index_time=start_index if header.index_type == "time" else None,
                    start_index_value=start_index
                    if header.index_type != "time"
                    else None,
                    end_index_time=end_index if header.index_type == "time" else None,
                    end_index_value=end_index if header.index_type != "time" else None,
                    index_uom=header.start_uom,
                    curves=[
                        LogCurve(
                            mnemonic=curve.mnemonic,
                            unit=curve.unit,
                            curve_type=curve.curve_type,
                            is_index=curve.is_index,
                            description=curve.description,
                            uid=curve.uid,
                            ordering=order,
                        )
                        for order, curve in enumerate(header.curves)
                    ],
                )
                await self._ensure_unique(self._logs, uid, uid_well, uid_wellbore)
                await self._logs.add(record)  # type: ignore[arg-type]
                if samples:
                    await self._logs.upsert_samples(uid, samples, header.index_type)
            else:
                await self._require_parent("wellbore", uid_wellbore or "", uid_well)
                header = xd.parse_trajectory_header(element)
                stations = self._stations_from_element(element, header)
                self._enforce_write_limits(config, len(stations), 1)
                md_min, md_max = self._md_range(stations)
                xd.strip_payload(element)
                xml = serialize(element)
                record = TrajectoryRecord(
                    uid=uid,
                    uid_well=uid_well,
                    uid_wellbore=uid_wellbore,
                    name=xd.text_of(element, "name"),
                    xml=xml,
                    fields=header.fields,
                    created_at=now,
                    changed_at=now,
                    md_min=md_min,
                    md_max=md_max,
                    md_uom=header.md_uom,
                )
                await self._ensure_unique(
                    self._trajectories, uid, uid_well, uid_wellbore
                )
                await self._trajectories.add(record)  # type: ignore[arg-type]
                if stations:
                    await self._trajectories.replace_stations(uid, stations)

            await self._change_log.add(
                ChangeLogRecord(
                    uid=uid,
                    object_type=object_type,
                    change_type="add",
                    change_date=now,
                    uid_well=uid_well,
                    uid_wellbore=uid_wellbore,
                    name_object=xd.text_of(element, "name"),
                    name_well=xd.text_of(element, "nameWell"),
                    name_wellbore=xd.text_of(element, "nameWellbore"),
                )
            )
            uids.append(uid)

        return StoreResult(
            code=int(WmlsCode.SUCCESS), supp_msg=xd.make_supp_msg(uids)
        )

    # ------------------------------------------------------------------
    # UpdateInStore
    # ------------------------------------------------------------------
    async def update_in_store(
        self,
        principal: Principal,
        *,
        object_type: str,
        xml_in: str,
        options_xml: str | None,
        correlation_id: str,
    ) -> StoreResult:
        started = time.perf_counter()
        try:
            result = await self._update(principal, object_type=object_type, xml_in=xml_in)
        except WitsmlError as exc:
            await self._record_audit(
                principal,
                action=f"wmls.UpdateInStore.{object_type}",
                result=AuditResult.DENIED
                if exc.wmls_code == int(WmlsCode.INSUFFICIENT_RIGHTS)
                else AuditResult.ERROR,
                correlation_id=correlation_id,
                object_type=object_type,
                started=started,
            )
            raise
        await self._record_audit(
            principal,
            action=f"wmls.UpdateInStore.{object_type}",
            result=AuditResult.SUCCESS,
            correlation_id=correlation_id,
            object_type=object_type,
            started=started,
            details={"code": result.code},
        )
        return result

    async def _update(
        self, principal: Principal, *, object_type: str, xml_in: str
    ) -> StoreResult:
        if object_type not in WRITABLE_TYPES:
            raise WitsmlError(WmlsCode.OBJECT_TYPE_NOT_SUPPORTED)
        root = parse_xml(xml_in)
        xd.ensure_namespace(root)
        self._validator.validate_document(object_type, root, operation="update")
        spec = spec_for(object_type)
        elements = [item for item in root if xd.localname(item) == spec.name]
        if not elements:
            raise WitsmlError(WmlsCode.MISSING_UID)
        config = await self._config.get()
        now = self._clock.now()
        uids: list[str] = []

        for element in elements:
            uid = xd.normalize_uid(xd.attr(element, "uid"))
            if not uid:
                raise WitsmlError(WmlsCode.MISSING_UID)
            uid_well = xd.attr(element, "uidWell")
            uid_wellbore = xd.attr(element, "uidWellbore")
            if object_type == "well":
                uid_well = uid
            if not principal.allows_witsml(WitsmlAction.WRITE, object_type, uid_well):
                raise WitsmlError(WmlsCode.INSUFFICIENT_RIGHTS)

            existing = await self._load_existing(
                object_type, uid, uid_well, uid_wellbore
            )
            if existing is None:
                raise WitsmlError(WmlsCode.OBJECT_NOT_EXIST)

            merged = xd.merge_header(parse_xml(existing.xml), element)
            xd.strip_server_fields(merged)
            growing_until = existing.growing_until

            if isinstance(existing, LogRecord):
                growing_until = await self._update_log(
                    existing, element, merged, now, config
                )
            elif isinstance(existing, TrajectoryRecord):
                growing_until = await self._update_trajectory(
                    existing, element, merged, now, config
                )

            changed = now
            growing = growing_until is not None and growing_until > now
            xd.apply_server_fields(
                merged, created_at=existing.created_at, changed_at=changed, growing=growing
            )
            xd.strip_payload(merged)
            existing.xml = serialize(merged)
            existing.changed_at = changed
            existing.growing_until = growing_until
            existing.fields = self._fields_for(object_type, merged)
            existing.name = xd.text_of(merged, "name")
            await self._update_repository(object_type, existing)
            await self._change_log.add(
                ChangeLogRecord(
                    uid=uid,
                    object_type=object_type,
                    change_type="update",
                    change_date=now,
                    uid_well=uid_well,
                    uid_wellbore=uid_wellbore,
                    name_object=xd.text_of(merged, "name"),
                    name_well=xd.text_of(merged, "nameWell"),
                    name_wellbore=xd.text_of(merged, "nameWellbore"),
                )
            )
            uids.append(uid)

        return StoreResult(
            code=int(WmlsCode.SUCCESS), supp_msg=xd.make_supp_msg(uids)
        )

    async def _update_log(
        self,
        record: LogRecord,
        incoming: etree._Element,
        merged: etree._Element,
        now: datetime,
        config: Any,
    ) -> datetime | None:
        index_type = xd.text_of(incoming, "indexType")
        if index_type and index_type.lower() != record.index_type:
            raise WitsmlError(
                WmlsCode.INPUT_OBJECT_NOT_COMPLIANT,
                "La dirección/tipo de índice de un log no puede cambiar.",
            )
        direction = xd.text_of(incoming, "direction")
        if direction and direction.lower() != record.direction:
            raise WitsmlError(
                WmlsCode.INPUT_OBJECT_NOT_COMPLIANT,
                "La dirección de un log no puede cambiar después de crearlo.",
            )

        incoming_curves = xd.parse_log_curves(incoming)
        if incoming_curves:
            merged_curves = {curve.mnemonic: curve for curve in record.curves}
            for order, curve in enumerate(incoming_curves):
                merged_curves[curve.mnemonic] = LogCurve(
                    mnemonic=curve.mnemonic,
                    unit=curve.unit,
                    curve_type=curve.curve_type,
                    is_index=curve.is_index,
                    description=curve.description,
                    uid=curve.uid,
                    ordering=order,
                )
            record.curves = list(merged_curves.values())
            await self._logs.replace_curves(record.uid, record.curves)

        data = xd.parse_log_data(incoming)
        if not data.rows:
            return record.growing_until

        if not data.units:
            raise WitsmlError(
                WmlsCode.MISSING_UNIT_LIST,
                "La actualización de logData requiere unitList.",
            )
        if record.index_curve not in data.mnemonics:
            raise WitsmlError(
                WmlsCode.INDEX_CURVE_NOT_FOUND,
                f"mnemonicList debe incluir la curva de índice '{record.index_curve}'.",
            )
        if len(set(data.mnemonics)) != len(data.mnemonics):
            raise WitsmlError(WmlsCode.MNEMONICS_NOT_UNIQUE)
        added_curve = False
        existing_mnemonics = {curve.mnemonic for curve in record.curves}
        for mnemonic in data.mnemonics:
            if mnemonic not in existing_mnemonics:
                unit = data.units[data.mnemonics.index(mnemonic)] if data.units else None
                record.curves.append(
                    LogCurve(
                        mnemonic=mnemonic,
                        unit=unit or None,
                        curve_type=None,
                        is_index=mnemonic == record.index_curve,
                        ordering=len(record.curves),
                    )
                )
                added_curve = True
        if added_curve:
            await self._logs.replace_curves(record.uid, record.curves)
        header = xd.LogHeader(
            index_type=record.index_type,
            index_curve=record.index_curve,
            direction=record.direction,
            start_index=record.start_index,
            end_index=record.end_index,
            start_uom=record.index_uom,
            end_uom=record.index_uom,
            curves=record.curves,
            fields=record.fields,
        )
        samples = self._samples_from_rows(header, data, record.uid)
        if len({self._sample_key(sample) for sample in samples}) != len(samples):
            raise WitsmlError(WmlsCode.NODES_WITH_SAME_INDEX)
        self._enforce_write_limits(config, len(samples), max(1, len(record.curves)))

        old_end = record.end_index
        old_start = record.start_index
        inserted, _updated = await self._logs.upsert_samples(
            record.uid, samples, record.index_type
        )
        indices = [
            sample.index_time if record.index_type == "time" else sample.index_value
            for sample in samples
            if (sample.index_time if record.index_type == "time" else sample.index_value)
            is not None
        ]
        if not indices:
            return record.growing_until
        new_min = min(indices)
        new_max = max(indices)
        starts = [value for value in (old_start, new_min) if value is not None]
        ends = [value for value in (old_end, new_max) if value is not None]
        if record.direction == "increasing":
            extended = old_end is None or new_max > old_end
            start_value = min(starts)
            end_value = max(ends)
        else:
            extended = old_end is None or new_min < old_end
            start_value = max(starts)
            end_value = min(ends)
        record.start_index_time = self._as_time(start_value, record.index_type)
        record.start_index_value = self._as_decimal(start_value, record.index_type)
        record.end_index_time = self._as_time(end_value, record.index_type)
        record.end_index_value = self._as_decimal(end_value, record.index_type)
        record.fields = dict(record.fields) | {
            "startIndex": xd.format_index_value(record.start_index),
            "endIndex": xd.format_index_value(record.end_index),
        }
        if inserted and extended:
            timeout = timedelta(seconds=config.growing_timeout_seconds)
            return now + timeout
        return record.growing_until

    async def _update_trajectory(
        self,
        record: TrajectoryRecord,
        incoming: etree._Element,
        merged: etree._Element,
        now: datetime,
        config: Any,
    ) -> datetime | None:
        header = xd.parse_trajectory_header(incoming)
        new_stations = xd.parse_trajectory_stations(incoming)
        if not new_stations:
            return record.growing_until
        self._enforce_write_limits(config, len(new_stations), 1)
        existing = await self._trajectories.list_stations(record.uid)
        by_md = {station.md: station for station in existing if station.md is not None}
        appended = False
        for station in new_stations:
            if station.md is not None and station.md in by_md:
                current = by_md[station.md]
                station.order = current.order
                by_md[station.md] = station
            else:
                station.order = len(by_md)
                by_md[station.md] = station
                appended = True
        stations = sorted(
            (station for station in by_md.values() if station.md is not None),
            key=lambda item: item.md or Decimal(0),
        )
        for order, station in enumerate(stations):
            station.order = order
        await self._trajectories.replace_stations(record.uid, stations)
        md_min, md_max = self._md_range(stations)
        extended = record.md_max is None or (md_max is not None and md_max > record.md_max)
        record.md_min = md_min
        record.md_max = md_max
        record.md_uom = header.md_uom or record.md_uom
        record.fields = dict(record.fields) | {
            "mdMn": xd.format_index_value(md_min),
            "mdMx": xd.format_index_value(md_max),
        }
        if appended and extended:
            return now + timedelta(seconds=config.growing_timeout_seconds)
        return record.growing_until

    # ------------------------------------------------------------------
    # DeleteFromStore
    # ------------------------------------------------------------------
    async def delete_from_store(
        self,
        principal: Principal,
        *,
        object_type: str,
        query_xml: str,
        options_xml: str | None,
        correlation_id: str,
    ) -> StoreResult:
        started = time.perf_counter()
        try:
            result = await self._delete(principal, object_type=object_type, query_xml=query_xml)
        except WitsmlError as exc:
            await self._record_audit(
                principal,
                action=f"wmls.DeleteFromStore.{object_type}",
                result=AuditResult.DENIED
                if exc.wmls_code == int(WmlsCode.INSUFFICIENT_RIGHTS)
                else AuditResult.ERROR,
                correlation_id=correlation_id,
                object_type=object_type,
                started=started,
            )
            raise
        await self._record_audit(
            principal,
            action=f"wmls.DeleteFromStore.{object_type}",
            result=AuditResult.SUCCESS,
            correlation_id=correlation_id,
            object_type=object_type,
            started=started,
        )
        return result

    async def _delete(
        self, principal: Principal, *, object_type: str, query_xml: str
    ) -> StoreResult:
        if object_type not in WRITABLE_TYPES:
            raise WitsmlError(WmlsCode.OBJECT_TYPE_NOT_SUPPORTED)
        queries = xd.parse_queries(query_xml, object_type)
        now = self._clock.now()
        deleted = 0
        for query in queries:
            if not query.uid:
                raise WitsmlError(WmlsCode.MISSING_UID)
            if not principal.allows_witsml(
                WitsmlAction.DELETE, object_type, query.uid_well
            ):
                raise WitsmlError(WmlsCode.INSUFFICIENT_RIGHTS)
            existing = await self._load_existing(
                object_type, query.uid, query.uid_well, query.uid_wellbore
            )
            if existing is None:
                raise WitsmlError(WmlsCode.OBJECT_NOT_EXIST)
            deleted_element = parse_xml(existing.xml)
            xd.ensure_namespace(deleted_element)
            await self._assert_no_children(object_type, existing)
            if object_type == "well":
                await self._wells.delete(query.uid)
            elif object_type == "wellbore":
                await self._wellbores.delete(query.uid, query.uid_well)
            elif object_type == "log":
                await self._logs.delete(query.uid, query.uid_well, query.uid_wellbore)
            else:
                await self._trajectories.delete(
                    query.uid, query.uid_well, query.uid_wellbore
                )
            await self._change_log.add(
                ChangeLogRecord(
                    uid=query.uid,
                    object_type=object_type,
                    change_type="delete",
                    change_date=now,
                    uid_well=query.uid_well,
                    uid_wellbore=query.uid_wellbore,
                    name_object=xd.text_of(deleted_element, "name"),
                    name_well=xd.text_of(deleted_element, "nameWell"),
                    name_wellbore=xd.text_of(deleted_element, "nameWellbore"),
                )
            )
            deleted += 1
        return StoreResult(
            code=int(WmlsCode.SUCCESS),
            supp_msg=xd.make_supp_msg([], [f"{deleted} objeto(s) eliminado(s)."]),
        )

    # ------------------------------------------------------------------
    # Utilidades internas
    # ------------------------------------------------------------------
    def _repository(self, object_type: str) -> Any:
        return {
            "well": self._wells,
            "wellbore": self._wellbores,
            "log": self._logs,
            "trajectory": self._trajectories,
        }[object_type]

    async def _load_existing(
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
        return await self._trajectories.get(uid, uid_well, uid_wellbore)

    async def _update_repository(self, object_type: str, record: StoredObject) -> None:
        if object_type == "well":
            await self._wells.update(record)  # type: ignore[arg-type]
        elif object_type == "wellbore":
            await self._wellbores.update(record)  # type: ignore[arg-type]
        elif object_type == "log":
            await self._logs.update(record)  # type: ignore[arg-type]
        else:
            await self._trajectories.update(record)  # type: ignore[arg-type]

    async def _ensure_unique(self, repo: Any, *args: str | None) -> None:
        if await repo.get(*args) is not None:
            raise WitsmlError(WmlsCode.DUPLICATE_OBJECT)

    async def _require_parent(
        self, parent_type: str, uid: str, uid_well: str | None = None
    ) -> None:
        if parent_type == "well":
            parent = await self._wells.get(uid)
        else:
            parent = await self._wellbores.get(uid, uid_well)
        if parent is None:
            raise WitsmlError(
                WmlsCode.MISSING_PARENT,
                f"No existe el objeto padre {parent_type} uid={uid}.",
            )

    async def _assert_no_children(
        self, object_type: str, record: StoredObject
    ) -> None:
        if object_type == "well":
            has_children = await self._wells.has_children(record.uid)
        elif object_type == "wellbore":
            has_children = await self._wellbores.has_children(
                record.uid, record.uid_well
            )
        else:
            return
        if has_children:
            raise WitsmlError(WmlsCode.NOT_BOTTOM_LEVEL)

    @staticmethod
    def _samples_from_rows(
        header: xd.LogHeader, data: xd.LogDataBlock, log_uid: str
    ) -> list[LogSample]:
        samples: list[LogSample] = []
        for order, row in enumerate(data.rows):
            raw_index = row.get(header.index_curve)
            if raw_index is None:
                raise WitsmlError(
                    WmlsCode.INDEX_CURVE_NOT_FOUND,
                    f"Fila sin valor para la curva de índice '{header.index_curve}'.",
                )
            index = xd.parse_index_value(raw_index, header.index_type)
            values = {
                mnemonic: value
                for mnemonic, value in row.items()
                if mnemonic != header.index_curve
            }
            samples.append(
                LogSample(
                    order=order,
                    index_time=index if header.index_type == "time" else None,
                    index_value=index if header.index_type != "time" else None,
                    values=values,
                )
            )
        return samples

    @staticmethod
    def _sample_key(sample: LogSample) -> str:
        return xd.format_index_value(
            sample.index_time if sample.index_time is not None else sample.index_value
        )

    @staticmethod
    def _range_from_samples(
        header: xd.LogHeader, samples: list[LogSample]
    ) -> tuple[datetime | Decimal | None, datetime | Decimal | None]:
        if not samples:
            return header.start_index, header.end_index
        indices = [
            sample.index_time if header.index_type == "time" else sample.index_value
            for sample in samples
        ]
        present = [value for value in indices if value is not None]
        if not present:
            return header.start_index, header.end_index
        return min(present), max(present)

    @staticmethod
    def _stations_from_element(
        element: etree._Element, header: xd.TrajectoryHeader
    ) -> list[TrajectoryStation]:
        return [
            TrajectoryStation(
                order=station.order,
                md=station.md,
                incl=station.incl,
                azi=station.azi,
                tvd=station.tvd,
                xml=station.xml,
            )
            for station in xd.parse_trajectory_stations(element)
        ]

    @staticmethod
    def _md_range(
        stations: list[TrajectoryStation],
    ) -> tuple[Decimal | None, Decimal | None]:
        values = [station.md for station in stations if station.md is not None]
        if not values:
            return None, None
        return min(values), max(values)

    @staticmethod
    def _fields_for(object_type: str, element: etree._Element) -> dict[str, Any]:
        if object_type == "well":
            return xd.parse_well_fields(element)
        if object_type == "wellbore":
            return xd.parse_wellbore_fields(element)
        if object_type == "log":
            return xd.parse_log_header(element).fields
        return xd.parse_trajectory_header(element).fields

    @staticmethod
    def _enforce_write_limits(config: Any, nodes: int, curves: int) -> None:
        if nodes > config.max_data_nodes or nodes * curves > config.max_data_points:
            raise WitsmlError(
                WmlsCode.MAX_DATA_EXCEEDED,
                f"La solicitud excede maxDataNodes={config.max_data_nodes} o "
                f"maxDataPoints={config.max_data_points}.",
            )

    @staticmethod
    def _as_time(value: Any, index_type: str) -> datetime | None:
        return value if index_type == "time" and isinstance(value, datetime) else None

    @staticmethod
    def _as_decimal(value: Any, index_type: str) -> Decimal | None:
        return value if index_type != "time" and isinstance(value, Decimal) else None

    async def _record_audit(
        self,
        principal: Principal,
        *,
        action: str,
        result: AuditResult,
        correlation_id: str,
        object_type: str | None,
        started: float,
        details: dict[str, object] | None = None,
    ) -> None:
        await self._audit.record(
            actor_id=principal.id,
            actor_name=principal.name,
            channel=AuditChannel.WMLS,
            action=action,
            result=result,
            correlation_id=correlation_id,
            object_type=object_type,
            duration_ms=int((time.perf_counter() - started) * 1000),
            details=details or {},
        )

    @staticmethod
    def supported_versions() -> tuple[str, str]:
        return API_VERSION, SCHEMA_VERSION
