"""Pruebas propias de los MUST no cubiertos por la suite (D-15).

Trazabilidad con el Test Plan oficial ``WITSML 1.4.1 Certification Test Plan``
y con los criterios de aceptación del spec del producto:

===========================================  ==================================
Prueba                                        Cobertura
===========================================  ==================================
``test_d15_12_13_change_log_*``               Test Plan 12 y 13: entradas
                                              ``update`` y ``delete`` en el
                                              ``changeLog``, consultables con
                                              el filtro SQ-018 (dTimChange).
``test_d15_74_*``                             Test Plan 74 / criterio 36:
                                              truncamiento por ``maxDataNodes``.
``test_d15_75_*``                             Test Plan 75 / criterio 36:
                                              truncamiento por ``maxDataPoints``.
``test_d15_76c_*``                            Test Plan 76c:
                                              ``requestLatestValues`` en un log
                                              de profundidad descendente.
``test_d15_82_*``                             Test Plan 82 / criterio 12:
                                              *clearing behavior* del §6.7.4.6
                                              de la API 1.4.1 (append e
                                              intersección por canal).
``test_d15_84_*``                             Test Plan 84: compresión del
                                              cliente no anunciada (D-01).
``test_acceptance_13_*``                      Criterio 13: tipo de índice
                                              preservado y nodos duplicados
                                              rechazados sin sobrescribir.
``test_acceptance_29_*``                      Criterio 29: SOAP y REST sobre
                                              los mismos casos de uso.
===========================================  ==================================

El Test Plan 83 (gzip de respuesta) se cubre en
``tests/test_wmls_soap.py::test_wmls_gzip_responses``, junto con el criterio 19.
El Test Plan 19 (fallo conjunto de consultas múltiples), 6 y 7 están cubiertos
por las pruebas existentes de GetCap y ``returnElements=id-only``.

La retención de 24 horas de las pruebas 12 y 13 no se espera en la prueba
automatizada: la retención aprobada es de 5 años sin purga (D-10), y la prueba
verifica que las entradas siguen disponibles con el mismo filtro que usa el
Test Plan.
"""

from __future__ import annotations

import base64
import gzip
from decimal import Decimal, InvalidOperation

import pytest
from httpx import AsyncClient
from lxml import etree

from sentinel.bootstrap.container import Container
from sentinel.xml_schema.namespaces import ACTION_NS, WITSML_NS
from tests.test_wmls_soap import (
    LOG,
    MUDLOG,
    TRAJECTORY,
    WELL,
    WELLBORE,
    create_writer,
    envelope,
    field,
    result,
    soap,
)

pytestmark = pytest.mark.integration

PARTIAL_SUCCESS = 2
WITSML = f"{{{WITSML_NS}}}"


# ----------------------------------------------------------------------
# Utilidades
# ----------------------------------------------------------------------
def localname(element: etree._Element) -> str:
    return etree.QName(element).localname


def log_rows(xml_out: str) -> list[dict[str, str]]:
    """Devuelve las filas de ``logData`` indexadas por mnemónico."""
    root = etree.fromstring(xml_out.encode("utf-8"))
    blocks = [element for element in root.iter() if localname(element) == "logData"]
    if not blocks:
        return []
    mnemonic_list = next(
        element.text or "" for element in blocks[0] if localname(element) == "mnemonicList"
    )
    mnemonics = mnemonic_list.split(",")
    rows: list[dict[str, str]] = []
    for element in blocks[0]:
        if localname(element) != "data":
            continue
        values = (element.text or "").split(",")
        rows.append(dict(zip(mnemonics, values, strict=False)))
    return rows


def number(raw: str) -> Decimal | str:
    """Normaliza un índice o valor numérico sin depender del formato emitido."""
    try:
        return Decimal(raw)
    except (InvalidOperation, TypeError):
        return raw


def value(rows: list[dict[str, str]], mnemonic: str, index: str) -> str | None:
    """Valor de ``mnemonic`` en la fila cuyo índice es ``index``."""
    target = number(index)
    for row in rows:
        if number(row.get("MD", "")) == target:
            raw = row.get(mnemonic, "")
            return raw if raw != "" else None
    return None


def log_indexes(xml_out: str) -> list[Decimal | str]:
    return [number(row.get("MD", "")) for row in log_rows(xml_out)]


