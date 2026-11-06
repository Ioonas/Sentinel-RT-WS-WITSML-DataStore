"""La sesión expone sus permisos efectivos para que la interfaz muestre solo lo permitido."""

from __future__ import annotations

from httpx import AsyncClient

from sentinel.identity_access.domain import ALL_ADMIN_PERMISSIONS


async def test_superadmin_profile_lists_every_permission(admin_client: AsyncClient) -> None:
    response = await admin_client.get("/admin-api/v1/profile")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["is_superadmin"] is True
    assert set(body["permissions"]) == set(ALL_ADMIN_PERMISSIONS)
