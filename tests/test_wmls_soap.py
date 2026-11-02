"""Pruebas de extremo a extremo del endpoint SOAP WMLS."""

from __future__ import annotations

import base64
from xml.sax.saxutils import escape

import pytest
from httpx import AsyncClient
from lxml import etree

from sentinel.wmls_transport.wsdl import OFFICIAL_WSDL
from sentinel.xml_schema.namespaces import (
    ACTION_NS,
    API_NS,
    MESSAGE_NS,
    SOAP_NS,
    WITSML_NS,
)
from sentinel.xml_schema.xsd import LxmlXsdValidator

pytestmark = pytest.mark.integration


def envelope(operation: str, parameters: dict[str, str] | None = None) -> str:
    body = ""
    for name, value in (parameters or {}).items():
        body += f"<witsml:{name}>{escape(value)}</witsml:{name}>"
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<soapenv:Envelope xmlns:soapenv="{SOAP_NS}" xmlns:witsml="{MESSAGE_NS}">'
        f"<soapenv:Body><witsml:{operation}>{body}</witsml:{operation}>"
        "</soapenv:Body></soapenv:Envelope>"
    )


def field(response, name: str) -> str:
    root = etree.fromstring(response.content)
    element = root.find(f".//{{{MESSAGE_NS}}}{name}")
    assert element is not None, response.text
    return element.text or ""


def result(response) -> int:
    return int(field(response, "Result"))


async def soap(
    client: AsyncClient,
    operation: str,
    secret: str,
    parameters: dict[str, str] | None = None,
):
    credentials = base64.b64encode(f"acme.writer:{secret}".encode()).decode()
    return await client.post(
        "/witsml",
        content=envelope(operation, parameters),
        headers={
            "content-type": "text/xml; charset=utf-8",
            "authorization": f"Basic {credentials}",
            "soapaction": f'"{ACTION_NS}/Store.{operation}"',
        },
    )