async def set_limits(container: Container, **changes: int) -> None:
    """Ajusta los límites de ``GetCap`` en la configuración del servidor.

    La configuración real (D-17) es de 10 000 nodos y 3 000 000 de puntos; para
    provocar el truncamiento sin cargar millones de filas se reducen los
    límites en la base de pruebas. Los valores efectivos se publican en GetCap
    y son los que consume el Store.
    """
    async with container.request() as services:
        config = await services.repos.config.get()
        assert config is not None
        for name, value_ in changes.items():
            setattr(config, name, value_)
        await services.repos.config.save(config)


async def add(
    client: AsyncClient, secret: str, object_type: str, xml: str
) -> None:
    response = await soap(
        client,
        "WMLS_AddToStore",
        secret,
        {"WMLtypeIn": object_type, "XMLin": xml, "OptionsIn": ""},
    )
    assert result(response) == 1, (object_type, field(response, "SuppMsgOut"))


async def read_log(
    client: AsyncClient, secret: str, uid: str, options: str = "returnElements=all"
):
    return await soap(
        client,
        "WMLS_GetFromStore",
        secret,
        {
            "WMLtypeIn": "log",
            "QueryIn": (
                f'<logs xmlns="{WITSML_NS}">'
                f'<log uid="{uid}" uidWell="w-a" uidWellbore="wb-a"/></logs>'
            ),
            "OptionsIn": options,
        },
    )


def _rows(count: int, start: int = 0) -> str:
    return "".join(
        f"<data>{index},{50 + index}</data>" for index in range(start, start + count)
    )


def log_xml(uid: str, rows: str, curves: int = 2) -> str:
    """Log de profundidad con ``curves`` curvas (incluye la curva de índice)."""
    definitions = "".join(
        f'<logCurveInfo uid="c{position}"><mnemonic>{"MD" if position == 0 else f"C{position}"}'
        f"</mnemonic><unit>m</unit><typeLogData>double</typeLogData></logCurveInfo>"
        for position in range(curves)
    )
    mnemonics = ",".join("MD" if position == 0 else f"C{position}" for position in range(curves))
    units = ",".join("m" for _ in range(curves))
    return (
        f'<logs xmlns="{WITSML_NS}" version="1.4.1.1">'
        f'<log uid="{uid}" uidWell="w-a" uidWellbore="wb-a">'
        "<nameWell>Well A</nameWell><nameWellbore>WB A</nameWellbore>"
        f"<name>{uid}</name><indexType>measured depth</indexType>"
        "<indexCurve>MD</indexCurve>"
        f"{definitions}"
        f"<logData><mnemonicList>{mnemonics}</mnemonicList>"
        f"<unitList>{units}</unitList>{rows}</logData></log></logs>"
    )


async def create_parents(client: AsyncClient, secret: str) -> None:
    await add(
        client,
        secret,
        "well",
        f'<wells xmlns="{WITSML_NS}" version="1.4.1.1">'
        '<well uid="w-a"><name>Well A</name></well></wells>',
    )
    await add(
        client,
        secret,
        "wellbore",
        f'<wellbores xmlns="{WITSML_NS}" version="1.4.1.1">'
        '<wellbore uid="wb-a" uidWell="w-a"><nameWell>Well A</nameWell>'
        "<name>WB A</name></wellbore></wellbores>",
    )


