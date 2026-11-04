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
DATA_CHILDREN = frozenset(
    {"logData", "logCurveInfo", "trajectoryStation", "geologyInterval", "parameter"}
)
#: Nodos de datos de ``mudLog`` (objeto de crecimiento aleatorio).
MUDLOG_DATA_CHILDREN = ("parameter", "geologyInterval")
SERVER_MANAGED_ALL = SERVER_MANAGED_ATTRIBUTES | SERVER_MANAGED_CHILDREN

TEXT_FILTERS: dict[str, tuple[str, ...]] = {
    "well": (
        "name",
        "field",
        "country",
        "operator",
        "statusWell",
        "purposeWell",
        "numGovt",
        "numAPI",
    ),
    "wellbore": (
        "name",
        "purposeWellbore",
        "statusWellbore",
        "typeWellbore",
        "shape",
    ),
    "log": ("name", "indexType", "serviceCompany"),
    "mudLog": ("name", "mudLogCompany", "mudLogEngineers"),
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
    # El API compara ``dTimLastChange``/``dTimCreation`` por "mayor que". Si se
    # truncan los microsegundos, el valor leído por el cliente queda por debajo
    # del almacenado y una consulta con ese mismo instante vuelve a incluir el
    # objeto. Se conserva la precisión completa cuando existe.
    if value.microsecond:
        return value.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"
    return value.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def format_index_value(value: datetime | Decimal | None) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return format_datetime(value)
    # ``wcmp`` compara dobles con tolerancia, pero ``log_verify`` compara los
    # valores de índice como cadenas exactas. Se eliminan ceros/notación
    # científica conservando la representación decimal canónica.
    return format(value.normalize(), "f")


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


def parse_mudlog_fields(element: etree._Element) -> dict[str, Any]:
    return {
        name: value
        for name in TEXT_FILTERS["mudLog"]
        if (value := text_of(element, name)) is not None
    }


def mudlog_md_range(
    element: etree._Element,
) -> tuple[Decimal | None, Decimal | None, str | None]:
    """Rango estructural declarado por ``startMd``/``endMd``."""
    start = child(element, "startMd")
    end = child(element, "endMd")
    md_min = _decimal(start.text if start is not None else None)
    md_max = _decimal(end.text if end is not None else None)
    uom = start.get("uom") if start is not None else None
    return md_min, md_max, uom


def parse_object_growing(element: etree._Element) -> bool:
    """Lee ``objectGrowing`` sin confundirlo con un campo administrado."""
    return _boolean_text(text_of(element, "objectGrowing")) is True


def mudlog_data_nodes(element: etree._Element) -> list[etree._Element]:
    return [item for item in element if localname(item) in MUDLOG_DATA_CHILDREN]


def merge_mudlog_nodes(
    merged: etree._Element, incoming: etree._Element
) -> bool:
    """Fusiona ``parameter`` y ``geologyInterval`` por ``uid``.

    Un nodo existente se actualiza campo a campo; uno nuevo se inserta en el
    orden del XSD. Devuelve ``True`` si la actualización trae nodos de datos.
    """
    changed = False
    for source in mudlog_data_nodes(incoming):
        name = localname(source)
        uid = normalize_uid(attr(source, "uid"))
        target = None
        if uid:
            for candidate in children(merged, name):
                if normalize_uid(attr(candidate, "uid")) == uid:
                    target = candidate
                    break
        if target is None:
            _insert_ordered(merged, copy.deepcopy(source), _MUDLOG_CHILD_ORDER)
        else:
            merge_header(target, source)
        changed = True
    return changed


def filter_mudlog_md_range(
    element: etree._Element, md_min: Decimal | None, md_max: Decimal | None
) -> None:
    """Descarta nodos de datos fuera del rango MD solicitado."""
    if md_min is None and md_max is None:
        return
    for node in mudlog_data_nodes(element):
        values = [
            value
            for value in (_child_decimal(node, "mdTop"), _child_decimal(node, "mdBottom"))
            if value is not None
        ]
        if not values:
            continue
        low, high = min(values), max(values)
        if (md_min is not None and high < md_min) or (
            md_max is not None and low > md_max
        ):
            element.remove(node)


def trim_mudlog_nodes(element: etree._Element, allowed: int) -> bool:
    """Recorta los nodos de datos que exceden el presupuesto de la respuesta."""
    nodes = mudlog_data_nodes(element)
    if allowed <= 0:
        for node in nodes:
            element.remove(node)
        return bool(nodes)
    if len(nodes) <= allowed:
        return False
    for node in nodes[allowed:]:
        element.remove(node)
    return True


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
    rows: list[dict[str, str | None]] = []
    # ``data`` es repetible en el esquema oficial (maxOccurs="unbounded"): cada
    # elemento puede contener una fila o varias separadas por saltos de línea.
    for data_el in children(log_data, "data"):
        if not data_el.text:
            continue
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


@dataclass(frozen=True)
class SelectionItem:
    """Elemento pedido explícitamente en la plantilla de consulta.

    ``returnElements=requested`` (el valor por defecto del API) devuelve sólo
    los elementos y atributos escritos en la plantilla. Los hijos se modelan en
    árbol para respetar selecciones anidadas como
    ``<commonData><dTimLastChange/></commonData>``. Un elemento sin hijos
    selecciona el nodo completo (por ejemplo ``<parameter uid="..."/>``), y
    ``uid`` permite emparejar nodos repetidos.
    """

    name: str
    uid: str | None = None
    children: tuple[SelectionItem, ...] = ()


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
    created_after: datetime | None = None
    changed_after: datetime | None = None
    object_growing: bool | None = None
    selection_items: frozenset[str] = frozenset()
    selection: tuple[SelectionItem, ...] = ()


@dataclass(frozen=True)
class QueryOptions:
    return_elements: str = "requested"
    request_latest_values: int | None = None
    max_return_nodes: int | None = None
    request_object_selection: bool = False
    cascaded_delete: bool = False


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
    values = parse_qs(text.replace(";", "&"), keep_blank_values=True)
    raw = values.get(name)
    if not raw:
        return None
    value = raw[0].strip()
    return value or None


def option_names(options: str | None) -> tuple[str, ...]:
    """Devuelve los keywords presentes en ``OptionsIn``.

    Se usa para validar combinaciones de opciones (por ejemplo, que
    ``requestObjectSelectionCapability`` no conviva con otro keyword). Acepta
    el formato URL-encoded oficial y el formato XML de clientes antiguos.
    """
    if not options or not options.strip():
        return ()
    text = options.strip()
    if text.startswith("<"):
        from sentinel.xml_schema.parser import parse_xml

        try:
            root = parse_xml(text)
        except ValidationError:
            return ()
        return tuple(localname(item) for item in root)
    values = parse_qs(text.replace(";", "&"), keep_blank_values=True)
    return tuple(values)


def parse_options(options_xml: str | None) -> QueryOptions:
    return_elements = (
        option_value(options_xml, "returnElements") or "requested"
    ).lower()
    latest = option_value(options_xml, "requestLatestValues")
    max_nodes = option_value(options_xml, "maxReturnNodes")
    selection = option_value(options_xml, "requestObjectSelectionCapability")
    cascaded = option_value(options_xml, "cascadedDelete")
    return QueryOptions(
        return_elements=return_elements,
        request_latest_values=int(latest) if latest and latest.isdigit() else None,
        max_return_nodes=int(max_nodes) if max_nodes and max_nodes.isdigit() else None,
        request_object_selection=selection is not None
        and selection.strip().lower() != "none",
        cascaded_delete=str(cascaded).strip().lower() == "true"
        if cascaded is not None
        else False,
    )


_TRAJECTORY_PLURALS = frozenset({"trajectorys", "trajectories"})

#: Atributos de la raíz que identifican un objeto concreto en una consulta.
_QUERY_SCOPE_ATTRIBUTES = ("uidWell", "uidWellbore", "uid")


def is_minimum_query(query_xml: str, object_type: str) -> bool:
    """Comprueba que ``QueryIn`` sea la Minimum Query Template.

    La API 1.4.1 §6.6.2.1 exige, cuando
    ``requestObjectSelectionCapability`` tiene un valor distinto de ``none``,
    una plantilla mínima: la raíz plural y, como mucho, un elemento vacío del
    objeto (por ejemplo ``<wells><well/></wells>``).
    """
    if not query_xml or not query_xml.strip():
        return False
    from sentinel.xml_schema.parser import parse_xml

    try:
        root = parse_xml(query_xml)
    except ValidationError:
        return False
    ensure_namespace(root)
    spec = spec_for(object_type)
    accepted_plurals = (
        _TRAJECTORY_PLURALS
        if object_type == "trajectory"
        else frozenset({spec.plural})
    )
    if localname(root) not in accepted_plurals:
        return False
    if any(attr(root, name) for name in _QUERY_SCOPE_ATTRIBUTES):
        return False
    items = [item for item in root if localname(item) == spec.name]
    if len(items) != len(root) or len(items) > 1:
        return False
    return all(len(item) == 0 and not item.attrib for item in items)


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
    common = child(element, "commonData")
    created_after = _common_datetime(common, "dTimCreation")
    changed_after = _common_datetime(common, "dTimLastChange")
    latest = attr(element, "requestLatestValues")
    selection_items = _selection_items(element)
    selection = _selection_tree(element)
    object_growing = _boolean_text(text_of(element, "objectGrowing"))

    if object_type == "changeLog":
        history = child(element, "changeHistory")
        change_type = None
        start_index: datetime | Decimal | None = None
        if history is not None:
            change_type = text_of(history, "changeType")
            start_index = _common_datetime(history, "dTimChange")
        if change_type is None:
            change_type = text_of(element, "changeType")
        return ObjectQuery(
            uid=attr(element, "uidObject") or attr(element, "uid"),
            uid_well=uid_well,
            uid_wellbore=uid_wellbore,
            change_type=change_type,
            object_type=text_of(element, "objectType"),
            start_index=start_index,
            created_after=created_after,
            changed_after=changed_after,
            selection_items=selection_items,
            selection=selection,
        )

    start_index = _index_filter(element, ("startIndex", "startDateTimeIndex"), index_type)
    end_index = _index_filter(element, ("endIndex", "endDateTimeIndex"), index_type)
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
        created_after=created_after,
        changed_after=changed_after,
        object_growing=object_growing,
        selection_items=selection_items,
        selection=selection,
    )