async def create_writer(client: AsyncClient, csrf: str) -> str:
    response = await client.post(
        "/admin-api/v1/service-accounts",
        headers={"x-csrf-token": csrf},
        json={
            "name": "acme.writer",
            "role": "writer",
            "grants": [
                {"object_type": "*", "action": "read"},
                {"object_type": "*", "action": "write"},
                {"object_type": "*", "action": "delete"},
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["credential"]["secret"]


WELL = (
    f'<wells xmlns="{WITSML_NS}" version="1.4.1.1"><well uid="w-1">'
    "<name>Well One</name><numGovt>GOV-1</numGovt>"
    "<timeZone>-06:00</timeZone><numAPI>API-1</numAPI></well></wells>"
)
WELLBORE = (
    f'<wellbores xmlns="{WITSML_NS}" version="1.4.1.1">'
    '<wellbore uid="wb-1" uidWell="w-1">'
    "<nameWell>Well One</nameWell><name>WB One</name>"
    "</wellbore></wellbores>"
)
LOG = (
    f'<logs xmlns="{WITSML_NS}" version="1.4.1.1">'
    '<log uid="log-1" uidWell="w-1" uidWellbore="wb-1">'
    "<nameWell>Well One</nameWell><nameWellbore>WB One</nameWellbore>"
    "<name>Log One</name><indexType>measured depth</indexType>"
    '<startIndex uom="m">0</startIndex><endIndex uom="m">10</endIndex>'
    "<indexCurve>MD</indexCurve>"
    '<logCurveInfo uid="c1"><mnemonic>MD</mnemonic><unit>m</unit>'
    "<typeLogData>double</typeLogData></logCurveInfo>"
    '<logCurveInfo uid="c2"><mnemonic>GR</mnemonic><unit>gAPI</unit>'
    "<typeLogData>double</typeLogData></logCurveInfo>"
    "<logData><mnemonicList>MD,GR</mnemonicList><unitList>m,gAPI</unitList>"
    "<data>0,50\n10,60</data></logData></log></logs>"
)
TRAJECTORY = (
    f'<trajectorys xmlns="{WITSML_NS}" version="1.4.1.1">'
    '<trajectory uid="tr-1" uidWell="w-1" uidWellbore="wb-1">'
    "<nameWell>Well One</nameWell><nameWellbore>WB One</nameWellbore>"
    "<name>Trajectory One</name>"
    '<mdMn uom="m">0</mdMn><mdMx uom="m">100</mdMx>'
    '<trajectoryStation uid="s1"><typeTrajStation>magnetic MWD</typeTrajStation>'
    '<md uom="m">0</md><tvd uom="m">0</tvd>'
    '<incl uom="dega">0</incl><azi uom="dega">0</azi>'
    "</trajectoryStation></trajectory></trajectorys>"
)


TIME_LOG = (
    f'<logs xmlns="{WITSML_NS}" version="1.4.1.1">'
    '<log uid="log-time" uidWell="w-2" uidWellbore="wb-2">'
    "<nameWell>Well Two</nameWell><nameWellbore>WB Two</nameWellbore>"
    "<name>Time Log</name><indexType>date time</indexType>"
    "<direction>increasing</direction><indexCurve>TIME</indexCurve>"
    '<logCurveInfo uid="TIME"><mnemonic>TIME</mnemonic><unit>unitless</unit>'
    "<typeLogData>date time</typeLogData></logCurveInfo>"
    '<logCurveInfo uid="C1"><mnemonic>C1</mnemonic><unit>m</unit>'
    "<typeLogData>double</typeLogData></logCurveInfo>"
    "<logData><mnemonicList>TIME,C1</mnemonicList><unitList>unitless,m</unitList>"
    "<data>2026-10-30T00:00:00.000Z,1</data>"
    "<data>2026-10-30T00:00:01.000Z,2</data></logData></log></logs>"
)


async def test_wmls_discovery_and_crud(admin_client: AsyncClient, csrf: str) -> None:
    secret = await create_writer(admin_client, csrf)

    version = await soap(admin_client, "WMLS_GetVersion", secret)
    assert version.status_code == 200, version.text
    assert field(version, "Result") == "1.4.1.1"

    capabilities = await soap(
        admin_client,
        "WMLS_GetCap",
        secret,
        {"OptionsIn": "dataVersion=1.4.1.1&returnElements=all"},
    )
    assert result(capabilities) == 1
    capabilities_root = etree.fromstring(field(capabilities, "CapabilitiesOut").encode())
    assert capabilities_root.tag == f"{{{API_NS}}}capServers"
    assert capabilities_root.get("version") == "1.4.1"
    cap_server = capabilities_root.find(f"{{{API_NS}}}capServer")
    assert cap_server is not None
    assert cap_server.get("apiVers") == "1.4.1"
    assert cap_server.findtext(f"{{{API_NS}}}schemaVersion") == "1.4.1.1"
    assert cap_server.findtext(f"{{{API_NS}}}cascadedDelete") == "false"
    assert cap_server.findtext(f"{{{API_NS}}}supportUomConversion") == "false"
    # D-01: compressionMethod no se declara; solo describe compresión de
    # solicitudes y las respuestas se comprimen según Accept-Encoding.
    assert cap_server.find(f"{{{API_NS}}}compressionMethod") is None
    # D-17: referencia aprobada de límites y crecimiento.
    assert cap_server.findtext(f"{{{API_NS}}}changeDetectionPeriod") == "60"
    assert cap_server.findtext(f"{{{API_NS}}}maxRequestLatestValues") == "500"
    growing = {}
    for element in cap_server.findall(f"{{{API_NS}}}growingTimeoutPeriod"):
        growing[element.get("dataObject")] = element.text
    assert growing == {"log": "3600", "trajectory": "3600"}

    functions = {
        element.get("name"): element
        for element in cap_server.findall(f"{{{API_NS}}}function")
    }
    assert set(functions) == {
        "WMLS_GetCap",
        "WMLS_GetFromStore",
        "WMLS_AddToStore",
        "WMLS_UpdateInStore",
        "WMLS_DeleteFromStore",
        "WMLS_GetVersion",
        "WMLS_GetBaseMsg",
    }
    read_objects = {
        element.text: element
        for element in functions["WMLS_GetFromStore"].findall(f"{{{API_NS}}}dataObject")
    }
    assert set(read_objects) == {"changeLog", "log", "trajectory", "well", "wellbore"}
    assert read_objects["log"].get("maxDataNodes") == "10000"
    assert read_objects["log"].get("maxDataPoints") == "3000000"
    assert read_objects["trajectory"].get("maxDataNodes") == "10000"
    assert read_objects["trajectory"].get("maxDataPoints") is None
    write_objects = {
        element.text: element
        for element in functions["WMLS_AddToStore"].findall(f"{{{API_NS}}}dataObject")
    }
    assert set(write_objects) == {"log", "trajectory", "well", "wellbore"}

    for object_type, xml in (
        ("well", WELL),
        ("wellbore", WELLBORE),
        ("log", LOG),
        ("trajectory", TRAJECTORY),
    ):
        added = await soap(
            admin_client,
            "WMLS_AddToStore",
            secret,
            {"WMLtypeIn": object_type, "XMLin": xml, "OptionsIn": ""},
        )
        assert result(added) == 1, (object_type, field(added, "SuppMsgOut"))

    read = await soap(
        admin_client,
        "WMLS_GetFromStore",
        secret,
        {
            "WMLtypeIn": "well",
            "QueryIn": f'<wells xmlns="{WITSML_NS}"><well uid="w-1"/></wells>',
            "OptionsIn": "",
        },
    )
    assert result(read) == 1
    assert 'uid="w-1"' in field(read, "XMLout")
    assert 'version="1.4.1.1"' in field(read, "XMLout")

    id_only = await soap(
        admin_client,
        "WMLS_GetFromStore",
        secret,
        {
            "WMLtypeIn": "well",
            "QueryIn": f'<wells xmlns="{WITSML_NS}"><well uid="w-1"/></wells>',
            "OptionsIn": "returnElements=id-only",
        },
    )
    assert result(id_only) == 1
    assert "<name>Well One</name>" in field(id_only, "XMLout")

    for selection in ("<numGovt>GOV-1</numGovt>", "<numAPI>API-1</numAPI>"):
        selected = await soap(
            admin_client,
            "WMLS_GetFromStore",
            secret,
            {
                "WMLtypeIn": "well",
                "QueryIn": f'<wells xmlns="{WITSML_NS}"><well>{selection}</well></wells>',
                "OptionsIn": "returnElements=id-only",
            },
        )
        assert result(selected) == 1, selection
        selected_xml = field(selected, "XMLout")
        assert 'uid="w-1"' in selected_xml
        value = selection.split(">")[1].split("<")[0]
        assert value in selected_xml

    for options, code in (
        ("returnElements=header-only", -425),
        ("returnElements=data-only", -425),
        ("returnElements=station-location-only", -425),
        ("returnElements=latest-change-only", -476),
    ):
        rejected = await soap(
            admin_client,
            "WMLS_GetFromStore",
            secret,
            {
                "WMLtypeIn": "well",
                "QueryIn": f'<wells xmlns="{WITSML_NS}"><well uid="w-1"/></wells>',
                "OptionsIn": options,
            },
        )
        assert result(rejected) == code, options

    log_read = await soap(
        admin_client,
        "WMLS_GetFromStore",
        secret,
        {
            "WMLtypeIn": "log",
            "QueryIn": (
                f'<logs xmlns="{WITSML_NS}">'
                '<log uid="log-1" uidWell="w-1" uidWellbore="wb-1"/></logs>'
            ),
            "OptionsIn": "",
        },
    )
    assert result(log_read) == 1
    assert "MD,GR" in field(log_read, "XMLout")

    # Sin cascada: el padre con hijos no se elimina.
    blocked = await soap(
        admin_client,
        "WMLS_DeleteFromStore",
        secret,
        {
            "WMLtypeIn": "well",
            "QueryIn": f'<wells xmlns="{WITSML_NS}"><well uid="w-1"/></wells>',
            "OptionsIn": "",
        },
    )
    assert result(blocked) == -432

    deletions = (
        (
            "log",
            f'<logs xmlns="{WITSML_NS}"><log uid="log-1" uidWell="w-1" '
            'uidWellbore="wb-1"/></logs>',
        ),
        (
            "trajectory",
            f'<trajectorys xmlns="{WITSML_NS}">'
            '<trajectory uid="tr-1" uidWell="w-1" uidWellbore="wb-1"/>'
            "</trajectorys>",
        ),
        (
            "wellbore",
            f'<wellbores xmlns="{WITSML_NS}"><wellbore uid="wb-1" '
            'uidWell="w-1"/></wellbores>',
        ),
        ("well", f'<wells xmlns="{WITSML_NS}"><well uid="w-1"/></wells>'),
    )
    for object_type, query in deletions:
        deleted = await soap(
            admin_client,
            "WMLS_DeleteFromStore",
            secret,
            {"WMLtypeIn": object_type, "QueryIn": query, "OptionsIn": ""},
        )
        assert result(deleted) == 1, (object_type, field(deleted, "SuppMsgOut"))

    change_log = await soap(
        admin_client,
        "WMLS_GetFromStore",
        secret,
        {
            "WMLtypeIn": "changeLog",
            "QueryIn": f'<changeLogs xmlns="{WITSML_NS}"/>',
            "OptionsIn": "",
        },
    )
    assert result(change_log) == 1
    xml_out = field(change_log, "XMLout")
    assert "<lastChangeType>delete</lastChangeType>" in xml_out
    assert "<nameObject>Well One</nameObject>" in xml_out
    assert 'uidObject="w-1"' in xml_out


async def test_update_log_accepts_official_index_type_alias(
    admin_client: AsyncClient, csrf: str
) -> None:
    secret = await create_writer(admin_client, csrf)
    for object_type, xml in (
        ("well", f'<wells xmlns="{WITSML_NS}" version="1.4.1.1">'
         '<well uid="w-2"><name>Well Two</name></well></wells>'),
        ("wellbore", f'<wellbores xmlns="{WITSML_NS}" version="1.4.1.1">'
         '<wellbore uid="wb-2" uidWell="w-2"><nameWell>Well Two</nameWell>'
         "<name>WB Two</name></wellbore></wellbores>"),
        ("log", TIME_LOG),
    ):
        added = await soap(
            admin_client,
            "WMLS_AddToStore",
            secret,
            {"WMLtypeIn": object_type, "XMLin": xml, "OptionsIn": ""},
        )
        assert result(added) == 1, (object_type, field(added, "SuppMsgOut"))

    update = (
        f'<logs xmlns="{WITSML_NS}" version="1.4.1.1">'
        '<log uid="log-time" uidWell="w-2" uidWellbore="wb-2">'
        "<indexType>date time</indexType><direction>increasing</direction>"
        "<indexCurve>TIME</indexCurve>"
        "<logData><mnemonicList>TIME,C1</mnemonicList><unitList>unitless,m</unitList>"
        "<data>2026-10-30T00:00:02.000Z,3</data></logData></log></logs>"
    )
    updated = await soap(
        admin_client,
        "WMLS_UpdateInStore",
        secret,
        {"WMLtypeIn": "log", "XMLin": update, "OptionsIn": ""},
    )
    assert result(updated) == 1, field(updated, "SuppMsgOut")

    mismatch = update.replace("date time", "measured depth")
    rejected = await soap(
        admin_client,
        "WMLS_UpdateInStore",
        secret,
        {"WMLtypeIn": "log", "XMLin": mismatch, "OptionsIn": ""},
    )
    assert result(rejected) == -412
    assert field(rejected, "SuppMsgOut").isascii()

    added = await soap(
        admin_client,
        "WMLS_AddToStore",
        secret,
        {
            "WMLtypeIn": "well",
            "XMLin": f'<wells xmlns="{WITSML_NS}" version="1.4.1.1">'
            '<well uid="w-3"><name>Well Three</name></well></wells>',
            "OptionsIn": "",
        },
    )
    assert result(added) == 1

    stored = await soap(
        admin_client,
        "WMLS_GetFromStore",
        secret,
        {
            "WMLtypeIn": "well",
            "QueryIn": f'<wells xmlns="{WITSML_NS}"><well uid="w-3"/></wells>',
            "OptionsIn": "",
        },
    )
    assert result(stored) == 1
    changed_at = field(stored, "XMLout").split("<dTimLastChange>")[1].split("<")[0]

    def changed_query(value: str) -> str:
        return (
            f'<wells xmlns="{WITSML_NS}"><well><commonData>'
            f"<dTimLastChange>{value}</dTimLastChange>"
            "</commonData></well></wells>"
        )

    filtered = await soap(
        admin_client,
        "WMLS_GetFromStore",
        secret,
        {
            "WMLtypeIn": "well",
            "QueryIn": changed_query(changed_at),
            "OptionsIn": "returnElements=id-only",
        },
    )
    assert result(filtered) == 1
    assert 'uid="w-3"' not in field(filtered, "XMLout")

    older = await soap(
        admin_client,
        "WMLS_GetFromStore",
        secret,
        {
            "WMLtypeIn": "well",
            "QueryIn": changed_query("1900-01-01T00:00:00.000Z"),
            "OptionsIn": "returnElements=id-only",
        },
    )
    assert result(older) == 1
    older_xml = field(older, "XMLout")
    assert 'uid="w-2"' in older_xml
    assert 'uid="w-3"' in older_xml


async def test_wmls_requires_authentication(admin_client: AsyncClient) -> None:
    response = await admin_client.post(
        "/witsml",
        content=envelope("WMLS_GetVersion"),
        headers={"content-type": "text/xml; charset=utf-8"},
    )
    assert response.status_code == 401


async def test_get_base_message(admin_client: AsyncClient, csrf: str) -> None:
    secret = await create_writer(admin_client, csrf)
    response = await soap(
        admin_client, "WMLS_GetBaseMsg", secret, {"ReturnValueIn": "-414"}
    )
    assert response.status_code == 200
    assert "rights" in field(response, "Result")


async def test_get_cap_data_version_contract(
    admin_client: AsyncClient, csrf: str
) -> None:
    secret = await create_writer(admin_client, csrf)

    absent = await soap(admin_client, "WMLS_GetCap", secret, {"OptionsIn": ""})
    assert result(absent) == 1

    invalid = await soap(
        admin_client,
        "WMLS_GetCap",
        secret,
        {"OptionsIn": "dataVersion=1.3.1.1"},
    )
    assert result(invalid) == -423

    legacy_xml = await soap(
        admin_client,
        "WMLS_GetCap",
        secret,
        {"OptionsIn": "<options><dataVersion>1.4.1.1</dataVersion></options>"},
    )
    assert result(legacy_xml) == 1


async def test_add_rejects_nonconforming_xml(
    admin_client: AsyncClient, csrf: str
) -> None:
    secret = await create_writer(admin_client, csrf)
    response = await soap(
        admin_client,
        "WMLS_AddToStore",
        secret,
        {
            "WMLtypeIn": "well",
            # Falta version="1.4.1.1": el XSD oficial debe rechazarlo.
            "XMLin": f'<wells xmlns="{WITSML_NS}"><well uid="w-x">'
            "<name>No Version</name></well></wells>",
            "OptionsIn": "",
        },
    )
    assert result(response) == -409


async def test_published_wsdl_is_official(admin_client: AsyncClient) -> None:
    response = await admin_client.get("/witsml")
    assert response.status_code == 200
    published = response.text

    official = OFFICIAL_WSDL.read_text(encoding="utf-8")
    assert "targetNamespace='http://www.witsml.org/wsdl/120'" in published
    assert "http://www.witsml.org/message/120" in published
    assert "http://www.witsml.org/action/120/Store.WMLS_GetCap" in published
    assert "location='http://testserver/witsml'" in published
    # Salvo la dirección, el WSDL publicado es idéntico al oficial.
    assert published.replace(
        "location='http://testserver/witsml'",
        "location='http://yourorg.com/yourwebservice'",
    ) == official


async def test_wmls_gzip_responses(admin_client: AsyncClient, csrf: str) -> None:
    """D-01: las respuestas WMLS usan gzip cuando el cliente lo acepta."""
    secret = await create_writer(admin_client, csrf)
    credentials = base64.b64encode(f"acme.writer:{secret}".encode()).decode()
    headers = {
        "content-type": "text/xml; charset=utf-8",
        "authorization": f"Basic {credentials}",
    }

    compressed = await admin_client.post(
        "/witsml",
        content=envelope("WMLS_GetVersion"),
        headers={**headers, "accept-encoding": "gzip"},
    )
    assert compressed.status_code == 200, compressed.text
    assert compressed.headers["content-encoding"] == "gzip"
    assert "Accept-Encoding" in compressed.headers["vary"]
    root = etree.fromstring(compressed.content)
    assert root.tag == f"{{{SOAP_NS}}}Envelope"
    assert field(compressed, "Result") == "1.4.1.1"

    refused = await admin_client.post(
        "/witsml",
        content=envelope("WMLS_GetVersion"),
        headers={**headers, "accept-encoding": "gzip;q=0, identity"},
    )
    assert refused.status_code == 200
    assert "content-encoding" not in refused.headers
    assert field(refused, "Result") == "1.4.1.1"


async def test_read_outputs_conform_to_official_xsd(
    admin_client: AsyncClient, csrf: str
) -> None:
    secret = await create_writer(admin_client, csrf)
    for object_type, xml in (
        ("well", WELL),
        ("wellbore", WELLBORE),
        ("log", LOG),
        ("trajectory", TRAJECTORY),
    ):
        added = await soap(
            admin_client,
            "WMLS_AddToStore",
            secret,
            {"WMLtypeIn": object_type, "XMLin": xml, "OptionsIn": ""},
        )
        assert result(added) == 1, (object_type, field(added, "SuppMsgOut"))

    queries = {
        "well": f'<wells xmlns="{WITSML_NS}"><well uid="w-1"/></wells>',
        "wellbore": (
            f'<wellbores xmlns="{WITSML_NS}"><wellbore uid="wb-1" '
            'uidWell="w-1"/></wellbores>'
        ),
        "log": (
            f'<logs xmlns="{WITSML_NS}"><log uid="log-1" uidWell="w-1" '
            'uidWellbore="wb-1"/></logs>'
        ),
        "trajectory": (
            f'<trajectorys xmlns="{WITSML_NS}"><trajectory uid="tr-1" '
            'uidWell="w-1" uidWellbore="wb-1"/></trajectorys>'
        ),
        "changeLog": f'<changeLogs xmlns="{WITSML_NS}"/>',
    }
    validator = LxmlXsdValidator()
    assert validator.available
    for object_type, query in queries.items():
        read = await soap(
            admin_client,
            "WMLS_GetFromStore",
            secret,
            {"WMLtypeIn": object_type, "QueryIn": query, "OptionsIn": ""},
        )
        assert result(read) == 1, (object_type, field(read, "SuppMsgOut"))
        xml_out = field(read, "XMLout")
        document = etree.fromstring(xml_out.encode("utf-8"))
        validator.validate_document(object_type, document, operation="read")