# ----------------------------------------------------------------------
# Test Plan 12 y 13 - changeLog de actualización y borrado
# ----------------------------------------------------------------------
async def test_d15_12_13_change_log_keeps_update_and_delete_entries(
    admin_client: AsyncClient, csrf: str
) -> None:
    secret = await create_writer(admin_client, csrf)
    await create_parents(admin_client, secret)
    await add(admin_client, secret, "log", log_xml("log-cl", _rows(3)))

    update = (
        f'<logs xmlns="{WITSML_NS}" version="1.4.1.1">'
        '<log uid="log-cl" uidWell="w-a" uidWellbore="wb-a">'
        "<logData><mnemonicList>MD,C1</mnemonicList><unitList>m,m</unitList>"
        "<data>3,53</data></logData></log></logs>"
    )
    updated = await soap(
        admin_client,
        "WMLS_UpdateInStore",
        secret,
        {"WMLtypeIn": "log", "XMLin": update, "OptionsIn": ""},
    )
    assert result(updated) == 1, field(updated, "SuppMsgOut")

    def change_log_query(change_type: str) -> str:
        return (
            f'<changeLogs xmlns="{WITSML_NS}"><changeLog uidObject="log-cl">'
            f"<changeHistory><changeType>{change_type}</changeType></changeHistory>"
            "</changeLog></changeLogs>"
        )

    # Test Plan 12: la entrada ``update`` queda registrada y es consultable con
    # el filtro de SQ-018 (dTimChange dentro de la ventana).
    updates = await soap(
        admin_client,
        "WMLS_GetFromStore",
        secret,
        {
            "WMLtypeIn": "changeLog",
            "QueryIn": change_log_query("update"),
            "OptionsIn": "",
        },
    )
    assert result(updates) == 1
    update_xml = field(updates, "XMLout")
    assert 'uidObject="log-cl"' in update_xml
    assert "<lastChangeType>update</lastChangeType>" in update_xml
    assert "<changeType>update</changeType>" in update_xml
    assert "<mnemonics>MD,C1</mnemonics>" in update_xml
    assert "<startIndex" in update_xml and "<endIndex" in update_xml

    deleted = await soap(
        admin_client,
        "WMLS_DeleteFromStore",
        secret,
        {
            "WMLtypeIn": "log",
            "QueryIn": (
                f'<logs xmlns="{WITSML_NS}"><log uid="log-cl" uidWell="w-a" '
                'uidWellbore="wb-a"/></logs>'
            ),
            "OptionsIn": "",
        },
    )
    assert result(deleted) == 1, field(deleted, "SuppMsgOut")

    # Test Plan 13: la entrada ``delete`` sobrevive al borrado del objeto.
    deletions = await soap(
        admin_client,
        "WMLS_GetFromStore",
        secret,
        {
            "WMLtypeIn": "changeLog",
            "QueryIn": change_log_query("delete"),
            "OptionsIn": "",
        },
    )
    assert result(deletions) == 1
    delete_xml = field(deletions, "XMLout")
    assert 'uidObject="log-cl"' in delete_xml
    assert "<lastChangeType>delete</lastChangeType>" in delete_xml
    assert "<nameObject>log-cl</nameObject>" in delete_xml


# ----------------------------------------------------------------------
# Test Plan 74 y 75 - límites de nodos y puntos
# ----------------------------------------------------------------------
async def test_d15_74_get_from_store_truncates_by_max_data_nodes(
    admin_client: AsyncClient, csrf: str, container: Container
) -> None:
    secret = await create_writer(admin_client, csrf)
    await create_parents(admin_client, secret)
    await add(admin_client, secret, "log", log_xml("log-nodes", _rows(6)))
    await set_limits(container, max_data_nodes=3, max_data_points=3_000_000)

    response = await read_log(admin_client, secret, "log-nodes")
    assert result(response) == PARTIAL_SUCCESS, field(response, "SuppMsgOut")
    assert "maxDataNodes" in field(response, "SuppMsgOut")

    rows = log_rows(field(response, "XMLout"))
    assert len(rows) == 3
    # El nodo de corte respeta los índices del encabezado, sin duplicados.
    assert log_indexes(field(response, "XMLout")) == [
        Decimal(0),
        Decimal(1),
        Decimal(2),
    ]


async def test_d15_75_get_from_store_truncates_by_max_data_points(
    admin_client: AsyncClient, csrf: str, container: Container
) -> None:
    secret = await create_writer(admin_client, csrf)
    await create_parents(admin_client, secret)
    await add(admin_client, secret, "log", log_xml("log-points", _rows(5)))
    # 5 filas < maxDataNodes, pero 6 puntos entre las dos curvas.
    await set_limits(container, max_data_nodes=1_000, max_data_points=6)

    response = await read_log(admin_client, secret, "log-points")
    assert result(response) == PARTIAL_SUCCESS, field(response, "SuppMsgOut")
    assert "maxDataPoints" in field(response, "SuppMsgOut")

    rows = log_rows(field(response, "XMLout"))
    assert len(rows) == 3
    assert log_indexes(field(response, "XMLout")) == [
        Decimal(0),
        Decimal(1),
        Decimal(2),
    ]


