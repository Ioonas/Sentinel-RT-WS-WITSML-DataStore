"""Eliminar cuentas humanas: reglas de seguridad del borrado."""

from __future__ import annotations

from httpx import AsyncClient


async def test_cannot_delete_own_account(admin_client: AsyncClient, csrf: str) -> None:
    me = (await admin_client.get("/admin-api/v1/profile")).json()["user"]
    response = await admin_client.delete(
        f"/admin-api/v1/admin-users/{me['id']}", headers={"x-csrf-token": csrf}
    )
    assert response.status_code == 422, response.text
    assert "propia cuenta" in response.json()["message"]


async def test_deleting_unknown_user_returns_not_found(
    admin_client: AsyncClient, csrf: str
) -> None:
    response = await admin_client.delete(
        "/admin-api/v1/admin-users/no-existe", headers={"x-csrf-token": csrf}
    )
    assert response.status_code == 404, response.text
