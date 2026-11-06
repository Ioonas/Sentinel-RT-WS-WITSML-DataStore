"""Acceso web vinculado: una persona ve solo los pozos de una cuenta de servicio."""

from __future__ import annotations

from httpx import AsyncClient


async def _create_account(
    client: AsyncClient, csrf: str, name: str, well_scope: list[str] | None
) -> str:
    body: dict = {
        "name": name,
        "role": "reader",
        "grants": [{"object_type": "*", "action": "read"}],
    }
    if well_scope is not None:
        body["well_scope"] = well_scope
    response = await client.post(
        "/admin-api/v1/service-accounts",
        headers={"x-csrf-token": csrf},
        json=body,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def test_empty_scope_is_not_all_wells(admin_client: AsyncClient, csrf: str) -> None:
    """Una lista vacía de pozos no debe guardarse como acceso a todos los pozos."""
    account_id = await _create_account(admin_client, csrf, "lector.vacio", [])
    listed = await admin_client.get("/admin-api/v1/service-accounts")
    account = next(item for item in listed.json() if item["id"] == account_id)
    assert account["well_scope"] == []


async def test_web_access_requires_a_scoped_account(admin_client: AsyncClient, csrf: str) -> None:
    open_account = await _create_account(admin_client, csrf, "lector.todos", None)
    rejected = await admin_client.post(
        f"/admin-api/v1/service-accounts/{open_account}/web-access",
        headers={"x-csrf-token": csrf},
        json={"email": "ana@example.mx"},
    )
    assert rejected.status_code == 409, rejected.text

    scoped = await _create_account(admin_client, csrf, "lector.propio", [])
    invited = await admin_client.post(
        f"/admin-api/v1/service-accounts/{scoped}/web-access",
        headers={"x-csrf-token": csrf},
        json={"email": "ana@example.mx"},
    )
    assert invited.status_code == 201, invited.text

    listed = await admin_client.get(
        f"/admin-api/v1/service-accounts/{scoped}/web-access",
    )
    assert listed.status_code == 200, listed.text
    assert listed.json()["users"] == []
    assert [item["email"] for item in listed.json()["invitations"]] == ["ana@example.mx"]

    duplicated = await admin_client.post(
        f"/admin-api/v1/service-accounts/{scoped}/web-access",
        headers={"x-csrf-token": csrf},
        json={"email": "ana@example.mx"},
    )
    assert duplicated.status_code == 409, duplicated.text


async def test_linked_role_cannot_be_granted_by_plain_invitation(
    admin_client: AsyncClient, csrf: str
) -> None:
    response = await admin_client.post(
        "/admin-api/v1/invitations",
        headers={"x-csrf-token": csrf},
        json={"email": "otra@example.mx", "role": "lector_vinculado"},
    )
    assert response.status_code == 422, response.text
