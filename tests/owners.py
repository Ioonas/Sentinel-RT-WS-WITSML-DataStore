"""Ayudas para crear cuentas de servicio dueñas de objetos en las pruebas."""

from __future__ import annotations

from httpx import AsyncClient


async def create_owner_account(client: AsyncClient, csrf: str, name: str) -> str:
    """Crea una cuenta de servicio con permisos completos y devuelve su id."""
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
    return created.json()["account"]["id"]
