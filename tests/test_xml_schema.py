"""Pruebas del parseo XML seguro y de la serialización de capacidades."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from sentinel.audit_config.domain import ServerConfig
from sentinel.shared.errors import ValidationError
from sentinel.xml_schema import documents as xd
from sentinel.xml_schema.namespaces import WITSML_NS
from sentinel.xml_schema.parser import parse_xml, serialize
from sentinel.xml_schema.serializer import (
    ChangeLogView,
    build_capabilities,
    build_change_log,
)
from sentinel.xml_schema.xsd import LxmlXsdValidator


def test_parser_rejects_doctype_and_entities() -> None:
    with pytest.raises(ValidationError):
        parse_xml(
            '<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///c:/">]>'
            f'<wells xmlns="{WITSML_NS}"><well uid="&xxe;"/></wells>'
        )
    with pytest.raises(ValidationError):
        parse_xml(
            '<?xml version="1.0"?><!DOCTYPE wells [<!ENTITY xxe "boom">]>'
            f'<wells xmlns="{WITSML_NS}"><well uid="&xxe;"/></wells>'
        )
    with pytest.raises(ValidationError):
        parse_xml(f'<wells xmlns="{WITSML_NS}"><well uid="a">&undefined;</well></wells>')


def test_roundtrip_preserves_namespace() -> None:
    root = parse_xml(f'<wells xmlns="{WITSML_NS}"><well uid="w-1"/></wells>')
    xd.ensure_namespace(root)
    xml = serialize(root)
    assert WITSML_NS in xml
    assert 'uid="w-1"' in xml


def test_parse_options_and_queries() -> None:
    options = xd.parse_options(
        "<options><returnElements>header-only</returnElements>"
        "<maxReturnNodes>10</maxReturnNodes></options>"
    )
    assert options.return_elements == "header-only"
    assert options.max_return_nodes == 10

    official = xd.parse_options(
        "dataVersion=1.4.1.1&returnElements=id-only&requestLatestValues=5"
    )
    assert official.return_elements == "id-only"
    assert official.request_latest_values == 5
    assert xd.option_value("dataVersion=1.4.1.1", "dataVersion") == "1.4.1.1"

    queries = xd.parse_queries(
        f'<wells xmlns="{WITSML_NS}"><well uid="w-1"><name>Alpha</name></well></wells>',
        "well",
    )
    assert queries[0].uid == "w-1"
    assert queries[0].text_filters["name"] == "Alpha"


def test_official_log_header_uses_index_curve() -> None:
    log = parse_xml(
        f'<logs xmlns="{WITSML_NS}" version="1.4.1.1"><log uid="log-1" '
        'uidWell="w-1" uidWellbore="wb-1">'
        "<nameWell>Well One</nameWell><nameWellbore>WB One</nameWellbore>"
        "<name>Log One</name><indexType>measured depth</indexType>"
        '<startIndex uom="m">0</startIndex><endIndex uom="m">10</endIndex>'
        "<indexCurve>MD</indexCurve>"
        '<logCurveInfo uid="c1"><mnemonic>MD</mnemonic><unit>m</unit>'
        "<typeLogData>double</typeLogData></logCurveInfo>"
        '<logCurveInfo uid="c2"><mnemonic>GR</mnemonic><unit>gAPI</unit>'
        "<typeLogData>double</typeLogData></logCurveInfo></log></logs>"
    )
    element = log[0]
    header = xd.parse_log_header(element)
    assert header.index_type == "measured depth"
    assert [curve.mnemonic for curve in header.curves if curve.is_index] == ["MD"]
    xd.validate_object_element("log", element)


def test_capabilities_use_server_config() -> None:
    config = ServerConfig(contact_email="ops@example.com", contact_phone="+1 555 0100")
    xml = build_capabilities(config)
    assert "Sentinel RT&amp;WS WITSML DataStore" in xml
    assert "ops@example.com" in xml
    assert "cascadedDelete" in xml
    assert "1.4.1.1" in xml


def test_change_log_serialization() -> None:
    xml = build_change_log(
        [
            ChangeLogView(
                uid="w-1",
                object_type="well",
                change_type="add",
                change_date=datetime(2026, 10, 31, tzinfo=UTC),
                name_object="Well One",
            )
        ]
    )
    assert "<lastChangeType>add</lastChangeType>" in xml
    assert "<nameObject>Well One</nameObject>" in xml
    assert "<objectType>well</objectType>" in xml
    assert 'uidObject="w-1"' in xml
    document = parse_xml(xml)
    LxmlXsdValidator().validate_document("changeLog", document, operation="read")