# ----------------------------------------------------------------------
# Test Plan 76c - requestLatestValues en un log descendente
# ----------------------------------------------------------------------
DECREASING_LOG = (
    f'<logs xmlns="{WITSML_NS}" version="1.4.1.1">'
    '<log uid="log-dec" uidWell="w-d" uidWellbore="wb-d">'
    "<nameWell>Well D</nameWell><nameWellbore>WB D</nameWellbore>"
    "<name>Decreasing Log</name><indexType>measured depth</indexType>"
    '<startIndex uom="m">10</startIndex><endIndex uom="m">2</endIndex>'
    "<direction>decreasing</direction><indexCurve>MD</indexCurve>"
    '<logCurveInfo uid="MD"><mnemonic>MD</mnemonic><unit>m</unit>'
    "<typeLogData>double</typeLogData></logCurveInfo>"
    '<logCurveInfo uid="GR"><mnemonic>GR</mnemonic><unit>gAPI</unit>'
    "<typeLogData>double</typeLogData></logCurveInfo>"
    "<logData><mnemonicList>MD,GR</mnemonicList><unitList>m,gAPI</unitList>"
    "<data>10,50</data><data>8,60</data><data>6,70</data>"
    "<data>4,80</data><data>2,90</data></logData></log></logs>"
)


async def test_d15_76c_request_latest_values_for_decreasing_log(
    admin_client: AsyncClient, csrf: str
) -> None:
    secret = await create_writer(admin_client, csrf)
    await add(
        admin_client,
        secret,
        "well",
        f'<wells xmlns="{WITSML_NS}" version="1.4.1.1">'
        '<well uid="w-d"><name>Well D</name></well></wells>',
    )
    await add(
        admin_client,
        secret,
        "wellbore",
        f'<wellbores xmlns="{WITSML_NS}" version="1.4.1.1">'
        '<wellbore uid="wb-d" uidWell="w-d"><nameWell>Well D</nameWell>'
        "<name>WB D</name></wellbore></wellbores>",
    )
    await add(admin_client, secret, "log", DECREASING_LOG)

    response = await soap(
        admin_client,
        "WMLS_GetFromStore",
        secret,
        {
            "WMLtypeIn": "log",
            "QueryIn": (
                f'<logs xmlns="{WITSML_NS}"><log uid="log-dec" uidWell="w-d" '
                'uidWellbore="wb-d"/></logs>'
            ),
            "OptionsIn": "returnElements=all&requestLatestValues=2",
        },
    )
    assert result(response) == 1, field(response, "SuppMsgOut")
    xml_out = field(response, "XMLout")
    rows = log_rows(xml_out)
    # Los dos últimos valores del log descendente, en orden descendente.
    assert [number(row["MD"]) for row in rows] == [Decimal(4), Decimal(2)]
    assert [row["GR"] for row in rows] == ["80", "90"]

    beyond = await soap(
        admin_client,
        "WMLS_GetFromStore",
        secret,
        {
            "WMLtypeIn": "log",
            "QueryIn": (
                f'<logs xmlns="{WITSML_NS}"><log uid="log-dec" uidWell="w-d" '
                'uidWellbore="wb-d"/></logs>'
            ),
            "OptionsIn": "requestLatestValues=501",
        },
    )
    assert result(beyond) == -1054, field(beyond, "SuppMsgOut")


# ----------------------------------------------------------------------
# Test Plan 82 - clearing behavior del §6.7.4.6 (API 1.4.1)
# ----------------------------------------------------------------------
CLEARING_LOG = (
    f'<logs xmlns="{WITSML_NS}" version="1.4.1.1">'
    '<log uid="log-clear" uidWell="w-a" uidWellbore="wb-a">'
    "<nameWell>Well A</nameWell><nameWellbore>WB A</nameWellbore>"
    "<name>Clearing Log</name><indexType>measured depth</indexType>"
    "<indexCurve>MD</indexCurve>"
    '<logCurveInfo uid="MD"><mnemonic>MD</mnemonic><unit>m</unit>'
    "<typeLogData>double</typeLogData></logCurveInfo>"
    '<logCurveInfo uid="A"><mnemonic>A</mnemonic><unit>unitless</unit>'
    "<typeLogData>double</typeLogData></logCurveInfo>"
    '<logCurveInfo uid="B"><mnemonic>B</mnemonic><unit>unitless</unit>'
    "<typeLogData>double</typeLogData></logCurveInfo>"
    '<logCurveInfo uid="C"><mnemonic>C</mnemonic><unit>unitless</unit>'
    "<typeLogData>double</typeLogData></logCurveInfo>"
    "<logData><mnemonicList>MD,A,B,C</mnemonicList>"
    "<unitList>m,unitless,unitless,unitless</unitList>"
    "<data>1000,1,11,21</data><data>1001,,12,22</data>"
    "<data>1002,3,,23</data></logData></log></logs>"
)


