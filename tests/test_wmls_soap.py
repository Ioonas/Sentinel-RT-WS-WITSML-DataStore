"""Pruebas de extremo a extremo del endpoint SOAP WMLS."""

from __future__ import annotations

import base64
from xml.sax.saxutils import escape

import pytest
from httpx import AsyncClient
from lxml import etree

from sentinel.wmls_transport.wsdl import OFFICIAL_WSDL
from sentinel.xml_schema.namespaces import ACTION_NS, MESSAGE_NS, SOAP_NS, WITSML_NS
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
    "<name>Well One</name></well></wells>"
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
    assert "well" in field(capabilities, "CapabilitiesOut")

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
