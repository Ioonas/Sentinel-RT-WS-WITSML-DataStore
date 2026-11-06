"""Casos de uso del Store WITSML.

Implementa las siete funciones WMLS sobre los puertos de persistencia. No
conoce SOAP ni HTTP: recibe y devuelve cadenas XML y códigos WMLS.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from xml.sax.saxutils import escape

from lxml import etree

from sentinel import API_VERSION, SCHEMA_VERSION
from sentinel.audit_config.domain import AuditChannel, AuditResult, ServerConfig
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
    MudLogRecord,
    StoredObject,
    TrajectoryRecord,
    TrajectoryStation,
    WellboreRecord,
    WellRecord,
)
from sentinel.witsml_application.domain.uom import UomValidator
from sentinel.witsml_application.ports import (
    ChangeLogRepositoryPort,
    ListFilter,
    LogRepositoryPort,
    MudLogRepositoryPort,
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
    ChangeLogHistoryView,
    ChangeLogView,
    build_capabilities,
    build_change_log,
)

#: Máximo de filas que se recorren para calcular min/max por curva en una
#: respuesta ``header-only``. Los logs mayores usan su rango almacenado.
_HEADER_SAMPLE_LIMIT = 1000


class WitsmlStoreService:
    def __init__(
        self,
        *,
        wells: WellRepositoryPort,
        wellbores: WellboreRepositoryPort,
        logs: LogRepositoryPort,
        mud_logs: MudLogRepositoryPort,
        trajectories: TrajectoryRepositoryPort,
        change_log: ChangeLogRepositoryPort,
        config: ConfigService,
        audit: AuditService,
        clock: Clock,
        ids: IdGenerator,
        validator: SchemaValidatorPort,
        uom: UomValidator | None = None,
    ) -> None:
        self._wells = wells
        self._wellbores = wellbores
        self._logs = logs
        self._mud_logs = mud_logs
        self._trajectories = trajectories
        self._change_log = change_log
        self._config = config
        self._audit = audit
        self._clock = clock
        self._ids = ids
        self._validator = validator
        self._uom = uom or UomValidator()

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
        if options.request_object_selection:
            self._validate_selection_request(object_type, query_xml, options_xml)
            return await self._selection_capability(principal, object_type)
        mode = options.return_elements
        if mode not in (
            "all",
            "requested",
            "header-only",
            "id-only",
            "data-only",
            "station-location-only",
            "latest-change-only",
        ):
            raise WitsmlError(
                WmlsCode.INVALID_KEYWORD_VALUE,
                f"returnElements no soportado: {mode}",
            )
        growing = object_type in ("log", "trajectory", "mudLog")
        if mode in ("header-only", "data-only") and not growing:
            raise WitsmlError(WmlsCode.INVALID_OPTION_FOR_GROWING_ONLY)
        if mode == "station-location-only" and object_type != "trajectory":
            raise WitsmlError(WmlsCode.INVALID_OPTION_FOR_GROWING_ONLY)
        if mode == "latest-change-only":
            raise WitsmlError(WmlsCode.INVALID_OPTION_FOR_CHANGELOG)
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
                    created_after=query.created_after,
                    changed_after=query.changed_after,
                )
            )
            now = self._clock.now()
            for record in records:
                if query.object_growing is not None:
                    actual = (
                        record.growing_until is not None
                        and record.growing_until > now
                    )
                    if actual != query.object_growing:
                        continue
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
                [], ["Response truncated by maxDataNodes/maxDataPoints."]
            )
            if partial
            else None
        )
        return StoreResult(code=code, xml_out=serialize(container), supp_msg=supp)

    def _validate_selection_request(
        self, object_type: str, query_xml: str, options_xml: str | None
    ) -> None:
        """Aplica las reglas ``-427``/``-428`` de la API 1.4.1 §6.6.2.1.

        ``requestObjectSelectionCapability`` con un valor distinto de ``none``
        no admite ningún otro keyword de ``OptionsIn`` y exige que ``QueryIn``
        sea la Minimum Query Template.
        """
        others = [
            name
            for name in xd.option_names(options_xml)
            if name != "requestObjectSelectionCapability"
        ]
        if others:
            raise WitsmlError(
                WmlsCode.INVALID_OPTIONS_COMBINATION,
                "requestObjectSelectionCapability no admite otras opciones: "
                + ", ".join(sorted(others)),
            )
        if not xd.is_minimum_query(query_xml, object_type):
            raise WitsmlError(WmlsCode.INVALID_MINIMUM_QUERY)

    async def _selection_capability(
        self, principal: Principal, object_type: str
    ) -> StoreResult:
        """Plantilla de selección con valores no significativos (§6.6.2.1)."""
        container = xd.new_container(object_type)
        records = await self._repository(object_type).list(
            ListFilter(allowed_wells=principal.readable_wells, limit=1)
        )
        for record in records[:1]:
            element = parse_xml(record.xml)
            xd.ensure_namespace(element)
            xd.apply_server_fields(
                element,
                created_at=record.created_at,
                changed_at=record.changed_at,
                growing=record.growing_until is not None
                and record.growing_until > self._clock.now(),
            )
            container.append(xd.apply_selection_capability(element))
        return StoreResult(
            code=int(WmlsCode.SUCCESS), xml_out=serialize(container)
        )

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
        mode = options.return_elements
        wants_data = mode not in ("header-only", "id-only")
        if mode == "requested":
            selected = {item.name for item in query.selection}
            if isinstance(record, LogRecord):
                wants_data = "logData" in selected
            elif isinstance(record, TrajectoryRecord):
                wants_data = "trajectoryStation" in selected
            elif isinstance(record, MudLogRecord):
                wants_data = bool(selected & {"geologyInterval", "parameter"})
            else:
                wants_data = False

        if isinstance(record, LogRecord):
            latest = query.latest_values or options.request_latest_values
            if latest is not None and (
                latest <= 0 or latest > config.max_request_latest_values
            ):
                raise WitsmlError(
                    WmlsCode.INVALID_REQUEST_LATEST_VALUE,
                    "requestLatestValues debe estar entre 1 y "
                    f"{config.max_request_latest_values}.",
                )
            curve_count = max(1, len(record.curves))
            allowed = max(0, min(budget, config.max_data_points // curve_count))
            if options.max_return_nodes is not None:
                allowed = min(allowed, options.max_return_nodes)

            samples: list[LogSample]
            if latest is not None:
                all_samples = await self._logs.list_samples(record.uid)
                samples = self._latest_rows(record, all_samples, latest)
                if len(samples) > allowed:
                    samples = samples[:allowed]
                    truncated = True
            elif wants_data:
                samples = await self._logs.list_samples(
                    record.uid,
                    start=query.start_index,
                    end=query.end_index,
                    limit=allowed,
                )
                if len(samples) >= allowed and allowed > 0:
                    total = await self._logs.count_samples(
                        record.uid, start=query.start_index, end=query.end_index
                    )
                    truncated = total > len(samples)
            else:
                # Los encabezados pequeños se validan también por curva (prueba
                # 76a). Los logs masivos usan el rango almacenado para no
                # recorrer todas sus filas en cada SQ-010.
                total = await self._logs.count_samples(record.uid)
                if total <= _HEADER_SAMPLE_LIMIT:
                    samples = await self._logs.list_samples(record.uid)
                else:
                    samples = []

            if samples:
                start_value, end_value = self._sample_bounds(record, samples)
            else:
                start_value, end_value = await self._stored_range(record)
            self._apply_log_header(
                record, element, start_value, end_value
            )
            self._set_log_curve_ranges(
                record, element, samples, start_value, end_value
            )
            if wants_data:
                log_data = self._build_log_data(record, samples)
                for old in xd.children(element, "logData"):
                    element.remove(old)
                xd.append_group_child(element, log_data)
            used = len(samples) or 1
        elif isinstance(record, TrajectoryRecord) and wants_data:
            stations = await self._trajectories.list_stations(
                record.uid, md_min=query.md_min, md_max=query.md_max
            )
            allowed = max(0, budget)
            if options.max_return_nodes is not None:
                allowed = min(allowed, options.max_return_nodes)
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
            if stations:
                self._apply_trajectory_header(record, element, stations)
        elif isinstance(record, TrajectoryRecord):
            for old in xd.children(element, "trajectoryStation"):
                element.remove(old)
            self._apply_trajectory_header(record, element, [])
        elif isinstance(record, MudLogRecord):
            if wants_data:
                xd.filter_mudlog_md_range(element, query.md_min, query.md_max)
                allowed = max(0, budget)
                if options.max_return_nodes is not None:
                    allowed = min(allowed, options.max_return_nodes)
                truncated = xd.trim_mudlog_nodes(element, allowed)
                used = len(xd.mudlog_data_nodes(element)) or 1
            else:
                used = 1

        return (
            xd.apply_return_elements(
                element,
                options.return_elements,
                query.selection_items,
                query.selection,
            ),
            used,
            truncated,
        )

    @staticmethod
    def _sample_index(record: LogRecord, sample: LogSample) -> Any:
        return (
            sample.index_time
            if record.index_type == "time"
            else sample.index_value
        )

    @classmethod
    def _sample_bounds(
        cls, record: LogRecord, samples: list[LogSample]
    ) -> tuple[Any, Any]:
        indices = [
            cls._sample_index(record, sample)
            for sample in samples
            if cls._sample_index(record, sample) is not None
        ]
        if not indices:
            return None, None
        low, high = min(indices), max(indices)
        if record.direction == "decreasing":
            return high, low
        return low, high

    async def _stored_range(
        self, record: LogRecord
    ) -> tuple[Any, Any]:
        if record.start_index is not None and record.end_index is not None:
            return record.start_index, record.end_index
        low, high = await self._logs.sample_range(record.uid)
        if record.direction == "decreasing":
            return high, low
        return low, high

    @classmethod
    def _apply_log_header(
        cls,
        record: LogRecord,
        element: etree._Element,
        start_value: Any,
        end_value: Any,
    ) -> None:
        is_time = record.index_type == "time"
        for name in (
            "startIndex",
            "endIndex",
            "startDateTimeIndex",
            "endDateTimeIndex",
        ):
            for old in xd.children(element, name):
                element.remove(old)
        if is_time:
            if start_value is not None:
                xd.set_ordered_child_text(
                    element,
                    "startDateTimeIndex",
                    xd.format_index_value(start_value),
                )
            if end_value is not None:
                xd.set_ordered_child_text(
                    element,
                    "endDateTimeIndex",
                    xd.format_index_value(end_value),
                )
        else:
            if start_value is not None:
                xd.set_ordered_child_text(
                    element,
                    "startIndex",
                    xd.format_index_value(start_value),
                    uom=record.index_uom,
                )
            if end_value is not None:
                xd.set_ordered_child_text(
                    element,
                    "endIndex",
                    xd.format_index_value(end_value),
                    uom=record.index_uom,
                )

    @classmethod
    def _set_log_curve_ranges(
        cls,
        record: LogRecord,
        element: etree._Element,
        samples: list[LogSample],
        start_value: Any,
        end_value: Any,
    ) -> None:
        is_time = record.index_type == "time"
        by_mnemonic = {
            xd.text_of(item, "mnemonic"): item
            for item in xd.children(element, "logCurveInfo")
        }
        for curve in record.curves:
            curve_element = by_mnemonic.get(curve.mnemonic)
            if curve_element is None:
                continue
            for name in (
                "minIndex",
                "maxIndex",
                "minDateTimeIndex",
                "maxDateTimeIndex",
            ):
                for old in xd.children(curve_element, name):
                    curve_element.remove(old)
            indices: list[Any] = []
            for sample in samples:
                if curve.is_index or curve.mnemonic == record.index_curve:
                    index = cls._sample_index(record, sample)
                else:
                    value = sample.values.get(curve.mnemonic)
                    if value is None or value == "":
                        continue
                    index = cls._sample_index(record, sample)
                if index is not None:
                    indices.append(index)
            if not indices:
                if start_value is None or end_value is None:
                    continue
                indices = [start_value, end_value]
            low = min(indices)
            high = max(indices)
            if is_time:
                xd.set_ordered_child_text(
                    curve_element,
                    "minDateTimeIndex",
                    xd.format_index_value(low),
                    order=xd._LOG_CURVE_CHILD_ORDER,
                )
                xd.set_ordered_child_text(
                    curve_element,
                    "maxDateTimeIndex",
                    xd.format_index_value(high),
                    order=xd._LOG_CURVE_CHILD_ORDER,
                )
            else:
                xd.set_ordered_child_text(
                    curve_element,
                    "minIndex",
                    xd.format_index_value(low),
                    uom=record.index_uom,
                    order=xd._LOG_CURVE_CHILD_ORDER,
                )
                xd.set_ordered_child_text(
                    curve_element,
                    "maxIndex",
                    xd.format_index_value(high),
                    uom=record.index_uom,
                    order=xd._LOG_CURVE_CHILD_ORDER,
                )

    @classmethod
    def _apply_trajectory_header(
        cls,
        record: TrajectoryRecord,
        element: etree._Element,
        stations: list[TrajectoryStation],
    ) -> None:
        values = [station.md for station in stations if station.md is not None]
        if values:
            md_min, md_max = min(values), max(values)
        else:
            md_min, md_max = record.md_min, record.md_max
        if md_min is None or md_max is None:
            return
        xd.set_ordered_child_text(
            element, "mdMn", xd.format_index_value(md_min), uom=record.md_uom,
            order=xd._TRAJECTORY_CHILD_ORDER,
        )
        xd.set_ordered_child_text(
            element, "mdMx", xd.format_index_value(md_max), uom=record.md_uom,
            order=xd._TRAJECTORY_CHILD_ORDER,
        )

    @classmethod
    def _latest_rows(
        cls, record: LogRecord, samples: list[LogSample], latest: int
    ) -> list[LogSample]:
        """Filas sintéticas con los últimos ``latest`` valores de cada curva."""
        curves = [curve.mnemonic for curve in record.curves if not curve.is_index]
        if not curves:
            curves = [
                key
                for key in (samples[0].values if samples else {})
                if key != record.index_curve
            ]
        merged: dict[Any, LogSample] = {}
        for mnemonic in curves:
            matches = [
                sample
                for sample in samples
                if sample.values.get(mnemonic) not in (None, "")
            ]
            for sample in matches[-latest:]:
                index = cls._sample_index(record, sample)
                if index is None:
                    continue
                current = merged.get(index)
                if current is None:
                    current = LogSample(
                        order=0,
                        index_time=sample.index_time,
                        index_value=sample.index_value,
                        values={},
                    )
                    merged[index] = current
                current.values[mnemonic] = sample.values.get(mnemonic)
        rows = sorted(
            merged.values(),
            key=lambda item: item.index_time
            if item.index_time is not None
            else item.index_value,
            reverse=record.direction == "decreasing",
        )
        for order, row in enumerate(rows):
            row.order = order
        return rows

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
        latest_only = options.return_elements == "latest-change-only"
        queries = xd.parse_queries(query_xml, "changeLog")
        merged: dict[
            tuple[str, str, str | None, str | None], list[ChangeLogRecord]
        ] = {}
        for query in queries:
            records = await self._change_log.search(
                object_type=query.object_type,
                uid=query.uid,
                uid_well=query.uid_well,
                uid_wellbore=query.uid_wellbore,
                allowed_wells=principal.readable_wells,
                limit=100_000,
            )
            grouped: dict[
                tuple[str, str, str | None, str | None], list[ChangeLogRecord]
            ] = {}
            for record in records:
                key = (
                    record.object_type,
                    record.uid,
                    record.uid_well,
                    record.uid_wellbore,
                )
                grouped.setdefault(key, []).append(record)
            for key, items in grouped.items():
                items.sort(key=lambda item: item.change_date)
                latest = items[-1]
                # ``commonData/dTimLastChange`` filtra a nivel de objeto.
                if (
                    query.changed_after is not None
                    and latest.change_date <= query.changed_after
                ):
                    continue
                histories = items
                if query.start_index is not None:
                    histories = [
                        item
                        for item in histories
                        if item.change_date > query.start_index
                    ]
                if query.change_type:
                    histories = [
                        item
                        for item in histories
                        if item.change_type == query.change_type
                    ]
                if not latest_only and not histories:
                    continue
                merged[key] = histories or items
        views: list[ChangeLogView] = []
        for items in merged.values():
            items.sort(key=lambda item: item.change_date)
            latest = items[-1]
            current = await self._current_names(
                latest.object_type, latest.uid, latest.uid_well, latest.uid_wellbore
            )
            index_uom = current[3] if current is not None else None
            histories = ()
            if not latest_only:
                histories = tuple(
                    ChangeLogHistoryView(
                        change_date=item.change_date,
                        change_type=item.change_type,
                        change_info=item.change_info,
                        start_index=item.start_index,
                        end_index=item.end_index,
                        mnemonics=item.mnemonics,
                        index_uom=index_uom,
                    )
                    for item in items
                )
            last_type = items[-1].change_type if items else "update"
            last_info = items[-1].change_info if items else None
            name_object = self._last_value(items, "name_object")
            name_well = self._last_value(items, "name_well")
            name_wellbore = self._last_value(items, "name_wellbore")
            if current is not None:
                name_object = current[0] or name_object
                name_well = current[1] or name_well
                name_wellbore = current[2] or name_wellbore
            views.append(
                ChangeLogView(
                    uid=latest.uid,
                    object_type=latest.object_type,
                    name_object=name_object,
                    name_well=name_well,
                    name_wellbore=name_wellbore,
                    uid_well=latest.uid_well,
                    uid_wellbore=latest.uid_wellbore,
                    histories=histories,
                    last_change_type=last_type,
                    last_change_info=last_info,
                    d_tim_last_change=latest.change_date,
                    include_history=not latest_only,
                )
            )
        views.sort(
            key=lambda item: (
                item.d_tim_last_change.isoformat() if item.d_tim_last_change else ""
            )
        )
        return StoreResult(code=int(WmlsCode.SUCCESS), xml_out=build_change_log(views))

    async def _current_names(
        self,
        object_type: str,
        uid: str,
        uid_well: str | None,
        uid_wellbore: str | None,
    ) -> tuple[str | None, str | None, str | None, str | None] | None:
        if object_type not in WRITABLE_TYPES:
            return None
        record = await self._load_existing(object_type, uid, uid_well, uid_wellbore)
        if record is None:
            return None
        element = parse_xml(record.xml)
        xd.ensure_namespace(element)
        index_uom = record.index_uom if isinstance(record, LogRecord) else None
        return (
            xd.text_of(element, "name"),
            xd.text_of(element, "nameWell"),
            xd.text_of(element, "nameWellbore"),
            index_uom,
        )

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

    async def create_object_as_admin(
        self, object_type: str, *, uid: str | None, uid_well: str | None, name: str
    ) -> str:
        """Alta de pozo o pozo lateral iniciada por un administrador humano.

        Aplica la misma validación XSD, unicidad y padre que WMLS_AddToStore.
        La autorización la decide el permiso admin.objects.write, no los derechos
        WITSML de un cliente. Devuelve el uid asignado.
        """
        if object_type == "well":
            uid_value = xd.normalize_uid(uid or "") or self._ids.new_uid()
            xml = (
                f'<wells version="1.4.1.1"><well uid="{escape(uid_value)}">'
                f"<name>{escape(name)}</name></well></wells>"
            )
        elif object_type == "wellbore":
            if not uid_well:
                raise WitsmlError(WmlsCode.MISSING_UID, "Indique el uid del pozo.")
            await self._require_parent("well", uid_well)
            parent = await self._wells.get(uid_well)
            uid_value = xd.normalize_uid(uid or "") or self._ids.new_uid()
            xml = (
                f'<wellbores version="1.4.1.1">'
                f'<wellbore uid="{escape(uid_value)}" uidWell="{escape(uid_well)}">'
                f"<nameWell>{escape(parent.name or uid_well)}</nameWell>"
                f"<name>{escape(name)}</name></wellbore></wellbores>"
            )
        else:
            raise WitsmlError(WmlsCode.OBJECT_TYPE_NOT_SUPPORTED)
        await self._add(None, object_type=object_type, xml_in=xml)
        return uid_value

    async def _add(
        self, principal: Principal | None, *, object_type: str, xml_in: str
    ) -> StoreResult:
        if object_type not in WRITABLE_TYPES:
            raise WitsmlError(WmlsCode.OBJECT_TYPE_NOT_SUPPORTED)
        root = parse_xml(xml_in)
        xd.ensure_namespace(root)
        self._uom.validate(root)
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
            xd.validate_object_element(object_type, element, require_uid=False)
            uid_well = xd.attr(element, "uidWell")
            uid_wellbore = xd.attr(element, "uidWellbore")
            if object_type == "well":
                uid_well = xd.attr(element, "uid")
            # Con principal None (alta administrativa) el permiso admin ya autorizó.
            if principal is not None and not principal.allows_witsml(
                WitsmlAction.WRITE, object_type, uid_well
            ):
                raise WitsmlError(WmlsCode.INSUFFICIENT_RIGHTS)

            uid = xd.normalize_uid(xd.attr(element, "uid")) or self._ids.new_uid()
            element.set("uid", uid)
            # ``mudLog`` es de crecimiento aleatorio: se conserva el
            # ``objectGrowing`` declarado por el cliente en el alta. Debe leerse
            # antes de ``strip_server_fields``, que lo elimina.
            incoming_growing = (
                xd.parse_object_growing(element) if object_type == "mudLog" else False
            )
            xd.strip_server_fields(element)
            xd.apply_server_fields(
                element, created_at=now, changed_at=now, growing=incoming_growing
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
            elif object_type == "mudLog":
                await self._require_parent("wellbore", uid_wellbore or "", uid_well)
                md_min, md_max, md_uom = xd.mudlog_md_range(element)
                nodes = len(xd.mudlog_data_nodes(element))
                self._enforce_write_limits(config, nodes, 1)
                growing_until = (
                    now + timedelta(seconds=config.growing_timeout_seconds)
                    if incoming_growing
                    else None
                )
                xml = serialize(element)
                record = MudLogRecord(
                    uid=uid,
                    uid_well=uid_well,
                    uid_wellbore=uid_wellbore,
                    name=xd.text_of(element, "name"),
                    xml=xml,
                    fields=xd.parse_mudlog_fields(element),
                    created_at=now,
                    changed_at=now,
                    growing_until=growing_until,
                    md_min=md_min,
                    md_max=md_max,
                    md_uom=md_uom,
                )
                await self._ensure_unique(
                    self._mud_logs, uid, uid_well, uid_wellbore
                )
                await self._mud_logs.add(record)
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
        self._uom.validate(root)
        self._validator.validate_document(object_type, root, operation="update")
        spec = spec_for(object_type)
        elements = [item for item in root if xd.localname(item) == spec.name]
        if not elements:
            raise WitsmlError(WmlsCode.MISSING_UID)
        config = await self._config.get()
        prepared: list[
            tuple[etree._Element, str, str | None, str | None, StoredObject]
        ] = []

        # Primera pasada: permisos, existencia, bloqueo y token de todas las
        # entradas antes de persistir nada. Así un conflicto de concurrencia en
        # un lote no deja escrituras parciales de los elementos anteriores.
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
                object_type, uid, uid_well, uid_wellbore, for_update=True
            )
            if existing is None:
                raise WitsmlError(WmlsCode.OBJECT_NOT_EXIST)
            self._require_matching_token(
                xd.last_change_token(element), existing.changed_at
            )
            prepared.append((element, uid, uid_well, uid_wellbore, existing))

        uids: list[str] = []
        for element, uid, uid_well, uid_wellbore, existing in prepared:
            # Se calcula tras adquirir el bloqueo para que el nuevo
            # ``dTimLastChange`` no retroceda respecto del que acaba de escribir
            # otra transacción.
            now = self._clock.now()

            merged = xd.merge_header(parse_xml(existing.xml), element)
            xd.strip_server_fields(merged)
            growing_until = existing.growing_until
            history = ChangeLogHistoryView(change_date=now, change_type="update")

            if isinstance(existing, LogRecord):
                growing_until, history = await self._update_log(
                    existing, element, merged, now, config
                )
            elif isinstance(existing, TrajectoryRecord):
                growing_until, history = await self._update_trajectory(
                    existing, element, merged, now, config
                )
            elif isinstance(existing, MudLogRecord):
                growing_until, history = self._update_mudlog(
                    existing, element, merged, now, config
                )

            changed = now
            growing = growing_until is not None and growing_until > now
            xd.apply_server_fields(
                merged, created_at=existing.created_at, changed_at=changed, growing=growing
            )
            if not isinstance(existing, MudLogRecord):
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
                    change_info=history.change_info,
                    mnemonics=history.mnemonics,
                    start_index=history.start_index,
                    end_index=history.end_index,
                )
            )
            uids.append(uid)

        return StoreResult(
            code=int(WmlsCode.SUCCESS), supp_msg=xd.make_supp_msg(uids)
        )

    def _update_mudlog(
        self,
        record: MudLogRecord,
        incoming: etree._Element,
        merged: etree._Element,
        now: datetime,
        config: Any,
    ) -> tuple[datetime | None, ChangeLogHistoryView]:
        """Fusiona nodos de datos de un ``mudLog`` por ``uid``.

        ``mudLog`` crece de forma aleatoria: la actualización de un
        ``geologyInterval`` o ``parameter`` extiende el periodo de crecimiento.
        """
        history = ChangeLogHistoryView(change_date=now, change_type="update")
        growing_until = record.growing_until
        if xd.merge_mudlog_nodes(merged, incoming):
            nodes = len(xd.mudlog_data_nodes(merged))
            self._enforce_write_limits(config, nodes, 1)
            growing_until = now + timedelta(seconds=config.growing_timeout_seconds)
        record.md_min, record.md_max, record.md_uom = xd.mudlog_md_range(merged)
        return growing_until, history

    async def _update_log(
        self,
        record: LogRecord,
        incoming: etree._Element,
        merged: etree._Element,
        now: datetime,
        config: Any,
    ) -> tuple[datetime | None, ChangeLogHistoryView]:
        history = ChangeLogHistoryView(change_date=now, change_type="update")
        index_type = xd.normalize_index_type(xd.text_of(incoming, "indexType"))
        if index_type and index_type != record.index_type:
            raise WitsmlError(
                WmlsCode.INPUT_OBJECT_NOT_COMPLIANT,
                "Log indexType cannot change after creation.",
            )
        direction = (xd.text_of(incoming, "direction") or "").strip().lower()
        if direction and direction != record.direction:
            raise WitsmlError(
                WmlsCode.INPUT_OBJECT_NOT_COMPLIANT,
                "Log direction cannot change after creation.",
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
            return record.growing_until, history

        if not data.units:
            raise WitsmlError(
                WmlsCode.MISSING_UNIT_LIST,
                "The logData update requires unitList.",
            )
        if record.index_curve not in data.mnemonics:
            raise WitsmlError(
                WmlsCode.INDEX_CURVE_NOT_FOUND,
                f"mnemonicList must include the index curve '{record.index_curve}'.",
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
        # §6.7.4.6 de la API 1.4.1: se limpia por canal el rango implícito de la
        # actualización, no el startIndex/endIndex del encabezado.
        await self._clear_updated_channels(record, samples)

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
            return record.growing_until, history
        new_min = min(indices)
        new_max = max(indices)
        history_mnemonics = ",".join(data.mnemonics) if data.mnemonics else None
        if record.direction == "decreasing":
            history_start, history_end = new_max, new_min
        else:
            history_start, history_end = new_min, new_max
        history = ChangeLogHistoryView(
            change_date=now,
            change_type="update",
            mnemonics=history_mnemonics,
            start_index=xd.format_index_value(history_start),
            end_index=xd.format_index_value(history_end),
        )
        starts = [value for value in (old_start, new_min) if value is not None]
        ends = [value for value in (old_end, new_max) if value is not None]
        old_min = min((value for value in (old_start, old_end) if value is not None), default=None)
        old_max = max((value for value in (old_start, old_end) if value is not None), default=None)
        extended = (
            old_max is None
            or new_max > old_max
            or old_min is None
            or new_min < old_min
        )
        if record.direction == "increasing":
            start_value = min(starts)
            end_value = max(ends)
        else:
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
            return now + timeout, history
        return record.growing_until, history

    async def _clear_updated_channels(
        self, record: LogRecord, samples: list[LogSample]
    ) -> None:
        """Limpieza por canal del §6.7.4.6 de la API 1.4.1.

        Cada curva se limpia entre el menor y el mayor índice donde la
        actualización trae valor para esa curva; las filas ausentes de ese
        rango quedan en nulo y las curvas omitidas no se tocan. Un append
        conserva los valores fuera de su rango implícito y una modificación
        interior borra el valor previo del índice no informado.
        """
        ranges: dict[str, tuple[Any, Any]] = {}
        for sample in samples:
            index = (
                sample.index_time
                if record.index_type == "time"
                else sample.index_value
            )
            if index is None:
                continue
            for mnemonic, value in sample.values.items():
                if mnemonic == record.index_curve or value in (None, ""):
                    continue
                current = ranges.get(mnemonic)
                if current is None:
                    ranges[mnemonic] = (index, index)
                    continue
                low, high = current
                ranges[mnemonic] = (min(low, index), max(high, index))
        for mnemonic, (low, high) in ranges.items():
            await self._logs.remove_curve_values(
                record.uid, mnemonic, start=low, end=high
            )

    async def _update_trajectory(
        self,
        record: TrajectoryRecord,
        incoming: etree._Element,
        merged: etree._Element,
        now: datetime,
        config: Any,
    ) -> tuple[datetime | None, ChangeLogHistoryView]:
        history = ChangeLogHistoryView(change_date=now, change_type="update")
        header = xd.parse_trajectory_header(incoming)
        new_stations = xd.parse_trajectory_stations(incoming)
        if not new_stations:
            return record.growing_until, history
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
        extended = record.md_max is None or (
            (md_max is not None and md_max > record.md_max)
            or (
                md_min is not None
                and record.md_min is not None
                and md_min < record.md_min
            )
        )
        record.md_min = md_min
        record.md_max = md_max
        record.md_uom = header.md_uom or record.md_uom
        record.fields = dict(record.fields) | {
            "mdMn": xd.format_index_value(md_min),
            "mdMx": xd.format_index_value(md_max),
        }
        if appended and extended:
            return now + timedelta(seconds=config.growing_timeout_seconds), history
        return record.growing_until, history

    # ------------------------------------------------------------------
    # DeleteFromStore
    # ------------------------------------------------------------------
    @staticmethod
    def _require_cascade(principal: Principal, config: ServerConfig) -> None:
        if not (config.cascaded_delete and principal.can_cascade_delete):
            raise WitsmlError(
                WmlsCode.INSUFFICIENT_RIGHTS,
                f"{base_message(int(WmlsCode.INSUFFICIENT_RIGHTS))} "
                "cascadedDelete requiere el permiso de borrado en cascada.",
            )

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
        options = xd.parse_options(options_xml)
        try:
            if options.cascaded_delete:
                self._require_cascade(principal, await self._config.get())
            result = await self._delete(
                principal,
                object_type=object_type,
                query_xml=query_xml,
                cascade=options.cascaded_delete,
            )
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
        self,
        principal: Principal,
        *,
        object_type: str,
        query_xml: str,
        cascade: bool = False,
    ) -> StoreResult:
        if object_type not in WRITABLE_TYPES:
            raise WitsmlError(WmlsCode.OBJECT_TYPE_NOT_SUPPORTED)
        root = parse_xml(query_xml)
        xd.ensure_namespace(root)
        spec = spec_for(object_type)
        elements = [item for item in root if xd.localname(item) == spec.name]
        if not elements:
            raise WitsmlError(WmlsCode.MISSING_UID)
        prepared_delete: list[
            tuple[etree._Element, str, str | None, str | None, StoredObject]
        ] = []
        # Primera pasada: permisos, existencia, bloqueo y token antes de borrar
        # o modificar nada; un conflicto en un lote no deja cambios parciales.
        for element in elements:
            uid = xd.normalize_uid(xd.attr(element, "uid"))
            if not uid:
                raise WitsmlError(WmlsCode.MISSING_UID)
            uid_well = xd.attr(element, "uidWell")
            uid_wellbore = xd.attr(element, "uidWellbore")
            if object_type == "well":
                uid_well = uid
            if not principal.allows_witsml(
                WitsmlAction.DELETE, object_type, uid_well
            ):
                raise WitsmlError(WmlsCode.INSUFFICIENT_RIGHTS)
            existing = await self._load_existing(
                object_type, uid, uid_well, uid_wellbore, for_update=True
            )
            if existing is None:
                raise WitsmlError(WmlsCode.OBJECT_NOT_EXIST)
            self._require_matching_token(
                xd.last_change_token(element), existing.changed_at, deleting=True
            )
            prepared_delete.append((element, uid, uid_well, uid_wellbore, existing))

        deleted = 0
        modified = 0
        for element, uid, uid_well, uid_wellbore, existing in prepared_delete:
            now = self._clock.now()

            stored = parse_xml(existing.xml)
            xd.ensure_namespace(stored)
            attribute_changed = xd.apply_attribute_deletions(stored, element)
            curve_mnemonics = [
                mnemonic
                for item in xd.children(element, "logCurveInfo")
                if (mnemonic := (xd.text_of(item, "mnemonic") or xd.attr(item, "uid")))
            ]
            start, end = xd.index_bounds(element)
            has_range = xd.has_index_bounds(element)
            is_log = isinstance(existing, LogRecord)
            is_mudlog = isinstance(existing, MudLogRecord)
            mudlog_nodes = (
                xd.mudlog_data_nodes(element) if is_mudlog else []
            )
            partial = (
                attribute_changed
                or (is_log and (curve_mnemonics or has_range))
                or (is_mudlog and bool(mudlog_nodes))
            )

            if not partial:
                deleted_element = stored
                if cascade:
                    deleted += await self._delete_cascade(
                        principal, object_type, existing, now
                    )
                else:
                    await self._assert_no_children(object_type, existing)
                await self._delete_record(object_type, existing)
                await self._record_delete(
                    object_type, existing, now, deleted_element
                )
                deleted += 1
                continue

            if is_log:
                record = existing  # type: ignore[assignment]
                assert isinstance(record, LogRecord)
                if curve_mnemonics:
                    for mnemonic in curve_mnemonics:
                        await self._logs.remove_curve_values(
                            uid, mnemonic, start=start, end=end
                        )
                    if not has_range:
                        # Sin rango: se elimina la curva por completo.
                        record.curves = [
                            curve
                            for curve in record.curves
                            if curve.mnemonic not in curve_mnemonics
                        ]
                        await self._logs.replace_curves(uid, record.curves)
                        for item in list(xd.children(stored, "logCurveInfo")):
                            if (
                                xd.text_of(item, "mnemonic") in curve_mnemonics
                                or xd.attr(item, "uid") in curve_mnemonics
                            ):
                                stored.remove(item)
                elif has_range:
                    await self._logs.delete_samples(uid, start=start, end=end)
                await self._refresh_log_range(record)
            elif is_mudlog:
                record = existing  # type: ignore[assignment]
                assert isinstance(record, MudLogRecord)
                for node in mudlog_nodes:
                    name = xd.localname(node)
                    node_uid = xd.normalize_uid(xd.attr(node, "uid"))
                    for candidate in list(xd.children(stored, name)):
                        if node_uid and (
                            xd.normalize_uid(xd.attr(candidate, "uid")) != node_uid
                        ):
                            continue
                        stored.remove(candidate)
                record.md_min, record.md_max, record.md_uom = xd.mudlog_md_range(
                    stored
                )

            fields = self._fields_for(object_type, stored)
            existing.xml = serialize(stored)
            existing.changed_at = now
            existing.fields = fields
            existing.name = xd.text_of(stored, "name")
            await self._update_repository(object_type, existing)

            start_text = xd.format_index_value(start) if start is not None else None
            end_text = xd.format_index_value(end) if end is not None else None
            await self._change_log.add(
                ChangeLogRecord(
                    uid=uid,
                    object_type=object_type,
                    change_type="update",
                    change_date=now,
                    uid_well=uid_well,
                    uid_wellbore=uid_wellbore,
                    name_object=xd.text_of(stored, "name"),
                    name_well=xd.text_of(stored, "nameWell"),
                    name_wellbore=xd.text_of(stored, "nameWellbore"),
                    mnemonics=",".join(curve_mnemonics) if curve_mnemonics else None,
                    start_index=start_text,
                    end_index=end_text,
                )
            )
            modified += 1
        total = deleted + modified
        return StoreResult(
            code=int(WmlsCode.SUCCESS),
            supp_msg=xd.make_supp_msg([], [f"{total} object(s) deleted."]),
        )

    async def _refresh_log_range(self, record: LogRecord) -> None:
        low, high = await self._logs.sample_range(record.uid)
        if low is None or high is None:
            return
        if record.direction == "decreasing":
            start_value, end_value = high, low
        else:
            start_value, end_value = low, high
        record.start_index_time = self._as_time(start_value, record.index_type)
        record.start_index_value = self._as_decimal(start_value, record.index_type)
        record.end_index_time = self._as_time(end_value, record.index_type)
        record.end_index_value = self._as_decimal(end_value, record.index_type)
        record.fields = dict(record.fields) | {
            "startIndex": xd.format_index_value(record.start_index),
            "endIndex": xd.format_index_value(record.end_index),
        }

    # ------------------------------------------------------------------
    # Utilidades internas
    # ------------------------------------------------------------------
    def _repository(self, object_type: str) -> Any:
        return {
            "well": self._wells,
            "wellbore": self._wellbores,
            "log": self._logs,
            "mudLog": self._mud_logs,
            "trajectory": self._trajectories,
        }[object_type]

    @staticmethod
    def _require_matching_token(
        token: datetime | None, stored: datetime, *, deleting: bool = False
    ) -> None:
        """Aplica la precondición de concurrencia optimista del cliente.

        El token es opcional para no romper a los clientes WITSML 1.4.1 que no
        envían ``dTimLastChange``. Cuando llega, debe coincidir exactamente con
        el valor almacenado; si otra transacción escribió antes, la escritura se
        rechaza sin persistir ni registrar ``changeLog``.
        """
        if token is None or token == stored:
            return
        code = WmlsCode.ERROR_DELETING if deleting else WmlsCode.ERROR_UPDATING
        raise WitsmlError(
            code,
            "dTimLastChange no coincide con el objeto almacenado; "
            "recargue el objeto y reintente.",
        )

    async def _load_existing(
        self,
        object_type: str,
        uid: str,
        uid_well: str | None,
        uid_wellbore: str | None,
        *,
        for_update: bool = False,
    ) -> StoredObject | None:
        if object_type == "well":
            return await self._wells.get(uid, for_update=for_update)
        if object_type == "wellbore":
            return await self._wellbores.get(uid, uid_well, for_update=for_update)
        if object_type == "log":
            return await self._logs.get(
                uid, uid_well, uid_wellbore, for_update=for_update
            )
        if object_type == "mudLog":
            return await self._mud_logs.get(
                uid, uid_well, uid_wellbore, for_update=for_update
            )
        return await self._trajectories.get(
            uid, uid_well, uid_wellbore, for_update=for_update
        )

    async def _update_repository(self, object_type: str, record: StoredObject) -> None:
        if object_type == "well":
            await self._wells.update(record)  # type: ignore[arg-type]
        elif object_type == "wellbore":
            await self._wellbores.update(record)  # type: ignore[arg-type]
        elif object_type == "log":
            await self._logs.update(record)  # type: ignore[arg-type]
        elif object_type == "mudLog":
            await self._mud_logs.update(record)  # type: ignore[arg-type]
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

    async def _delete_record(self, object_type: str, record: StoredObject) -> None:
        """Elimina una fila concreta sin comprobar hijos ni registrar changeLog."""
        if object_type == "well":
            await self._wells.delete(record.uid)
        elif object_type == "wellbore":
            await self._wellbores.delete(record.uid, record.uid_well)
        elif object_type == "log":
            await self._logs.delete(record.uid, record.uid_well, record.uid_wellbore)
        elif object_type == "mudLog":
            await self._mud_logs.delete(
                record.uid, record.uid_well, record.uid_wellbore
            )
        else:
            await self._trajectories.delete(
                record.uid, record.uid_well, record.uid_wellbore
            )

    async def _record_delete(
        self,
        object_type: str,
        record: StoredObject,
        now: datetime,
        element: etree._Element | None = None,
    ) -> None:
        stored = element if element is not None else parse_xml(record.xml)
        xd.ensure_namespace(stored)
        await self._change_log.add(
            ChangeLogRecord(
                uid=record.uid,
                object_type=object_type,
                change_type="delete",
                change_date=now,
                uid_well=record.uid_well,
                uid_wellbore=record.uid_wellbore,
                name_object=xd.text_of(stored, "name"),
                name_well=xd.text_of(stored, "nameWell"),
                name_wellbore=xd.text_of(stored, "nameWellbore"),
            )
        )

    async def _wellbore_children(
        self, uid_well: str | None, uid_wellbore: str
    ) -> list[tuple[str, StoredObject]]:
        """Hijos directos de un wellbore en orden de borrado."""
        children: list[tuple[str, StoredObject]] = []
        for object_type, repository in (
            ("log", self._logs),
            ("mudLog", self._mud_logs),
            ("trajectory", self._trajectories),
        ):
            records = await repository.list(
                ListFilter(uid_well=uid_well, uid_wellbore=uid_wellbore)
            )
            children.extend((object_type, record) for record in records)
        return children

    async def _cascade_plan(
        self, object_type: str, record: StoredObject
    ) -> list[tuple[str, StoredObject]]:
        """Objetos dependientes que deben borrarse antes que ``record``."""
        if object_type == "well":
            plan: list[tuple[str, StoredObject]] = []
            wellbores = await self._wellbores.list(
                ListFilter(uid_well=record.uid)
            )
            for wellbore in wellbores:
                plan.extend(
                    await self._wellbore_children(
                        wellbore.uid_well, wellbore.uid
                    )
                )
                plan.append(("wellbore", wellbore))
            return plan
        if object_type == "wellbore":
            return await self._wellbore_children(record.uid_well, record.uid)
        return []

    async def _delete_cascade(
        self,
        principal: Principal,
        object_type: str,
        record: StoredObject,
        now: datetime,
    ) -> int:
        """Borra los dependientes de ``record`` y devuelve cuántos eliminó."""
        plan = await self._cascade_plan(object_type, record)
        for child_type, child in plan:
            if not principal.allows_witsml(
                WitsmlAction.DELETE, child_type, child.uid_well
            ):
                raise WitsmlError(WmlsCode.INSUFFICIENT_RIGHTS)
        for child_type, child in plan:
            await self._delete_record(child_type, child)
            await self._record_delete(child_type, child, now)
        return len(plan)

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
                    f"Row without value for index curve '{header.index_curve}'.",
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
        low, high = min(present), max(present)
        if header.direction == "decreasing":
            return high, low
        return low, high

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
        if object_type == "mudLog":
            return xd.parse_mudlog_fields(element)
        return xd.parse_trajectory_header(element).fields

    @staticmethod
    def _enforce_write_limits(config: Any, nodes: int, curves: int) -> None:
        if nodes > config.max_data_nodes or nodes * curves > config.max_data_points:
            raise WitsmlError(
                WmlsCode.MAX_DATA_EXCEEDED,
                f"Request exceeds maxDataNodes={config.max_data_nodes} or "
                f"maxDataPoints={config.max_data_points}.",
            )

    @staticmethod
    def _as_time(value: Any, index_type: str) -> datetime | None:
        return value if index_type == "time" and isinstance(value, datetime) else None

    @staticmethod
    def _as_decimal(value: Any, index_type: str) -> Decimal | None:
        return value if index_type != "time" and isinstance(value, Decimal) else None

    @staticmethod
    def _last_value(items: list[Any], attribute: str) -> str | None:
        for item in reversed(items):
            value = getattr(item, attribute)
            if value:
                return value
        return None

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
