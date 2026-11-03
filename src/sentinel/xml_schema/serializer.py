"""Serialización de documentos de capacidades y ChangeLog."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import NAMESPACE_URL, uuid5

from lxml import etree

from sentinel import SCHEMA_VERSION
from sentinel.audit_config.domain import ServerConfig
from sentinel.xml_schema.documents import format_datetime
from sentinel.xml_schema.namespaces import API, API_NS, WITSML, WITSML_NS

#: API version declarada en ``capServers``/``capServer`` (API 1.4.1).
API_VERSION = "1.4.1"

#: ``(función, ((dataObject, growing, systematic), ...))``.
#:
#: ``growing`` añade ``maxDataNodes``; ``systematic`` añade además
#: ``maxDataPoints``. ``changeLog`` sólo se ofrece en lectura.
CAPABILITY_FUNCTIONS: tuple[
    tuple[str, tuple[tuple[str, bool, bool], ...]], ...
] = (
    ("WMLS_GetCap", (("capServer", False, False),)),
    (
        "WMLS_GetFromStore",
        (
            ("changeLog", False, False),
            ("log", True, True),
            ("mudLog", True, False),
            ("trajectory", True, False),
            ("well", False, False),
            ("wellbore", False, False),
        ),
    ),
    (
        "WMLS_AddToStore",
        (
            ("log", True, True),
            ("mudLog", True, False),
            ("trajectory", True, False),
            ("well", False, False),
            ("wellbore", False, False),
        ),
    ),
    (
        "WMLS_UpdateInStore",
        (
            ("log", True, True),
            ("mudLog", True, False),
            ("trajectory", True, False),
            ("well", False, False),
            ("wellbore", False, False),
        ),
    ),
    (
        "WMLS_DeleteFromStore",
        (
            ("log", True, True),
            ("mudLog", True, False),
            ("trajectory", True, False),
            ("well", False, False),
            ("wellbore", False, False),
        ),
    ),
    ("WMLS_GetVersion", ()),
    ("WMLS_GetBaseMsg", ()),
)


@dataclass(frozen=True)
class ChangeLogHistoryView:
    """Una entrada de ``cs_changeHistory``."""

    change_date: datetime
    change_type: str
    change_info: str | None = None
    start_index: str | None = None
    end_index: str | None = None
    mnemonics: str | None = None
    index_uom: str | None = None


@dataclass(frozen=True)
class ChangeLogView:
    """Un objeto ``changeLog`` agregado (todas las entradas de un objeto)."""

    uid: str
    object_type: str
    name_object: str | None = None
    name_well: str | None = None
    name_wellbore: str | None = None
    uid_well: str | None = None
    uid_wellbore: str | None = None
    histories: tuple[ChangeLogHistoryView, ...] = ()
    last_change_type: str = "update"
    last_change_info: str | None = None
    d_tim_last_change: datetime | None = None
    include_history: bool = True


def build_capabilities(config: ServerConfig) -> str:
    """Construye el objeto ``capServer`` oficial (namespace API 1.4.1).

    La forma sigue la Sección 4.2.4 del WITSML STORE API v1.4.1: el documento
    raíz es ``capServers``, cada función declara sus ``dataObject`` y los
    objetos crecientes declaran ``maxDataNodes``/``maxDataPoints`` y
    ``growingTimeoutPeriod``. El cliente de certificación consume exactamente
    esa estructura para descubrir qué operaciones puede ejecutar.
    """
    root = etree.Element("capServers", nsmap={None: API_NS}, version=API_VERSION)
    server = etree.SubElement(root, f"{API}capServer", apiVers=config.api_version)

    contact = etree.SubElement(server, f"{API}contact")
    etree.SubElement(contact, f"{API}name").text = config.contact_name
    etree.SubElement(contact, f"{API}email").text = config.contact_email
    etree.SubElement(contact, f"{API}phone").text = config.contact_phone
    etree.SubElement(server, f"{API}description").text = config.description
    etree.SubElement(server, f"{API}name").text = config.product_name
    etree.SubElement(server, f"{API}vendor").text = config.vendor
    etree.SubElement(server, f"{API}version").text = config.version
    etree.SubElement(server, f"{API}schemaVersion").text = config.schema_version
    etree.SubElement(server, f"{API}changeDetectionPeriod").text = str(
        config.change_detection_seconds
    )
    etree.SubElement(server, f"{API}maxRequestLatestValues").text = str(
        config.max_request_latest_values
    )
    for data_object in ("log", "mudLog", "trajectory"):
        etree.SubElement(
            server,
            f"{API}growingTimeoutPeriod",
            dataObject=data_object,
        ).text = str(config.growing_timeout_seconds)
    etree.SubElement(server, f"{API}cascadedDelete").text = (
        "true" if config.cascaded_delete else "false"
    )
    etree.SubElement(server, f"{API}supportUomConversion").text = (
        "true" if config.support_uom_conversion else "false"
    )
    # D-01: no se declara ``compressionMethod``; el elemento describe solo la
    # compresión de solicitudes, que es opcional. Las respuestas se comprimen
    # con gzip cuando el cliente lo acepta (ver ``wmls_transport.router``).

    for function_name, data_objects in CAPABILITY_FUNCTIONS:
        function = etree.SubElement(server, f"{API}function", name=function_name)
        for data_object, growing, systematic in data_objects:
            element = etree.SubElement(function, f"{API}dataObject")
            element.text = data_object
            if growing:
                element.set("maxDataNodes", str(config.max_data_nodes))
            if systematic:
                element.set("maxDataPoints", str(config.max_data_points))

    return etree.tostring(root, encoding="unicode")


def build_change_log(records: list[ChangeLogView]) -> str:
    root = etree.Element(
        f"{WITSML}changeLogs", nsmap={None: WITSML_NS}, version=SCHEMA_VERSION
    )
    for record in records:
        root.append(build_change_log_element(record))
    return etree.tostring(root, encoding="unicode")


def build_change_log_element(record: ChangeLogView) -> etree._Element:
    """Serializa un objeto ``changeLog`` con el formato oficial.

    El esquema 1.4.1.1 no admite atributos ``objectType``, ``changeType`` ni
    ``dTimChange``: el objeto cambiado va en ``uidObject`` y los nombres
    contextuales, el tipo y la fecha son elementos del grupo ``grp_changeLog``.
    Todas las entradas de ``changeHistory`` de un mismo objeto se agrupan en un
    único ``changeLog``.
    """
    element = etree.Element(f"{WITSML}changeLog")
    element.set("uid", _change_log_uid(record))
    element.set("uidObject", record.uid)
    if record.uid_well:
        element.set("uidWell", record.uid_well)
    if record.uid_wellbore:
        element.set("uidWellbore", record.uid_wellbore)
    if record.name_well:
        _append_text(element, "nameWell", record.name_well)
    if record.name_wellbore:
        _append_text(element, "nameWellbore", record.name_wellbore)
    _append_text(element, "nameObject", record.name_object or record.uid)
    _append_text(element, "objectType", record.object_type)
    _append_text(element, "lastChangeType", record.last_change_type or "update")
    if record.last_change_info:
        _append_text(element, "lastChangeInfo", record.last_change_info)
    if record.include_history and record.histories:
        for index, history in enumerate(record.histories):
            element.append(_build_history(history, record.uid, index))
    changed = record.d_tim_last_change
    if changed is None and record.histories:
        changed = max(history.change_date for history in record.histories)
    if changed is not None:
        common = etree.SubElement(element, f"{WITSML}commonData")
        _append_text(common, "dTimLastChange", format_datetime(changed))
    return element


def _build_history(
    history: ChangeLogHistoryView, object_uid: str, index: int
) -> etree._Element:
    """Construye ``cs_changeHistory`` en el orden exacto del XSD.

    El esquema de escritura generado exige el atributo ``uid`` en cada entrada
    (``attgrp_uid`` pasa a ``use="required"``); se deriva de forma estable a
    partir del objeto, la fecha y el tipo de cambio.
    """
    element = etree.Element(f"{WITSML}changeHistory")
    element.set(
        "uid",
        str(
            uuid5(
                NAMESPACE_URL,
                "|".join(
                    (
                        "changeHistory",
                        object_uid,
                        history.change_date.isoformat(),
                        history.change_type or "update",
                        str(index),
                    )
                ),
            )
        ),
    )
    _append_text(element, "dTimChange", format_datetime(history.change_date))
    _append_text(element, "changeType", history.change_type or "update")
    if history.change_info:
        _append_text(element, "changeInfo", history.change_info)
    if history.start_index is not None and history.end_index is not None:
        start_name, end_name = _index_element_names(history.start_index)
        if start_name == "startIndex":
            # ``startIndex``/``endIndex`` son ``genericMeasure``: el esquema de
            # escritura generado exige el atributo ``uom``.
            uom = history.index_uom or "m"
            start_element = _append_text(element, start_name, history.start_index)
            start_element.set("uom", uom)
            end_element = _append_text(element, end_name, history.end_index)
            end_element.set("uom", uom)
        else:
            _append_text(element, start_name, history.start_index)
            _append_text(element, end_name, history.end_index)
    if history.mnemonics:
        _append_text(element, "mnemonics", history.mnemonics)
    return element


def _index_element_names(value: str) -> tuple[str, str]:
    # ``format_index_value`` emite ISO 8601 con ``T`` para fechas.
    if "T" in value:
        return "startDateTimeIndex", "endDateTimeIndex"
    return "startIndex", "endIndex"


def _append_text(parent: etree._Element, name: str, value: str) -> etree._Element:
    element = etree.SubElement(parent, f"{WITSML}{name}")
    element.text = value
    return element


def _change_log_uid(record: ChangeLogView) -> str:
    """UID estable y único (<= 64 caracteres) para el objeto ``changeLog``."""
    seed = "|".join(
        (
            record.object_type,
            record.uid,
            record.last_change_type,
            record.d_tim_last_change.isoformat() if record.d_tim_last_change else "",
        )
    )
    return str(uuid5(NAMESPACE_URL, seed))