def _boolean_text(raw: str | None) -> bool | None:
    if raw is None:
        return None
    value = raw.strip().lower()
    if value in ("true", "1"):
        return True
    if value in ("false", "0"):
        return False
    return None


def _selection_items(element: etree._Element) -> frozenset[str]:
    """Elementos de selección usados en la plantilla de consulta.

    ``returnElements`` solicita elementos "adicionales" a los de selección, por
    lo que éstos deben seguir presentes en la respuesta aunque el modo sea
    ``id-only`` o ``data-only`` (WITSML STORE API §6.6.2.1).
    """
    items = {
        localname(item) for item in element if localname(item) in _SELECTION_ITEMS
    }
    common = child(element, "commonData")
    if common is not None and child(common, "dTimLastChange") is not None:
        items.add("dTimLastChange")
    return frozenset(items)


def _selection_tree(element: etree._Element) -> tuple[SelectionItem, ...]:
    """Árbol de elementos pedidos explícitamente en la plantilla."""
    return tuple(
        SelectionItem(
            name=localname(item),
            uid=normalize_uid(attr(item, "uid")),
            children=_selection_tree(item),
        )
        for item in element
    )


def _common_datetime(common: etree._Element | None, name: str) -> datetime | None:
    """``dTimCreation``/``dTimLastChange`` filtran por comparación "mayor que"."""
    if common is None:
        return None
    value = text_of(common, name)
    if value is None:
        return None
    return parse_iso_datetime(value)