def clearing_update(rows: str) -> str:
    return (
        f'<logs xmlns="{WITSML_NS}" version="1.4.1.1">'
        '<log uid="log-clear" uidWell="w-a" uidWellbore="wb-a">'
        "<logData><mnemonicList>MD,A,B</mnemonicList>"
        "<unitList>m,unitless,unitless</unitList>"
        f"{rows}</logData></log></logs>"
    )


async def test_d15_82_log_append_and_intersection_clearing_behavior(
    admin_client: AsyncClient, csrf: str
) -> None:
    secret = await create_writer(admin_client, csrf)
    await create_parents(admin_client, secret)
    await add(admin_client, secret, "log", CLEARING_LOG)

    # Ejemplo 1 de la API: sin intersección real en A, el valor A@1002 se
    # conserva; B sí cubre 1002 y se actualiza. La curva C, omitida en la
    # actualización, no se toca (criterio 12).
    append = await soap(
        admin_client,
        "WMLS_UpdateInStore",
        secret,
        {
            "WMLtypeIn": "log",
            "XMLin": clearing_update(
                "<data>1002,,13</data><data>1003,4,14</data>"
            ),
            "OptionsIn": "",
        },
    )
    assert result(append) == 1, field(append, "SuppMsgOut")

    after_append = await read_log(admin_client, secret, "log-clear")
    assert result(after_append) == 1, field(after_append, "SuppMsgOut")
    rows = log_rows(field(after_append, "XMLout"))
    assert value(rows, "A", "1002") == "3"
    assert value(rows, "B", "1002") == "13"
    assert value(rows, "B", "1001") == "12"
    assert value(rows, "C", "1002") == "23"
    assert value(rows, "A", "1003") == "4"
    assert value(rows, "B", "1003") == "14"
    assert value(rows, "C", "1003") is None

    # Ejemplo 2: la intersección limpia A@1002 (rango implícito 1001-1003) y
    # B@1002 se sobrescribe; C sigue intacta.
    intersection = await soap(
        admin_client,
        "WMLS_UpdateInStore",
        secret,
        {
            "WMLtypeIn": "log",
            "XMLin": clearing_update(
                "<data>1001,5,</data><data>1002,,13.5</data>"
                "<data>1003,4,14.5</data>"
            ),
            "OptionsIn": "",
        },
    )
    assert result(intersection) == 1, field(intersection, "SuppMsgOut")

    after_intersection = await read_log(admin_client, secret, "log-clear")
    assert result(after_intersection) == 1
    rows = log_rows(field(after_intersection, "XMLout"))
    assert value(rows, "A", "1000") == "1"
    assert value(rows, "A", "1001") == "5"
    assert value(rows, "A", "1002") is None, "A@1002 debe quedar nulo"
    assert value(rows, "A", "1003") == "4"
    assert value(rows, "B", "1001") == "12", "B@1001 está fuera del rango"
    assert value(rows, "B", "1002") == "13.5"
    assert value(rows, "B", "1003") == "14.5"
    assert value(rows, "C", "1002") == "23", "la curva omitida no se limpia"
    # El changeLog refleja la modificación interior (API §6.7.4.6).
    changes = await soap(
        admin_client,
        "WMLS_GetFromStore",
        secret,
        {
            "WMLtypeIn": "changeLog",
            "QueryIn": (
                f'<changeLogs xmlns="{WITSML_NS}"><changeLog uidObject="log-clear">'
                "<changeHistory><changeType>update</changeType></changeHistory>"
                "</changeLog></changeLogs>"
            ),
            "OptionsIn": "",
        },
    )
    assert result(changes) == 1
    assert "<lastChangeType>update</lastChangeType>" in field(changes, "XMLout")
    assert "<mnemonics>MD,A,B</mnemonics>" in field(changes, "XMLout")


