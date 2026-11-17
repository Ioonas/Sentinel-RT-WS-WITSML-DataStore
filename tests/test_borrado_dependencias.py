"""El borrado administrativo explica qué dependientes bloquean la eliminación."""

from __future__ import annotations

from httpx import AsyncClient


async def test_borrado_con_dependientes_lista_todos_los_bloqueos(
    admin_client: AsyncClient, csrf: str
) -> None:
    headers = {"x-csrf-token": csrf}
    well = await admin_client.post(
        "/admin-api/v1/objects/well", headers=headers, json={"uid": "dep-well", "name": "Pozo"}
    )
    assert well.status_code == 201, well.text
    wellbore = await admin_client.post(
        "/admin-api/v1/objects/wellbore",
        headers=headers,
        json={"uid": "dep-wb", "uid_well": "dep-well", "name": "Sondeo"},
    )
    assert wellbore.status_code == 201, wellbore.text

    blocked = await admin_client.post(
        "/admin-api/v1/objects/well/dep-well/delete",
        headers=headers,
        json={"reason": "prueba de dependientes", "confirmation": "dep-well"},
    )
    assert blocked.status_code == 409, blocked.text
    assert "wellbore:dep-wb" in blocked.json()["message"]
    assert "eliminarse primero" in blocked.json()["message"]

    # El listado de dependencias muestra exactamente lo mismo que bloquea el borrado.
    dependencies = await admin_client.get(
        "/admin-api/v1/objects/well/dep-well/dependencies"
    )
    assert dependencies.status_code == 200, dependencies.text
    assert dependencies.json() == ["wellbore:dep-wb"]


async def test_borrado_sin_dependientes_funciona(
    admin_client: AsyncClient, csrf: str
) -> None:
    headers = {"x-csrf-token": csrf}
    well = await admin_client.post(
        "/admin-api/v1/objects/well", headers=headers, json={"uid": "solo-well", "name": "Pozo"}
    )
    assert well.status_code == 201, well.text

    deleted = await admin_client.post(
        "/admin-api/v1/objects/well/solo-well/delete",
        headers=headers,
        json={"reason": "prueba sin dependientes", "confirmation": "solo-well"},
    )
    assert deleted.status_code == 200, deleted.text
