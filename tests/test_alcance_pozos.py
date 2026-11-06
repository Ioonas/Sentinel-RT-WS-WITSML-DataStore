"""El alcance por pozo solo acepta pozos existentes en el inventario (UI-07)."""

from __future__ import annotations

from httpx import AsyncClient

from tests.test_wmls_soap import WELL, create_writer, soap


async def test_scope_rejects_wells_missing_from_inventory(
    admin_client: AsyncClient, csrf: str
) -> None:
    secret = await create_writer(admin_client, csrf)
    added = await soap(
        admin_client,
        "WMLS_AddToStore",
        secret,
        {"WMLtypeIn": "well", "XMLin": WELL, "OptionsIn": ""},
    )
    assert added.status_code == 200, added.text

    rejected = await admin_client.post(
        "/admin-api/v1/service-accounts",
        headers={"x-csrf-token": csrf},
        json={
            "name": "lector.pozos",
            "role": "reader",
            "grants": [{"object_type": "*", "action": "read"}],
            "well_scope": ["w-1", "pozo-inexistente"],
        },
    )
    assert rejected.status_code == 422, rejected.text
    assert rejected.json()["error"] == "validation_error"
    assert "pozo-inexistente" in rejected.json()["message"]
    assert "w-1" not in rejected.json()["message"]

    accepted = await admin_client.post(
        "/admin-api/v1/service-accounts",
        headers={"x-csrf-token": csrf},
        json={
            "name": "lector.pozos",
            "role": "reader",
            "grants": [{"object_type": "*", "action": "read"}],
            "well_scope": ["w-1"],
        },
    )
    assert accepted.status_code == 201, accepted.text


async def test_scoped_writer_creates_well_and_owns_it(
    admin_client: AsyncClient, csrf: str
) -> None:
    """Una cuenta sin pozos puede crear un pozo; el pozo queda en su alcance."""
    created = await admin_client.post(
        "/admin-api/v1/service-accounts",
        headers={"x-csrf-token": csrf},
        json={
            "name": "escritor.sin.pozos",
            "role": "writer",
            "grants": [
                {"object_type": "*", "action": "read"},
                {"object_type": "*", "action": "write"},
            ],
            "well_scope": [],
        },
    )
    assert created.status_code == 201, created.text
    secret = created.json()["credential"]["secret"]

    added = await soap(
        admin_client,
        "WMLS_AddToStore",
        secret,
        {"WMLtypeIn": "well", "XMLin": WELL, "OptionsIn": ""},
    )
    assert added.status_code == 200, added.text

    listed = await admin_client.get(
        "/admin-api/v1/service-accounts", headers={"x-csrf-token": csrf}
    )
    account = next(item for item in listed.json() if item["name"] == "escritor.sin.pozos")
    assert account["well_scope"] == ["w-1"]
