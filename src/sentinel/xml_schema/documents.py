"""Lectura, normalización y fusión de documentos WITSML.

Este módulo no conoce la base de datos ni HTTP. Traduce entre el XML WITSML
1.4.1.1 y las estructuras de dominio del núcleo.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import parse_qs

from lxml import etree

from sentinel import SCHEMA_VERSION
from sentinel.shared.errors import ValidationError
from sentinel.xml_schema.namespaces import WITSML, WITSML_NS
from sentinel.xml_schema.objects import ObjectSpec, spec_for

SERVER_MANAGED_ATTRIBUTES = frozenset({"dTimCreation", "dTimLastChange"})
SERVER_MANAGED_CHILDREN = frozenset({"objectGrowing"})
DATA_CHILDREN = frozenset({"logData", "logCurveInfo", "trajectoryStation"})
SERVER_MANAGED_ALL = SERVER_MANAGED_ATTRIBUTES | SERVER_MANAGED_CHILDREN

TEXT_FILTERS: dict[str, tuple[str, ...]] = {
    "well": ("name", "field", "country", "operator", "statusWell", "purposeWell"),
    "wellbore": (
        "name",
        "purposeWellbore",
        "statusWellbore",
        "typeWellbore",
        "shape",
    ),
    "log": ("name", "indexType", "serviceCompany"),
    "trajectory": ("name", "serviceCompany"),
}


def localname(element: etree._Element) -> str:
    tag = element.tag
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1]


def namespace_of(element: etree._Element) -> str | None:
    tag = element.tag
    if isinstance(tag, str) and tag.startswith("{"):
        return tag[1:].split("}", 1)[0]
    return None


def ensure_namespace(element: etree._Element) -> None:
    """Asigna el namespace WITSML a etiquetas sin namespace.

    El XSD oficial exige el namespace; esta normalización evita rechazar
    clientes que envían XML sin prefijo pero con estructura correcta.
    """
    if isinstance(element.tag, str) and not element.tag.startswith("{"):
        element.tag = f"{WITSML}{localname(element)}"
    for child in element:
        ensure_namespace(child)


def child(element: etree._Element, name: str) -> etree._Element | None:
    for item in element:
        if localname(item) == name:
            return item
    return None


def children(element: etree._Element, name: str) -> list[etree._Element]:
    return [item for item in element if localname(item) == name]


def text_of(element: etree._Element, name: str) -> str | None:
    item = child(element, name)
    if item is None or item.text is None:
        return None
    value = item.text.strip()
    return value or None


def attr(element: etree._Element, name: str) -> str | None:
    value = element.get(name)
    return value.strip() if value else None


def set_child_text(element: etree._Element, name: str, value: str) -> None:
    item = child(element, name)
    if item is None:
        item = etree.SubElement(element, f"{WITSML}{name}")
    item.text = value


def set_attr(element: etree._Element, name: str, value: str) -> None:
    element.set(name, value)


def parse_index_value(raw: str | None, index_type: str) -> datetime | Decimal | None:
    if raw is None:
        return None
    value = raw.strip()
    if not value:
        return None
    if index_type == "time":
        return parse_iso_datetime(value)
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise ValidationError(f"Índice numérico inválido: {raw}") from exc


# Valores oficiales de ``LogIndexType`` en WITSML 1.4.1.1. ``time`` y ``depth``
# se conservan como alias de versiones anteriores del cliente.
_INDEX_TYPE_ALIASES: dict[str, str] = {
    "date time": "time",
    "time": "time",
    "elapsed time": "elapsed time",
    "length": "length",
    "measured depth": "measured depth",
    "depth": "measured depth",
    "vertical depth": "vertical depth",
    "none": "none",
    "other": "other",
    "unknown": "unknown",
}


def normalize_index_type(raw: str | None) -> str | None:
    """Normaliza ``indexType`` al vocabulario interno del Store."""
    if raw is None:
        return None
    return _INDEX_TYPE_ALIASES.get(raw.strip().lower())


def parse_iso_datetime(raw: str) -> datetime:
    value = raw.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError(f"Fecha/hora inválida: {raw}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def format_datetime(value: datetime) -> str:
    value = value.astimezone(UTC)
    return value.strftime("%Y-%m-%dT%H:%M:%S.") + f"{value.microsecond // 1000:03d}Z"


def format_index_value(value: datetime | Decimal | None) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return format_datetime(value)
    return format(value, "f")


def normalize_uid(value: str | None) -> str | None:
    if value is None:
        return None
    uid = value.strip()
    if not uid:
        return None
    if len(uid) > 128:
        raise ValidationError("El UID excede 128 caracteres.")
    if any(ord(ch) < 32 for ch in uid):
        raise ValidationError("El UID contiene caracteres de control.")
    return uid


@dataclass(frozen=True)
class LogCurveDef:
    mnemonic: str
    unit: str | None = None
    curve_type: str | None = None
    is_index: bool = False
    description: str | None = None
    uid: str | None = None


@dataclass
class LogDataBlock:
    mnemonics: list[str] = field(default_factory=list)
    units: list[str] = field(default_factory=list)
    rows: list[dict[str, str | None]] = field(default_factory=list)


@dataclass
class LogHeader:
    index_type: str
    index_curve: str
    direction: str
    start_index: datetime | Decimal | None
    end_index: datetime | Decimal | None
    start_uom: str | None
    end_uom: str | None
    curves: list[LogCurveDef]
    fields: dict[str, Any]


@dataclass
class TrajectoryHeader:
    md_min: Decimal | None
    md_max: Decimal | None
    md_uom: str | None
    fields: dict[str, Any]


@dataclass
class TrajectoryStationInput:
    order: int
    md: Decimal | None
    incl: Decimal | None
    azi: Decimal | None
    tvd: Decimal | None
    xml: str


def parse_well_fields(element: etree._Element) -> dict[str, Any]:
    return {
        name: value
        for name in TEXT_FILTERS["well"]
        if (value := text_of(element, name)) is not None
    }


def parse_wellbore_fields(element: etree._Element) -> dict[str, Any]:
    return {
        name: value
        for name in TEXT_FILTERS["wellbore"]
        if (value := text_of(element, name)) is not None
    }


def parse_log_header(element: etree._Element) -> LogHeader:
    index_type = normalize_index_type(text_of(element, "indexType"))
    if not index_type:
        raise ValidationError("El log requiere un indexType válido.")
    index_curve = text_of(element, "indexCurve")
    if not index_curve:
        raise ValidationError("El log requiere indexCurve.")
    direction = (text_of(element, "direction") or "increasing").lower()
    if direction not in ("increasing", "decreasing"):
        raise ValidationError("direction debe ser increasing o decreasing.")

    start_el = child(element, "startIndex")
    end_el = child(element, "endIndex")
    start_index = parse_index_value(start_el.text if start_el is not None else None, index_type)
    end_index = parse_index_value(end_el.text if end_el is not None else None, index_type)
    curves = parse_log_curves(element, index_curve=index_curve)
    return LogHeader(
        index_type=index_type,
        index_curve=index_curve,
        direction=direction,
        start_index=start_index,
        end_index=end_index,
        start_uom=start_el.get("uom") if start_el is not None else None,
        end_uom=end_el.get("uom") if end_el is not None else None,
        curves=curves,
        fields={
            name: value
            for name in TEXT_FILTERS["log"]
            if (value := text_of(element, name)) is not None
        }
        | {"indexType": index_type, "indexCurve": index_curve, "direction": direction},
    )


def parse_log_curves(
    element: etree._Element, *, index_curve: str | None = None
) -> list[LogCurveDef]:
    result: list[LogCurveDef] = []
    for item in children(element, "logCurveInfo"):
        mnemonic = text_of(item, "mnemonic")
        if not mnemonic:
            raise ValidationError("logCurveInfo requiere mnemonic.")
        # El esquema oficial 1.4.1.1 no tiene ``isIndex``: la curva de índice se
        # identifica porque su mnemónico coincide con ``indexCurve``. Se acepta
        # ``isIndex`` solo como compatibilidad de entrada.
        legacy_index = (text_of(item, "isIndex") or "false").lower() == "true"
        is_index = (
            mnemonic == index_curve if index_curve is not None else legacy_index
        )
        result.append(
            LogCurveDef(
                mnemonic=mnemonic,
                unit=text_of(item, "unit"),
                curve_type=text_of(item, "curveType"),
                is_index=is_index,
                description=text_of(item, "description"),
                uid=attr(item, "uid"),
            )
        )
    return result


def parse_log_data(element: etree._Element) -> LogDataBlock:
    log_data = child(element, "logData")
    if log_data is None:
        return LogDataBlock()
    mnemonic_list = text_of(log_data, "mnemonicList")
    if not mnemonic_list:
        raise ValidationError("logData requiere mnemonicList.")
    mnemonics = [part.strip() for part in mnemonic_list.split(",")]
    unit_list = text_of(log_data, "unitList") or ""
    units = [part.strip() for part in unit_list.split(",")] if unit_list else []
    data_el = child(log_data, "data")
    rows: list[dict[str, str | None]] = []
    if data_el is not None and data_el.text:
        for line in data_el.text.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            values = [part.strip() for part in line.split(",")]
            if len(values) != len(mnemonics):
                raise ValidationError(
                    "Cada fila de logData debe tener un valor por mnemonic "
                    f"({len(mnemonics)}), recibidos {len(values)}."
                )
            rows.append(
                {
                    mnemonic: (value if value != "" else None)
                    for mnemonic, value in zip(mnemonics, values, strict=True)
                }
            )
    return LogDataBlock(mnemonics=mnemonics, units=units, rows=rows)


def parse_trajectory_header(element: etree._Element) -> TrajectoryHeader:
    md_min_el = child(element, "mdMn")
    if md_min_el is None:
        md_min_el = child(element, "mdStart")
    md_max_el = child(element, "mdMx")
    if md_max_el is None:
        md_max_el = child(element, "mdEnd")
    return TrajectoryHeader(
        md_min=_decimal(md_min_el.text if md_min_el is not None else None),
        md_max=_decimal(md_max_el.text if md_max_el is not None else None),
        md_uom=md_min_el.get("uom") if md_min_el is not None else None,
        fields={
            name: value
            for name in TEXT_FILTERS["trajectory"]
            if (value := text_of(element, name)) is not None
        },
    )


def parse_trajectory_stations(element: etree._Element) -> list[TrajectoryStationInput]:
    stations: list[TrajectoryStationInput] = []
    for order, station in enumerate(children(element, "trajectoryStation")):
        stations.append(
            TrajectoryStationInput(
                order=order,
                md=_child_decimal(station, "md"),
                incl=_child_decimal(station, "incl"),
                azi=_child_decimal(station, "azi"),
                tvd=_child_decimal(station, "tvd"),
                xml=etree.tostring(station, encoding="unicode"),
            )
        )
    return stations


def _child_decimal(element: etree._Element, name: str) -> Decimal | None:
    item = child(element, name)
    return _decimal(item.text if item is not None else None)


def _decimal(raw: str | None) -> Decimal | None:
    if raw is None or not raw.strip():
        return None
    try:
        return Decimal(raw.strip())
    except InvalidOperation as exc:
        raise ValidationError(f"Valor numérico inválido: {raw}") from exc


@dataclass
class ObjectQuery:
    uid: str | None = None
    uid_well: str | None = None
    uid_wellbore: str | None = None
    text_filters: dict[str, str] = field(default_factory=dict)
    start_index: datetime | Decimal | None = None
    end_index: datetime | Decimal | None = None
    md_min: Decimal | None = None
    md_max: Decimal | None = None
    change_type: str | None = None
    object_type: str | None = None
    latest_values: int | None = None


@dataclass(frozen=True)
class QueryOptions:
    return_elements: str = "all"
    request_latest_values: int | None = None
    max_return_nodes: int | None = None


def option_value(options: str | None, name: str) -> str | None:
    """Extrae un keyword de ``OptionsIn``.

    El API oficial transporta las opciones como
    ``application/x-www-form-urlencoded`` (por ejemplo
    ``dataVersion=1.4.1.1&returnElements=all``). Se acepta además el formato
    XML usado por clientes antiguos.
    """
    if not options or not options.strip():
        return None
    text = options.strip()
    if text.startswith("<"):
        from sentinel.xml_schema.parser import parse_xml

        try:
            root = parse_xml(text)
        except ValidationError:
            return None
        return text_of(root, name)
    values = parse_qs(text, keep_blank_values=True)
    raw = values.get(name)
    if not raw:
        return None
    value = raw[0].strip()
    return value or None


def parse_options(options_xml: str | None) -> QueryOptions:
    return_elements = (option_value(options_xml, "returnElements") or "all").lower()
    latest = option_value(options_xml, "requestLatestValues")
    max_nodes = option_value(options_xml, "maxReturnNodes")
    return QueryOptions(
        return_elements=return_elements,
        request_latest_values=int(latest) if latest and latest.isdigit() else None,
        max_return_nodes=int(max_nodes) if max_nodes and max_nodes.isdigit() else None,
    )


_TRAJECTORY_PLURALS = frozenset({"trajectorys", "trajectories"})


def parse_queries(
    query_xml: str,
    object_type: str,
    *,
    index_type: str = "time",
) -> list[ObjectQuery]:
    """Convierte ``QueryIn`` en filtros de dominio.

    Acepta un documento vacío (``<wells/>``) como "todos los objetos
    autorizados". Los filtros de texto son comparación sin distinguir
    mayúsculas; el adaptador de persistencia la aplica.
    """
    from sentinel.xml_schema.parser import parse_xml

    root = parse_xml(query_xml)
    ensure_namespace(root)
    spec = spec_for(object_type)
    accepted_plurals = (
        _TRAJECTORY_PLURALS
        if object_type == "trajectory"
        else frozenset({spec.plural})
    )
    if localname(root) not in accepted_plurals:
        raise ValidationError(
            f"QueryIn debe tener raíz <{spec.plural}> para {object_type}."
        )
    defaults = {
        "uid_well": attr(root, "uidWell"),
        "uid_wellbore": attr(root, "uidWellbore"),
    }
    queries = [
        _parse_query_element(item, object_type, index_type, defaults)
        for item in root
        if localname(item) == spec.name
    ]
    if not queries:
        queries.append(
            ObjectQuery(
                uid_well=defaults["uid_well"],
                uid_wellbore=defaults["uid_wellbore"],
            )
        )
    return queries


def _parse_query_element(
    element: etree._Element,
    object_type: str,
    index_type: str,
    defaults: dict[str, str | None],
) -> ObjectQuery:
    uid_well = attr(element, "uidWell") or defaults.get("uid_well")
    uid_wellbore = attr(element, "uidWellbore") or defaults.get("uid_wellbore")
    if object_type == "well":
        uid_well = attr(element, "uid") or uid_well
    text_filters = {
        name: value
        for name in TEXT_FILTERS.get(object_type, ())
        if (value := text_of(element, name)) is not None
    }
    start_index = _index_filter(element, ("startIndex", "startDateTimeIndex"), index_type)
    end_index = _index_filter(element, ("endIndex", "endDateTimeIndex"), index_type)
    latest = attr(element, "requestLatestValues")
    return ObjectQuery(
        uid=attr(element, "uid"),
        uid_well=uid_well,
        uid_wellbore=uid_wellbore,
        text_filters=text_filters,
        start_index=start_index,
        end_index=end_index,
        md_min=_child_decimal(element, "mdMn"),
        md_max=_child_decimal(element, "mdMx"),
        change_type=text_of(element, "changeType"),
        object_type=text_of(element, "objectType"),
        latest_values=int(latest) if latest and latest.isdigit() else None,
    )


def _index_filter(
    element: etree._Element, names: tuple[str, ...], index_type: str
) -> datetime | Decimal | None:
    for name in names:
        item = child(element, name)
        if item is not None and item.text and item.text.strip():
            effective = "time" if name.endswith("DateTimeIndex") else index_type
            return parse_index_value(item.text, effective)
    return None


def merge_header(stored: etree._Element, incoming: etree._Element) -> etree._Element:
    """Fusiona un update de cabecera preservando UID y campos del servidor.

    Los elementos de datos (``logData``, ``logCurveInfo``, ``trajectoryStation``)
    se procesan por separado en el caso de uso.
    """
    merged = copy.deepcopy(stored)
    for name, value in incoming.attrib.items():
        if name in SERVER_MANAGED_ATTRIBUTES or name in ("uid", "uidWell", "uidWellbore"):
            continue
        merged.set(name, value)
    for item in incoming:
        name = localname(item)
        if name in DATA_CHILDREN or name in SERVER_MANAGED_CHILDREN:
            continue
        existing = children(merged, name)
        if existing:
            for old in existing:
                merged.replace(old, copy.deepcopy(item))
        else:
            merged.append(copy.deepcopy(item))
    return merged


def apply_server_fields(
    element: etree._Element,
    *,
    created_at: datetime,
    changed_at: datetime,
    growing: bool,
) -> None:
    common = child(element, "commonData")
    if common is None:
        common = etree.Element(f"{WITSML}commonData")
        custom = child(element, "customData")
        if custom is not None:
            element.insert(element.index(custom), common)
        else:
            element.append(common)
    _set_common_data_text(common, "dTimCreation", format_datetime(created_at))
    _set_common_data_text(common, "dTimLastChange", format_datetime(changed_at))
    name = localname(element)
    if name in ("log", "trajectory"):
        value = "true" if growing else "false"
        existing = child(element, "objectGrowing")
        if existing is not None:
            existing.text = value
        else:
            item = etree.Element(f"{WITSML}objectGrowing")
            item.text = value
            element.insert(_growing_position(element), item)


def _growing_position(element: etree._Element) -> int:
    """Posición de ``objectGrowing`` dentro de ``grp_log``/``grp_trajectory``."""
    contextual = {"nameWell", "nameWellbore", "name"}
    for index, candidate in enumerate(element):
        if localname(candidate) not in contextual:
            return index
    return len(element)


_COMMON_DATA_ORDER: tuple[str, ...] = (
    "sourceName",
    "dTimCreation",
    "dTimLastChange",
    "itemState",
    "serviceCategory",
    "comments",
    "acquisitionTimeZone",
    "defaultDatum",
    "privateGroupOnly",
    "extensionAny",
    "extensionNameValue",
)


def _set_common_data_text(
    common: etree._Element, name: str, value: str
) -> None:
    existing = child(common, name)
    if existing is not None:
        existing.text = value
        return
    item = etree.Element(f"{WITSML}{name}")
    item.text = value
    position = len(common)
    wanted = _COMMON_DATA_ORDER.index(name)
    for index, candidate in enumerate(common):
        candidate_name = localname(candidate)
        if (
            candidate_name in _COMMON_DATA_ORDER
            and _COMMON_DATA_ORDER.index(candidate_name) > wanted
        ):
            position = index
            break
    common.insert(position, item)


def contextual_names(
    element: etree._Element,
) -> tuple[str | None, str | None, str | None]:
    """Devuelve ``(nameWell, nameWellbore, name)`` del objeto cambiado."""
    return (
        text_of(element, "nameWell"),
        text_of(element, "nameWellbore"),
        text_of(element, "name"),
    )


def strip_server_fields(element: etree._Element) -> None:
    for name in SERVER_MANAGED_ATTRIBUTES:
        element.attrib.pop(name, None)
    common = child(element, "commonData")
    if common is not None:
        for item in list(common):
            if localname(item) in SERVER_MANAGED_ATTRIBUTES:
                common.remove(item)
    for item in list(element):
        if localname(item) in SERVER_MANAGED_CHILDREN:
            element.remove(item)


def strip_data_children(element: etree._Element) -> None:
    for item in list(element):
        if localname(item) in DATA_CHILDREN:
            element.remove(item)


def strip_payload(element: etree._Element) -> None:
    """Elimina solo los bloques de datos masivos, conservando la metadata."""
    for item in list(element):
        if localname(item) in ("logData", "trajectoryStation"):
            element.remove(item)


def validate_object_element(object_type: str, element: etree._Element) -> None:
    spec: ObjectSpec = spec_for(object_type)
    if localname(element) != spec.name:
        raise ValidationError(
            f"Se esperaba <{spec.name}> y se recibió <{localname(element)}>."
        )
    uid = normalize_uid(attr(element, "uid"))
    if object_type != "well" and not uid:
        raise ValidationError(f"{object_type} requiere uid.")
    if object_type in ("wellbore", "log", "trajectory") and not attr(element, "uidWell"):
        raise ValidationError(f"{object_type} requiere uidWell.")
    if object_type in ("log", "trajectory") and not attr(element, "uidWellbore"):
        raise ValidationError(f"{object_type} requiere uidWellbore.")
    if object_type == "log":
        index_type = normalize_index_type(text_of(element, "indexType"))
        if not index_type:
            raise ValidationError("log requiere un indexType válido.")
        index_curve = text_of(element, "indexCurve")
        if not index_curve:
            raise ValidationError("log requiere indexCurve.")
        curves = parse_log_curves(element, index_curve=index_curve)
        if curves:
            index_curves = [curve for curve in curves if curve.is_index]
            if len(index_curves) != 1:
                raise ValidationError(
                    "log requiere una curva de índice cuyo mnemónico coincida "
                    "con indexCurve."
                )
    if object_type == "trajectory":
        parse_trajectory_stations(element)


def build_log_data(
    mnemonics: list[str], units: list[str], rows: list[list[str]]
) -> etree._Element:
    log_data = etree.Element(f"{WITSML}logData")
    mnemonic_list = etree.SubElement(log_data, f"{WITSML}mnemonicList")
    mnemonic_list.text = ",".join(mnemonics)
    unit_list = etree.SubElement(log_data, f"{WITSML}unitList")
    unit_list.text = ",".join(units)
    data = etree.SubElement(log_data, f"{WITSML}data")
    data.text = "\n" + "\n".join(",".join(row) for row in rows) + "\n"
    return log_data


def apply_return_elements(element: etree._Element, mode: str) -> etree._Element:
    result = copy.deepcopy(element)
    if mode == "id-only":
        for item in list(result):
            result.remove(item)
    elif mode == "header-only":
        strip_payload(result)
    elif mode == "data-only":
        for item in list(result):
            if localname(item) != "logData":
                result.remove(item)
    elif mode == "station-location-only":
        for station in children(result, "trajectoryStation"):
            for item in list(station):
                if localname(item) not in ("md", "incl", "azi", "tvd"):
                    station.remove(item)
    return result


def new_container(object_type: str) -> etree._Element:
    spec = spec_for(object_type)
    return etree.Element(
        f"{WITSML}{spec.plural}",
        nsmap={None: WITSML_NS},
        version=SCHEMA_VERSION,
    )


_TRAILING_OBJECT_CHILDREN = frozenset({"commonData", "customData"})


def append_group_child(
    element: etree._Element, group_child: etree._Element
) -> None:
    """Inserta un hijo del grupo WITSML antes de ``commonData``/``customData``.

    El XSD oficial exige que ``logData``, ``trajectoryStation`` y el resto de
    elementos de grupo precedan a los contenedores comunes del objeto.
    """
    position = len(element)
    for index, candidate in enumerate(element):
        if localname(candidate) in _TRAILING_OBJECT_CHILDREN:
            position = index
            break
    element.insert(position, group_child)


def make_supp_msg(uids: list[str], messages: list[str] | None = None) -> str:
    root = etree.Element("suppMsgOut")
    for uid in uids:
        item = etree.SubElement(root, "uid")
        item.text = uid
    for message in messages or ():
        item = etree.SubElement(root, "message")
        item.text = message
    return etree.tostring(root, encoding="unicode")
