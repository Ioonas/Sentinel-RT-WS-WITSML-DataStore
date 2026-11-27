"""Objetos WITSML por cuenta de servicio: cada cuenta tiene su propio espacio de uids.

- Dos cuentas pueden crear objetos con el mismo nombre (uid) sin chocar.
- Una cuenta solo lee, cambia y borra lo que es suyo; lo ajeno no existe para ella.
- El panel asigna objetos a una cuenta, con sus descendientes, y rechaza conflictos.
- El alta desde el panel exige una cuenta dueña.
"""

from __future__ import annotations

import base64

from httpx import AsyncClient

from sentinel.witsml_application.domain.codes import WmlsCode
from sentinel.xml_schema.namespaces import WITSML_NS
from tests.owners import create_owner_account
from tests.test_wmls_soap import WELL, envelope, field, object_count, result

WELLBORE = (
    f'<wellbores xmlns="{WITSML_NS}" version="1.4.1.1">'
    '<wellbore uid="wb-1" uidWell="w-1"><nameWell>Well One</nameWell>'
    "<name>Sondeo</name></wellbore></wellbores>"
)


async def _account(client: AsyncClient, csrf: str, name: str) -> tuple[str, str]:
    """Devuelve (id, secreto) de una cuenta de servicio con permisos completos."""
    created = await client.post(
        "/admin-api/v1/service-accounts",
        headers={"x-csrf-token": csrf},
        json={
            "name": name,
            "role": "writer",
            "can_cascade_delete": True,
            "grants": [
                {"object_type": "*", "action": "read"},
                {"object_type": "*", "action": "write"},
                {"object_type": "*", "action": "delete"},
            ],
        },
    )
    assert created.status_code == 201, created.text
    return created.json()["account"]["id"], created.json()["credential"]["secret"]


async def _call(client: AsyncClient, name: str, secret: str, operation: str, params: dict):
    credentials = base64.b64encode(f"{name}:{secret}".encode()).decode()
    return await client.post(
        "/witsml",
        content=envelope(operation, params),
        headers={
            "content-type": "text/xml; charset=utf-8",
            "authorization": f"Basic {credentials}",
            "soapaction": f'"http://www.witsml.org/api/120/Store.{operation}"',
        },
    )


async def _add_well_and_wellbore(client: AsyncClient, name: str, secret: str) -> None:
    added = await _call(
        client, name, secret, "WMLS_AddToStore",
        {"WMLtypeIn": "well", "XMLin": WELL, "OptionsIn": ""},
    )
    assert result(added) == int(WmlsCode.SUCCESS), added.text
    added = await _call(
        client, name, secret, "WMLS_AddToStore",
        {"WMLtypeIn": "wellbore", "XMLin": WELLBORE, "OptionsIn": ""},
    )
    assert result(added) == int(WmlsCode.SUCCESS), added.text


async def _count(client: AsyncClient, name: str, secret: str, wmls_type: str) -> int:
    listed = await _call(
        client, name, secret, "WMLS_GetFromStore",
        {"WMLtypeIn": wmls_type, "QueryIn": f"<{wmls_type}s><{wmls_type}/></{wmls_type}s>",
         "OptionsIn": "returnElements=all", "CapabilityIn": ""},
    )
    assert result(listed) == int(WmlsCode.SUCCESS), listed.text
    return object_count(field(listed, "XMLout"), wmls_type)


async def test_dos_cuentas_pueden_usar_el_mismo_uid(admin_client: AsyncClient, csrf: str) -> None:
    _, secret_a = await _account(admin_client, csrf, "cuenta.a")
    _, secret_b = await _account(admin_client, csrf, "cuenta.b")

    await _add_well_and_wellbore(admin_client, "cuenta.a", secret_a)
    await _add_well_and_wellbore(admin_client, "cuenta.b", secret_b)

    assert await _count(admin_client, "cuenta.a", secret_a, "well") == 1
    assert await _count(admin_client, "cuenta.b", secret_b, "well") == 1