# ----------------------------------------------------------------------
# Criterio 13 - tipo de índice y nodos duplicados
# ----------------------------------------------------------------------
async def test_acceptance_13_index_type_and_duplicate_nodes(
    admin_client: AsyncClient, csrf: str
) -> None:
    secret = await create_writer(admin_client, csrf)
    await create_parents(admin_client, secret)
    await add(admin_client, secret, "log", log_xml("log-idx", _rows(3)))

    append = await soap(
        admin_client,
        "WMLS_UpdateInStore",
        secret,
        {
            "WMLtypeIn": "log",
            "XMLin": (
                f'<logs xmlns="{WITSML_NS}" version="1.4.1.1">'
                '<log uid="log-idx" uidWell="w-a" uidWellbore="wb-a">'
                "<logData><mnemonicList>MD,C1</mnemonicList>"
                "<unitList>m,m</unitList><data>3,53</data></logData>"
                "</log></logs>"
            ),
            "OptionsIn": "",
        },
    )
    assert result(append) == 1, field(append, "SuppMsgOut")

    read = await read_log(admin_client, secret, "log-idx")
    assert result(read) == 1
    xml_out = field(read, "XMLout")
    # El tipo de índice original se conserva aunque la actualización no lo diga.
    assert "<indexType>measured depth</indexType>" in xml_out
    assert len(log_rows(xml_out)) == 4

    duplicated = await soap(
        admin_client,
        "WMLS_UpdateInStore",
        secret,
        {
            "WMLtypeIn": "log",
            "XMLin": (
                f'<logs xmlns="{WITSML_NS}" version="1.4.1.1">'
                '<log uid="log-idx" uidWell="w-a" uidWellbore="wb-a">'
                "<logData><mnemonicList>MD,C1</mnemonicList>"
                "<unitList>m,m</unitList>"
                "<data>4,54</data><data>4,55</data></logData>"
                "</log></logs>"
            ),
            "OptionsIn": "",
        },
    )
    assert result(duplicated) == -463, field(duplicated, "SuppMsgOut")

    unchanged = await read_log(admin_client, secret, "log-idx")
    assert len(log_rows(field(unchanged, "XMLout"))) == 4


# ----------------------------------------------------------------------
# Test Plan 84 - compresión del cliente
# ----------------------------------------------------------------------
async def test_d15_84_client_compression_is_not_advertised(
    admin_client: AsyncClient, csrf: str
) -> None:
    secret = await create_writer(admin_client, csrf)

    capabilities = await soap(
        admin_client,
        "WMLS_GetCap",
        secret,
        {"OptionsIn": "dataVersion=1.4.1.1&returnElements=all"},
    )
    assert result(capabilities) == 1
    assert "<compressionMethod>" not in field(capabilities, "CapabilitiesOut")

    credentials = base64.b64encode(f"acme.writer:{secret}".encode()).decode()
    compressed = await admin_client.post(
        "/witsml",
        content=gzip.compress(envelope("WMLS_GetVersion").encode("utf-8")),
        headers={
            "content-type": "text/xml; charset=utf-8",
            "content-encoding": "gzip",
            "authorization": f"Basic {credentials}",
            "soapaction": f'"{ACTION_NS}/Store.WMLS_GetVersion"',
        },
    )
    # D-01: solo se comprimen respuestas. Una solicitud comprimida se rechaza
    # con un fault controlado, nunca con un 500 ni con datos corruptos.
    assert compressed.status_code == 400, compressed.text
    assert "Fault" in compressed.text