def _index_filter(
    element: etree._Element, names: tuple[str, ...], index_type: str
) -> datetime | Decimal | None:
    for name in names:
        item = child(element, name)
        if item is not None and item.text and item.text.strip():
            # ``startIndex``/``endIndex`` son numéricos por definición; sólo
            # ``startDateTimeIndex``/``endDateTimeIndex`` son marcas de tiempo.
            effective = "time" if name.endswith("DateTimeIndex") else "numeric"
            return parse_index_value(item.text, effective)
    return None


def index_bounds(
    element: etree._Element,
) -> tuple[datetime | Decimal | None, datetime | Decimal | None]:
    """Rango de índices de una plantilla de borrado/consulta."""
    return (
        _index_filter(element, ("startIndex", "startDateTimeIndex"), "time"),
        _index_filter(element, ("endIndex", "endDateTimeIndex"), "time"),
    )


def has_index_bounds(element: etree._Element) -> bool:
    return any(
        child(element, name) is not None
        for name in (
            "startIndex",
            "endIndex",
            "startDateTimeIndex",
            "endDateTimeIndex",
        )
    )


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
    order = _order_for(merged)
    for item in incoming:
        name = localname(item)
        if name in DATA_CHILDREN or name in SERVER_MANAGED_CHILDREN:
            continue
        existing = children(merged, name)
        if existing:
            for old in existing:
                merged.replace(old, copy.deepcopy(item))
        else:
            new_item = copy.deepcopy(item)
            if order is not None:
                _insert_ordered(merged, new_item, order)
            else:
                position = len(merged)
                for index, candidate in enumerate(merged):
                    if localname(candidate) in _TRAILING_OBJECT_CHILDREN:
                        position = index
                        break
                merged.insert(position, new_item)
    return merged