async def test_cuenta_no_ve_ni_cambia_objetos_ajenos(admin_client: AsyncClient, csrf: str) -> None:
    _, secret_a = await _account(admin_client, csrf, "dueno.lectura")
    _, secret_b = await _account(admin_client, csrf, "ajena.lectura")
    await _add_well_and_wellbore(admin_client, "dueno.lectura", secret_a)

    assert await _count(admin_client, "ajena.lectura", secret_b, "wellbore") == 0

    update = await _call(
        admin_client, "ajena.lectura", secret_b, "WMLS_UpdateInStore",
        {"WMLtypeIn": "wellbore", "XMLin": WELLBORE.replace("Sondeo", "Cambio"), "OptionsIn": ""},
    )
    assert result(update) == int(WmlsCode.OBJECT_NOT_EXIST)

    deleted = await _call(
        admin_client, "ajena.lectura", secret_b, "WMLS_DeleteFromStore",
        {"WMLtypeIn": "wellbore",
         "QueryIn": "<wellbores><wellbore uid='wb-1' uidWell='w-1'/></wellbores>",
         "OptionsIn": ""},
    )
    assert result(deleted) == int(WmlsCode.OBJECT_NOT_EXIST)

    # El objeto del dueno sigue intacto.
    assert await _count(admin_client, "dueno.lectura", secret_a, "wellbore") == 1


async def test_cuenta_no_crea_hijos_bajo_pozo_ajeno(admin_client: AsyncClient, csrf: str) -> None:
    _, secret_a = await _account(admin_client, csrf, "dueno.padre")
    _, secret_b = await _account(admin_client, csrf, "ajena.padre")
    await _add_well_and_wellbore(admin_client, "dueno.padre", secret_a)

    added = await _call(
        admin_client, "ajena.padre", secret_b, "WMLS_AddToStore",
        {"WMLtypeIn": "wellbore", "XMLin": WELLBORE.replace("wb-1", "wb-ajeno"), "OptionsIn": ""},
    )
    assert result(added) != int(WmlsCode.SUCCESS)
    assert await _count(admin_client, "dueno.padre", secret_a, "wellbore") == 1


async def test_panel_asigna_objeto_con_descendientes(admin_client: AsyncClient, csrf: str) -> None:
    id_a, secret_a = await _account(admin_client, csrf, "origen.asignacion")
    id_b, secret_b = await _account(admin_client, csrf, "destino.asignacion")
    await _add_well_and_wellbore(admin_client, "origen.asignacion", secret_a)

    moved = await admin_client.post(
        "/admin-api/v1/objects/well/owner",
        headers={"x-csrf-token": csrf},
        json={"uid": "w-1", "owner_id": id_b},
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["owner_id"] == id_b

    assert await _count(admin_client, "destino.asignacion", secret_b, "well") == 1
    assert await _count(admin_client, "destino.asignacion", secret_b, "wellbore") == 1
    assert await _count(admin_client, "origen.asignacion", secret_a, "well") == 0
    assert await _count(admin_client, "origen.asignacion", secret_a, "wellbore") == 0
    assert id_a != id_b


async def test_asignacion_con_uid_existente_en_destino_se_rechaza(
    admin_client: AsyncClient, csrf: str
) -> None:
    id_a, secret_a = await _account(admin_client, csrf, "conflicto.origen")
    id_b, secret_b = await _account(admin_client, csrf, "conflicto.destino")
    await _add_well_and_wellbore(admin_client, "conflicto.origen", secret_a)
    await _add_well_and_wellbore(admin_client, "conflicto.destino", secret_b)

    moved = await admin_client.post(
        "/admin-api/v1/objects/well/owner",
        headers={"x-csrf-token": csrf},
        json={"uid": "w-1", "owner_id": id_b},
    )
    assert moved.status_code == 409, moved.text
    assert await _count(admin_client, "conflicto.origen", secret_a, "well") == 1


async def test_alta_desde_panel_queda_en_la_cuenta_indicada(
    admin_client: AsyncClient, csrf: str
) -> None:
    id_a, secret_a = await _account(admin_client, csrf, "dueno.alta")
    _, secret_b = await _account(admin_client, csrf, "ajena.alta")

    created = await admin_client.post(
        "/admin-api/v1/objects/well",
        headers={"x-csrf-token": csrf},
        json={"uid": "panel-w", "name": "Pozo del panel", "owner_id": id_a},
    )
    assert created.status_code == 201, created.text
    assert created.json()["owner_id"] == id_a

    assert await _count(admin_client, "dueno.alta", secret_a, "well") == 1
    assert await _count(admin_client, "ajena.alta", secret_b, "well") == 0


async def test_alta_desde_panel_exige_cuenta_existente(
    admin_client: AsyncClient, csrf: str
) -> None:
    missing = await admin_client.post(
        "/admin-api/v1/objects/well",
        headers={"x-csrf-token": csrf},
        json={"uid": "sin-cuenta", "name": "Sin cuenta", "owner_id": "no-existe"},
    )
    assert missing.status_code == 404, missing.text
    assert await create_owner_account(admin_client, csrf, "dueno.requerido")
