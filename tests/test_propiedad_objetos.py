"""Alcance por propiedad: una cuenta acotada solo ve y cambia lo que creó.

Los objetos creados por un administrador quedan fuera del alcance de cualquier cuenta
acotada, incluso dentro de un pozo que la cuenta sí creó.
"""

from __future__ import annotations

import base64

from httpx import AsyncClient

from sentinel.witsml_application.domain.codes import WmlsCode
from sentinel.xml_schema.namespaces import WITSML_NS
from tests.test_wmls_soap import WELL, envelope, field, object_count, result

WELLBORE_ADMIN = (
    f'<wellbores xmlns="{WITSML_NS}" version="1.4.1.1">'
    '<wellbore uid="wb-admin" uidWell="w-1"><nameWell>Well One</nameWell>'
    "<name>Admin</name></wellbore></wellbores>"
)


async def _account(client: AsyncClient, csrf: str, name: str, scope: list[str] | None) -> str:
    payload: dict = {
        "name": name,
        "role": "writer",
        "can_cascade_delete": True,
        "grants": [
            {"object_type": "*", "action": "read"},
            {"object_type": "*", "action": "write"},
            {"object_type": "*", "action": "delete"},
        ],
    }
    if scope is not None:
        payload["well_scope"] = scope
    created = await client.post(
        "/admin-api/v1/service-accounts", headers={"x-csrf-token": csrf}, json=payload
    )
    assert created.status_code == 201, created.text
    return created.json()["credential"]["secret"]


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


async def _admin_wellbore(client: AsyncClient, csrf: str) -> None:
    created = await client.post(
        "/admin-api/v1/objects/wellbore",
        headers={"x-csrf-token": csrf},
        json={"uid": "wb-admin", "uid_well": "w-1", "name": "Admin"},
    )
    assert created.status_code == 201, created.text


async def test_admin_objects_are_outside_owner_scope(
    admin_client: AsyncClient, csrf: str
) -> None:
    secret = await _account(admin_client, csrf, "propietario.a", scope=[])
    added = await _call(
        admin_client, "propietario.a", secret, "WMLS_AddToStore",
        {"WMLtypeIn": "well", "XMLin": WELL, "OptionsIn": ""},
    )
    assert added.status_code == 200, added.text
    assert result(added) == int(WmlsCode.SUCCESS)

    await _admin_wellbore(admin_client, csrf)

    listed = await _call(
        admin_client, "propietario.a", secret, "WMLS_GetFromStore",
        {"WMLtypeIn": "wellbore", "QueryIn": "<wellbores><wellbore uidWell='w-1'/></wellbores>",
         "OptionsIn": "returnElements=all", "CapabilityIn": ""},
    )
    assert object_count(field(listed, "XMLout"), "wellbore") == 0


async def test_owner_cannot_change_or_delete_admin_objects(
    admin_client: AsyncClient, csrf: str
) -> None:
    secret = await _account(admin_client, csrf, "propietario.b", scope=[])
    await _call(
        admin_client, "propietario.b", secret, "WMLS_AddToStore",
        {"WMLtypeIn": "well", "XMLin": WELL, "OptionsIn": ""},
    )
    await _admin_wellbore(admin_client, csrf)

    update = await _call(
        admin_client, "propietario.b", secret, "WMLS_UpdateInStore",
        {"WMLtypeIn": "wellbore", "XMLin": WELLBORE_ADMIN.replace("Admin", "Cambio")},
    )
    assert result(update) == int(WmlsCode.INSUFFICIENT_RIGHTS)

    deleted = await _call(
        admin_client, "propietario.b", secret, "WMLS_DeleteFromStore",
        {"WMLtypeIn": "wellbore",
         "QueryIn": "<wellbores><wellbore uid='wb-admin' uidWell='w-1'/></wellbores>",
         "OptionsIn": ""},
    )
    assert result(deleted) == int(WmlsCode.INSUFFICIENT_RIGHTS)


async def test_cascade_is_refused_when_a_dependent_is_not_owned(
    admin_client: AsyncClient, csrf: str
) -> None:
    secret = await _account(admin_client, csrf, "propietario.c", scope=[])
    await _call(
        admin_client, "propietario.c", secret, "WMLS_AddToStore",
        {"WMLtypeIn": "well", "XMLin": WELL, "OptionsIn": ""},
    )
    await _admin_wellbore(admin_client, csrf)

    cascade = await _call(
        admin_client, "propietario.c", secret, "WMLS_DeleteFromStore",
        {"WMLtypeIn": "well", "QueryIn": "<wells><well uid='w-1'/></wells>",
         "OptionsIn": "cascadedDelete=true"},
    )
    assert result(cascade) == int(WmlsCode.INSUFFICIENT_RIGHTS)

    still_there = await admin_client.get(
        "/admin-api/v1/objects/wellbore/wb-admin", headers={"x-csrf-token": csrf},
        params={"uid_well": "w-1"},
    )
    assert still_there.status_code == 200, still_there.text