def _order_for(element: etree._Element) -> tuple[str, ...] | None:
    name = localname(element)
    if name == "log":
        return _LOG_CHILD_ORDER
    if name in ("mudLog", "mudLogs"):
        return _MUDLOG_CHILD_ORDER
    if name in ("trajectory", "trajectorys"):
        return _TRAJECTORY_CHILD_ORDER
    return None


def _trailing_position(element: etree._Element) -> int:
    for index, candidate in enumerate(element):
        if localname(candidate) in _TRAILING_OBJECT_CHILDREN:
            return index
    return len(element)


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
    if name in ("log", "trajectory", "mudLog"):
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


_LOG_CHILD_ORDER: tuple[str, ...] = (
    "nameWell",
    "nameWellbore",
    "name",
    "objectGrowing",
    "dataUpateRate",
    "curveSensorsAligned",
    "dataGroup",
    "serviceCompany",
    "runNumber",
    "bhaRunNumber",
    "pass",
    "creationDate",
    "description",
    "dataDelimiter",
    "indexType",
    "startIndex",
    "endIndex",
    "stepIncrement",
    "startDateTimeIndex",
    "endDateTimeIndex",
    "direction",
    "indexCurve",
    "nullValue",
    "logParam",
    "logCurveInfo",
    "logData",
    "commonData",
    "customData",
)

_MUDLOG_CHILD_ORDER: tuple[str, ...] = (
    "nameWell",
    "nameWellbore",
    "name",
    "objectGrowing",
    "dTim",
    "mudLogCompany",
    "mudLogEngineers",
    "startMd",
    "endMd",
    "relatedLog",
    "parameter",
    "geologyInterval",
    "commonData",
    "customData",
)

_LOG_CURVE_CHILD_ORDER: tuple[str, ...] = (
    "mnemonic",
    "classWitsml",
    "classIndex",
    "unit",
    "mnemAlias",
    "nullValue",
    "alternateIndex",
    "wellDatum",
    "minIndex",
    "maxIndex",
    "minDateTimeIndex",
    "maxDateTimeIndex",
    "curveDescription",
    "sensorOffset",
    "dataSource",
    "densData",
    "traceState",
    "traceOrigin",
    "typeLogData",
    "axisDefinition",
    "extensionNameValue",
)

_TRAJECTORY_CHILD_ORDER: tuple[str, ...] = (
    "nameWell",
    "nameWellbore",
    "name",
    "objectGrowing",
    "parentTrajectory",
    "dTimTrajStart",
    "dTimTrajEnd",
    "mdMn",
    "mdMx",
    "serviceCompany",
    "magDeclUsed",
    "gridCorUsed",
    "gridConUsed",
    "aziVertSect",
    "dispNsVertSectOrig",
    "dispEwVertSectOrig",
    "definitive",
    "memory",
    "finalTraj",
    "aziRef",
    "trajectoryStation",
    "commonData",
    "customData",
)


def _insert_ordered(
    parent: etree._Element, item: etree._Element, order: tuple[str, ...]
) -> None:
    wanted = order.index(localname(item)) if localname(item) in order else len(order)
    position = len(parent)
    for index, candidate in enumerate(parent):
        name = localname(candidate)
        rank = order.index(name) if name in order else len(order)
        if rank > wanted:
            position = index
            break
    parent.insert(position, item)


