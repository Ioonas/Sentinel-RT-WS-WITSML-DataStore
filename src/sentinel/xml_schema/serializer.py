"""Serialización de documentos de capacidades y ChangeLog."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import NAMESPACE_URL, uuid5

from lxml import etree

from sentinel import SCHEMA_VERSION
from sentinel.audit_config.domain import ServerConfig
from sentinel.xml_schema.documents import format_datetime
from sentinel.xml_schema.namespaces import WITSML, WITSML_NS

FUNCTIONS: tuple[str, ...] = (
    "WMLS_GetVersion",
    "WMLS_GetCap",
    "WMLS_GetBaseMsg",
    "WMLS_GetFromStore",
    "WMLS_AddToStore",
    "WMLS_UpdateInStore",
    "WMLS_DeleteFromStore",
)

OBJECTS: tuple[str, ...] = ("well", "wellbore", "log", "trajectory", "changeLog")


@dataclass(frozen=True)
class ChangeLogView:
    uid: str
    object_type: str
    change_type: str
    change_date: datetime
    uid_well: str | None = None
    uid_wellbore: str | None = None
    name_object: str | None = None
    name_well: str | None = None
    name_wellbore: str | None = None


def build_capabilities(config: ServerConfig) -> str:
    """Construye ``capServer`` desde ``server_config`` (única fuente, §6)."""
    root = etree.Element(
        "capServer",
        nsmap={None: WITSML_NS},
        apiVers=config.api_version,
        schemaVersion=config.schema_version,
    )
    contact = etree.SubElement(root, f"{WITSML}contact")
    etree.SubElement(contact, f"{WITSML}name").text = config.contact_name
    etree.SubElement(contact, f"{WITSML}email").text = config.contact_email
    etree.SubElement(contact, f"{WITSML}phone").text = config.contact_phone
    etree.SubElement(root, f"{WITSML}description").text = config.description
    etree.SubElement(root, f"{WITSML}name").text = config.product_name
    etree.SubElement(root, f"{WITSML}vendor").text = config.vendor
    etree.SubElement(root, f"{WITSML}version").text = config.version

    functions = etree.SubElement(root, f"{WITSML}functions")
    for name in FUNCTIONS:
        etree.SubElement(functions, f"{WITSML}function", name=name)

    objects = etree.SubElement(root, f"{WITSML}objects")
    for name in OBJECTS:
        etree.SubElement(objects, f"{WITSML}object", name=name)

    etree.SubElement(root, f"{WITSML}maxDataNodes").text = str(config.max_data_nodes)
    etree.SubElement(root, f"{WITSML}maxDataPoints").text = str(config.max_data_points)
    etree.SubElement(root, f"{WITSML}growingTimeoutPeriod").text = str(
        config.growing_timeout_seconds
    )
    etree.SubElement(root, f"{WITSML}changeDetectionPeriod").text = str(
        config.change_detection_seconds
    )
    etree.SubElement(root, f"{WITSML}maxRequestLatestValues").text = str(
        config.max_request_latest_values
    )
    etree.SubElement(root, f"{WITSML}cascadedDelete").text = (
        "true" if config.cascaded_delete else "false"
    )
    etree.SubElement(root, f"{WITSML}supportUomConversion").text = (
        "true" if config.support_uom_conversion else "false"
    )
    return etree.tostring(root, encoding="unicode")


def build_change_log(records: list[ChangeLogView]) -> str:
    root = etree.Element(
        f"{WITSML}changeLogs", nsmap={None: WITSML_NS}, version=SCHEMA_VERSION
    )
    for record in records:
        root.append(build_change_log_element(record))
    return etree.tostring(root, encoding="unicode")


def build_change_log_element(record: ChangeLogView) -> etree._Element:
    """Serializa un evento con el formato oficial de ``obj_changeLog``.

    El esquema 1.4.1.1 no admite atributos ``objectType``, ``changeType`` ni
    ``dTimChange``: el objeto cambiado va en ``uidObject`` y los nombres
    contextuales, el tipo y la fecha son elementos del grupo ``grp_changeLog``.
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
    _append_text(element, "lastChangeType", record.change_type)
    history = etree.SubElement(element, f"{WITSML}changeHistory")
    _append_text(history, "dTimChange", format_datetime(record.change_date))
    _append_text(history, "changeType", record.change_type)
    common = etree.SubElement(element, f"{WITSML}commonData")
    _append_text(common, "dTimLastChange", format_datetime(record.change_date))
    return element


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
            record.change_type,
            record.change_date.isoformat(),
        )
    )
    return str(uuid5(NAMESPACE_URL, seed))