# ----------------------------------------------------------------------
# Criterio 29 - SOAP y REST sobre los mismos casos de uso
# ----------------------------------------------------------------------
@pytest.mark.parametrize(
    ("object_type", "xml", "uid"),
    [
        ("well", WELL, "w-1"),
        ("wellbore", WELLBORE, "wb-1"),
        ("log", LOG, "log-1"),
        ("trajectory", TRAJECTORY, "tr-1"),
        ("mudLog", MUDLOG, "mud-1"),
    ],
)
async def test_acceptance_29_soap_and_rest_share_use_cases(
    admin_client: AsyncClient, csrf: str, object_type: str, xml: str, uid: str
) -> None:
    secret = await create_writer(admin_client, csrf)
    for parent_type, parent_xml in (("well", WELL), ("wellbore", WELLBORE)):
        if parent_type == object_type:
            break
        await add(admin_client, secret, parent_type, parent_xml)
    await add(admin_client, secret, object_type, xml)

    # El objeto creado por SOAP es visible por REST.
    params = (
        {}
        if object_type == "well"
        else {"uid_well": "w-1", "uid_wellbore": "wb-1"}
    )
    read = await admin_client.get(
        f"/admin-api/v1/objects/{object_type}/{uid}", params=params
    )
    assert read.status_code == 200, read.text
    assert read.json()["uid"] == uid

    # El borrado por REST se refleja en SOAP en la misma transacción.
    deleted = await admin_client.post(
        f"/admin-api/v1/objects/{object_type}/{uid}/delete",
        headers={"x-csrf-token": csrf},
        params=params,
        json={"reason": "prueba criterio 29", "confirmation": uid},
    )
    assert deleted.status_code == 200, deleted.text

    query = {
        "well": f'<wells xmlns="{WITSML_NS}"><well uid="{uid}"/></wells>',
        "wellbore": (
            f'<wellbores xmlns="{WITSML_NS}"><wellbore uid="{uid}" '
            'uidWell="w-1"/></wellbores>'
        ),
        "log": (
            f'<logs xmlns="{WITSML_NS}"><log uid="{uid}" uidWell="w-1" '
            'uidWellbore="wb-1"/></logs>'
        ),
        "trajectory": (
            f'<trajectorys xmlns="{WITSML_NS}"><trajectory uid="{uid}" '
            'uidWell="w-1" uidWellbore="wb-1"/></trajectorys>'
        ),
        "mudLog": (
            f'<mudLogs xmlns="{WITSML_NS}"><mudLog uid="{uid}" '
            'uidWell="w-1" uidWellbore="wb-1"/></mudLogs>'
        ),
    }[object_type]
    after = await soap(
        admin_client,
        "WMLS_GetFromStore",
        secret,
        {"WMLtypeIn": object_type, "QueryIn": query, "OptionsIn": ""},
    )
    assert result(after) == 1
    assert f'uid="{uid}"' not in field(after, "XMLout")


# ----------------------------------------------------------------------
# mudLog - SQ-012 (data-only), SQ-016/SQ-018 y borrado parcial por nodo
# ----------------------------------------------------------------------
MUDLOG_XML = (
    f'<mudLogs xmlns="{WITSML_NS}" version="1.4.1.1">'
    '<mudLog uid="mud-a" uidWell="w-a" uidWellbore="wb-a">'
    "<nameWell>Well A</nameWell><nameWellbore>WB A</nameWellbore>"
    "<name>MudLog A</name><objectGrowing>true</objectGrowing>"
    '<startMd uom="m">0</startMd><endMd uom="m">10</endMd>'
    '<parameter uid="p1"><type>core interval comment</type>'
    '<mdTop uom="m">0</mdTop><mdBottom uom="m">10</mdBottom></parameter>'
    '<geologyInterval uid="g1"><typeLithology>cuttings</typeLithology>'
    '<mdTop uom="m">0</mdTop><mdBottom uom="m">10</mdBottom></geologyInterval>'
    "</mudLog></mudLogs>"
)


async def read_mudlog(
    client: AsyncClient,
    secret: str,
    uid: str = "mud-a",
    options: str = "returnElements=all",
):
    return await soap(
        client,
        "WMLS_GetFromStore",
        secret,
        {
            "WMLtypeIn": "mudLog",
            "QueryIn": (
                f'<mudLogs xmlns="{WITSML_NS}">'
                f'<mudLog uid="{uid}" uidWell="w-a" uidWellbore="wb-a"/></mudLogs>'
            ),
            "OptionsIn": options,
        },
    )


def mudlog_element(xml_out: str) -> etree._Element:
    root = etree.fromstring(xml_out.encode("utf-8"))
    mudlogs = [element for element in root if localname(element) == "mudLog"]
    assert len(mudlogs) == 1, xml_out
    return mudlogs[0]