def set_ordered_child_text(
    parent: etree._Element,
    name: str,
    value: str,
    *,
    uom: str | None = None,
    order: tuple[str, ...] = _LOG_CHILD_ORDER,
) -> etree._Element:
    """Crea/actualiza un hijo respetando el orden del XSD oficial."""
    existing = child(parent, name)
    if existing is None:
        existing = etree.Element(f"{WITSML}{name}")
        _insert_ordered(parent, existing, order)
    existing.text = value
    if uom is not None:
        existing.set("uom", uom)
    return existing


def contextual_names(
    element: etree._Element,
) -> tuple[str | None, str | None, str | None]:
    """Devuelve ``(nameWell, nameWellbore, name)`` del objeto cambiado."""
    return (
        text_of(element, "nameWell"),
        text_of(element, "nameWellbore"),
        text_of(element, "name"),
    )


def last_change_token(element: etree._Element) -> datetime | None:
    """Devuelve ``commonData/dTimLastChange`` enviado por el cliente.

    Se usa como precondición de concurrencia optimista: una actualización o un
    borrado solo se aplican si el token coincide con el ``dTimLastChange``
    almacenado. Un cliente que no lo envía conserva el último escritor gana.
    """
    return _common_datetime(child(element, "commonData"), "dTimLastChange")


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
        if localname(item) in (
            "logData",
            "trajectoryStation",
            "geologyInterval",
            "parameter",
        ):
            element.remove(item)


def validate_object_element(
    object_type: str, element: etree._Element, *, require_uid: bool = True
) -> None:
    spec: ObjectSpec = spec_for(object_type)
    if localname(element) != spec.name:
        raise ValidationError(
            f"Se esperaba <{spec.name}> y se recibió <{localname(element)}>."
        )
    uid = normalize_uid(attr(element, "uid"))
    if require_uid and object_type != "well" and not uid:
        raise ValidationError(f"{object_type} requiere uid.")
    if object_type in ("wellbore", "log", "trajectory", "mudLog") and not attr(element, "uidWell"):
        raise ValidationError(f"{object_type} requiere uidWell.")
    if object_type in ("log", "trajectory", "mudLog") and not attr(element, "uidWellbore"):
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
    # El cliente de certificación de Energistics recorre los hijos de
    # ``logData/data`` como filas, por lo que se emite un ``data`` por fila
    # (el XSD oficial declara ``maxOccurs="unbounded"``).
    for row in rows:
        data = etree.SubElement(log_data, f"{WITSML}data")
        data.text = ",".join(row)
    return log_data


def apply_return_elements(
    element: etree._Element,
    mode: str,
    selection_items: frozenset[str] = frozenset(),
    selection: tuple[SelectionItem, ...] = (),
) -> etree._Element:
    result = copy.deepcopy(element)
    if mode == "requested":
        _project_selection(result, selection, keep_required=True)
    elif mode == "id-only":
        allowed = _ID_ONLY_CHILDREN | selection_items
        for item in list(result):
            if localname(item) not in allowed:
                result.remove(item)
        if "dTimLastChange" in selection_items:
            common = child(result, "commonData")
            if common is not None:
                for item in list(common):
                    if localname(item) != "dTimLastChange":
                        common.remove(item)
    elif mode == "header-only":
        strip_payload(result)
    elif mode == "data-only":
        allowed = {
            "logData",
            "trajectoryStation",
            "geologyInterval",
            "parameter",
        } | selection_items
        for item in list(result):
            if localname(item) not in allowed:
                result.remove(item)
    elif mode == "station-location-only":
        allowed = {"trajectoryStation"} | selection_items
        for item in list(result):
            if localname(item) not in allowed:
                result.remove(item)
        for station in children(result, "trajectoryStation"):
            for item in list(station):
                if localname(item) not in _STATION_LOCATION_CHILDREN:
                    station.remove(item)
    return result


def _match_selection(
    element: etree._Element, candidates: list[SelectionItem]
) -> SelectionItem | None:
    uid = normalize_uid(attr(element, "uid"))
    if uid:
        for candidate in candidates:
            if candidate.uid is not None and candidate.uid.lower() == uid.lower():
                return candidate
    for candidate in candidates:
        if candidate.uid is None:
            return candidate
    return None


