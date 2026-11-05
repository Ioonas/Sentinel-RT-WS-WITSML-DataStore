"""Pruebas del parseo XML seguro y de la serialización de capacidades."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from sentinel.audit_config.domain import ServerConfig
from sentinel.shared.errors import ValidationError
from sentinel.witsml_application.domain.codes import WmlsCode
from sentinel.witsml_application.domain.errors import WitsmlError
from sentinel.witsml_application.domain.uom import UomValidator
from sentinel.xml_schema import documents as xd
from sentinel.xml_schema.namespaces import WITSML_NS
from sentinel.xml_schema.parser import parse_xml, serialize
from sentinel.xml_schema.serializer import (
    ChangeLogHistoryView,
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


def test_uom_dictionary_validation_follows_measure_types() -> None:
    validator = UomValidator()
    assert validator.available

    prefix = (
        f'<wells xmlns="{WITSML_NS}" version="1.4.1.1"><well uid="w-uom">'
        "<name>UOM Well</name>"
    )
    validator.validate(parse_xml(prefix + '<waterDepth uom="m">1</waterDepth></well></wells>'))

    with pytest.raises(WitsmlError) as missing:
        validator.validate(parse_xml(prefix + "<waterDepth>1</waterDepth></well></wells>"))
    assert missing.value.wmls_code == -453

    with pytest.raises(WitsmlError) as invalid:
        validator.validate(
            parse_xml(prefix + '<waterDepth uom="furlong">1</waterDepth></well></wells>')
        )
    assert invalid.value.wmls_code == -443

    # customData usa xsd:any: su <value> no es una medida y no exige uom.
    validator.validate(
        parse_xml(
            prefix
            + '<customData><extensionNameValue name="note">'
            "<value>sin uom</value></extensionNameValue></customData></well></wells>"
        )
    )


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
    changed = datetime(2026, 10, 31, tzinfo=UTC)
    xml = build_change_log(
        [
            ChangeLogView(
                uid="w-1",
                object_type="well",
                name_object="Well One",
                histories=(
                    ChangeLogHistoryView(
                        change_date=changed,
                        change_type="update",
                        start_index="1",
                        end_index="4",
                        mnemonics="BDEP,CURVE3",
                        index_uom="m",
                    ),
                ),
                last_change_type="update",
                d_tim_last_change=changed,
            )
        ]
    )
    assert "<lastChangeType>update</lastChangeType>" in xml
    assert "<nameObject>Well One</nameObject>" in xml
    assert "<objectType>well</objectType>" in xml
    assert 'uidObject="w-1"' in xml
    assert 'uom="m"' in xml
    assert "<mnemonics>BDEP,CURVE3</mnemonics>" in xml
    assert "changeHistory uid=" in xml
    assert xml.index("<lastChangeType>") < xml.index("<changeHistory uid=")
    assert xml.index("<changeType>update</changeType>") < xml.index("<commonData>")
    document = parse_xml(xml)
    LxmlXsdValidator().validate_document("changeLog", document, operation="read")
    LxmlXsdValidator().validate_document("changeLog", document, operation="write")


def test_parse_log_data_accepts_repeated_data_elements() -> None:
    root = parse_xml(
        f'<logs xmlns="{WITSML_NS}"><log uid="l" uidWell="w" uidWellbore="wb">'
        "<indexType>date time</indexType><indexCurve>TIME</indexCurve>"
        "<logData><mnemonicList>TIME,C1</mnemonicList>"
        "<unitList>unitless,m</unitList>"
        "<data>2026-10-30T00:00:00.000Z,1</data>"
        "<data>2026-10-30T00:00:01.000Z,2</data></logData>"
        "</log></logs>"
    )
    block = xd.parse_log_data(root[0])
    assert block.mnemonics == ["TIME", "C1"]
    assert [row["C1"] for row in block.rows] == ["1", "2"]


def test_build_log_data_emits_one_data_element_per_row() -> None:
    log_data = xd.build_log_data(["TIME", "C1"], ["unitless", "m"], [["1", "2"], ["3", "4"]])
    assert [item.text for item in log_data if xd.localname(item) == "data"] == [
        "1,2",
        "3,4",
    ]


def test_uom_validator_fails_closed_without_dictionary(tmp_path) -> None:
    """Sin witsmlUnitDict.xml la validación rechaza la operación; no la omite."""
    from lxml import etree

    validator = UomValidator(tmp_path)
    assert validator.available is False
    root = etree.fromstring(f'<wells xmlns="{WITSML_NS}"/>')
    with pytest.raises(WitsmlError) as raised:
        validator.validate(root, code=WmlsCode.ERROR_UPDATING)
    assert raised.value.wmls_code == int(WmlsCode.ERROR_UPDATING)