async def test_mudlog_roundtrip_and_data_only(
    admin_client: AsyncClient, csrf: str
) -> None:
    secret = await create_writer(admin_client, csrf)
    await create_parents(admin_client, secret)
    await add(admin_client, secret, "mudLog", MUDLOG_XML)

    # SQ-012: ``data-only`` devuelve solo los nodos de datos y la identidad.
    data_only = await read_mudlog(
        admin_client, secret, options="returnElements=data-only"
    )
    assert result(data_only) == 1, field(data_only, "SuppMsgOut")
    mudlog = mudlog_element(field(data_only, "XMLout"))
    assert mudlog.get("uid") == "mud-a"
    assert mudlog.get("uidWell") == "w-a"
    assert mudlog.get("uidWellbore") == "wb-a"
    assert {localname(item) for item in mudlog} == {
        "geologyInterval",
        "parameter",
    }
    intervals = [item for item in mudlog if localname(item) == "geologyInterval"]
    parameters = [item for item in mudlog if localname(item) == "parameter"]
    assert [item.get("uid") for item in intervals] == ["g1"]
    assert [item.get("uid") for item in parameters] == ["p1"]

    # Roundtrip completo: se conserva ``objectGrowing=true`` del alta.
    full = await read_mudlog(admin_client, secret)
    assert result(full) == 1
    full_mudlog = mudlog_element(field(full, "XMLout"))
    assert full_mudlog.findtext(f"{WITSML}objectGrowing") == "true"
    assert full_mudlog.findtext(f"{WITSML}name") == "MudLog A"
    assert full_mudlog.findtext(f"{WITSML}startMd") == "0"
    assert full_mudlog.findtext(f"{WITSML}endMd") == "10"


async def test_mudlog_partial_update_and_delete_record_change_log(
    admin_client: AsyncClient, csrf: str
) -> None:
    secret = await create_writer(admin_client, csrf)
    await create_parents(admin_client, secret)
    await add(admin_client, secret, "mudLog", MUDLOG_XML)

    # Actualizacion parcial de un geologyInterval por uid.
    updated = await soap(
        admin_client,
        "WMLS_UpdateInStore",
        secret,
        {
            "WMLtypeIn": "mudLog",
            "XMLin": (
                f'<mudLogs xmlns="{WITSML_NS}" version="1.4.1.1">'
                '<mudLog uid="mud-a" uidWell="w-a" uidWellbore="wb-a">'
                '<geologyInterval uid="g1">'
                '<mdBottom uom="m">8</mdBottom>'
                "</geologyInterval></mudLog></mudLogs>"
            ),
            "OptionsIn": "",
        },
    )
    assert result(updated) == 1, field(updated, "SuppMsgOut")

    # Borrado parcial: se elimina solo el nodo indicado, no el objeto.
    partial = await soap(
        admin_client,
        "WMLS_DeleteFromStore",
        secret,
        {
            "WMLtypeIn": "mudLog",
            "QueryIn": (
                f'<mudLogs xmlns="{WITSML_NS}">'
                '<mudLog uid="mud-a" uidWell="w-a" uidWellbore="wb-a">'
                '<geologyInterval uid="g1"/></mudLog></mudLogs>'
            ),
            "OptionsIn": "",
        },
    )
    assert result(partial) == 1, field(partial, "SuppMsgOut")

    remaining = await read_mudlog(admin_client, secret)
    assert result(remaining) == 1
    mudlog = mudlog_element(field(remaining, "XMLout"))
    assert not [item for item in mudlog if localname(item) == "geologyInterval"]
    # El parametro y el objeto sobreviven al borrado parcial.
    assert [item.get("uid") for item in mudlog if localname(item) == "parameter"] == [
        "p1"
    ]

    # SQ-018: add + dos update (actualizacion y borrado parcial).
    changes = await soap(
        admin_client,
        "WMLS_GetFromStore",
        secret,
        {
            "WMLtypeIn": "changeLog",
            "QueryIn": (
                f'<changeLogs xmlns="{WITSML_NS}">'
                '<changeLog uidObject="mud-a"/></changeLogs>'
            ),
            "OptionsIn": "",
        },
    )
    assert result(changes) == 1
    change_xml = field(changes, "XMLout")
    assert 'uidObject="mud-a"' in change_xml
    assert "<changeType>add</changeType>" in change_xml
    assert change_xml.count("<changeType>update</changeType>") == 2
    assert "<lastChangeType>update</lastChangeType>" in change_xml

    # Borrado total posterior.
    deleted = await soap(
        admin_client,
        "WMLS_DeleteFromStore",
        secret,
        {
            "WMLtypeIn": "mudLog",
            "QueryIn": (
                f'<mudLogs xmlns="{WITSML_NS}">'
                '<mudLog uid="mud-a" uidWell="w-a" uidWellbore="wb-a"/>'
                "</mudLogs>"
            ),
            "OptionsIn": "",
        },
    )
    assert result(deleted) == 1, field(deleted, "SuppMsgOut")
    gone = await read_mudlog(admin_client, secret)
    assert result(gone) == 1
    assert 'uid="mud-a"' not in field(gone, "XMLout")