def _project_selection(
    stored: etree._Element,
    selection: tuple[SelectionItem, ...],
    *,
    keep_required: bool = False,
) -> None:
    """Deja en ``stored`` sólo los elementos pedidos en la plantilla.

    Los atributos del objeto se conservan: son la identidad mínima que el
    cliente necesita para correlacionar la respuesta. El nombre del objeto y de
    sus padres se mantiene para que la respuesta siga validando contra el XSD
    normativo, igual que hace ``id-only``. Un elemento de selección sin hijos se
    devuelve completo; uno con hijos se proyecta recursivamente.
    """
    for item in list(stored):
        name = localname(item)
        if keep_required and name in _ID_ONLY_CHILDREN:
            continue
        candidates = [entry for entry in selection if entry.name == name]
        match = _match_selection(item, candidates)
        if match is None:
            stored.remove(item)
        elif match.children:
            _project_selection(item, match.children)


def apply_selection_capability(element: etree._Element) -> etree._Element:
    """Respuesta mínima de ``requestObjectSelectionCapability`` (SQ-002)."""
    result = copy.deepcopy(element)
    allowed = {"name", "numGovt", "numAPI", "commonData"}
    for item in list(result):
        if localname(item) not in allowed:
            result.remove(item)
    common = child(result, "commonData")
    if common is not None:
        for item in list(common):
            if localname(item) != "dTimLastChange":
                common.remove(item)
    return result


def apply_attribute_deletions(
    stored: etree._Element, query: etree._Element
) -> bool:
    """Elimina atributos indicados con valor vacío en un borrado selectivo.

    Devuelve ``True`` si se eliminó al menos un atributo. El emparejamiento es
    por nombre de elemento y, cuando existe, por atributo ``uid``.
    """
    changed = False
    for query_child in query:
        name = localname(query_child)
        candidates = [item for item in stored if localname(item) == name]
        query_uid = attr(query_child, "uid")
        if query_uid:
            candidates = [
                item for item in candidates if attr(item, "uid") == query_uid
            ]
        for candidate in candidates:
            for attribute, value in query_child.attrib.items():
                if attribute in ("uid", "uidWell", "uidWellbore", "uidRef"):
                    continue
                if value == "" and attribute in candidate.attrib:
                    del candidate.attrib[attribute]
                    changed = True
            if apply_attribute_deletions(candidate, query_child):
                changed = True
    return changed


def new_container(object_type: str) -> etree._Element:
    spec = spec_for(object_type)
    return etree.Element(
        f"{WITSML}{spec.plural}",
        nsmap={None: WITSML_NS},
        version=SCHEMA_VERSION,
    )


_TRAILING_OBJECT_CHILDREN = frozenset({"commonData", "customData"})

#: ``returnElements=id-only``: uid + nombre del objeto y de sus padres.
_ID_ONLY_CHILDREN = frozenset({"name", "nameWell", "nameWellbore"})

#: ``returnElements=data-only``: datos crecientes y contexto mínimo.
_DATA_ONLY_CHILDREN = frozenset(
    {
        "indexCurve",
        "logCurveInfo",
        "logData",
        "mdMn",
        "mdMx",
        "trajectoryStation",
    }
)

#: ``returnElements=station-location-only`` (WITSML STORE API §6.6.5).
_STATION_LOCATION_CHILDREN = frozenset(
    {"dTimStn", "typeTrajStation", "md", "tvd", "incl", "azi", "location"}
)

#: Elementos de selección de datos (WITSML STORE API §7) que deben devolverse
#: siempre junto con ``returnElements``, aunque el modo los excluya.
_SELECTION_ITEMS = frozenset(
    {
        "name",
        "nameWell",
        "nameWellbore",
        "numGovt",
        "numAPI",
        "indexType",
        "startIndex",
        "endIndex",
        "startDateTimeIndex",
        "endDateTimeIndex",
        "objectGrowing",
        "mdMn",
        "mdMx",
        "logCurveInfo",
        "logData",
    }
)


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
    """Construye ``SuppMsgOut`` en texto plano.

    El cliente de certificación consume este campo como una cadena (toma el
    primer UID generado y lo usa tal cual). El formato XML de versiones
    anteriores hacía que ese UID incluyera las etiquetas y fallara la lectura.
    """
    return " ".join([*uids, *(messages or ())])
