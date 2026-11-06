"""El alcance por pozo solo acepta pozos existentes en el inventario (UI-07)."""

from __future__ import annotations

from httpx import AsyncClient

from tests.test_wmls_soap import WELL, soap


async def test_scope_cannot_be_assigned_by_hand(admin_client: AsyncClient, csrf: str) -> None:
    """El alcance solo crece al crear pozos: una lista con pozos existentes se rechaza."""
    rejected = await admin_client.post(
        "/admin-api/v1/service-accounts",
        headers={"x-csrf-token": csrf},
        json={
            "name": "lector.manual",
            "role": "reader",
            "grants": [{"object_type": "*", "action": "read"}],
            "well_scope": ["w-1"],
        },
    )
    assert rejected.status_code == 422, rejected.text
    assert rejected.json()["error"] == "validation_error"
    assert "no se asigna" in rejected.json()["message"]

    accepted = await admin_client.post(
        "/admin-api/v1/service-accounts",
        headers={"x-csrf-token": csrf},
        json={
            "name": "lector.pozos",
            "role": "reader",
            "grants": [{"object_type": "*", "action": "read"}],
            "well_scope": [],
        },
    )
    assert accepted.status_code == 201, accepted.text


async def test_scoped_writer_creates_well_and_owns_it(admin_client: AsyncClient, csrf: str) -> None:
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
