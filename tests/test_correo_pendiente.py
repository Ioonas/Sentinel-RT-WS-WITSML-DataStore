"""Diagnóstico y reintento de correo: el listado nunca expone el cuerpo ni tokens."""

from __future__ import annotations

from httpx import AsyncClient


async def _invite(client: AsyncClient, csrf: str, email: str) -> None:
    created = await client.post(
        "/admin-api/v1/invitations",
        headers={"x-csrf-token": csrf},
        json={"email": email, "role": "auditor"},
    )
    assert created.status_code == 201, created.text


async def test_listado_no_expone_cuerpo_ni_token(admin_client: AsyncClient, csrf: str) -> None:
    await _invite(admin_client, csrf, "correo.lista@example.com")

    listed = await admin_client.get("/admin-api/v1/mail-outbox", params={"status": "pending"})
    assert listed.status_code == 200, listed.text
    items = listed.json()["items"]
    assert any(item["recipient"] == "correo.lista@example.com" for item in items)
    for item in items:
        assert "body" not in item
        assert set(item) == {
            "id", "kind", "recipient", "subject", "status", "attempts",
            "next_attempt_at", "last_error", "created_at",
        }
    # El enlace de invitación contiene el token: nunca debe aparecer en el listado.
    assert "accept-invitation" not in listed.text


async def test_filtra_por_tipo(admin_client: AsyncClient, csrf: str) -> None:
    await _invite(admin_client, csrf, "correo.filtro@example.com")

    listed = await admin_client.get("/admin-api/v1/mail-outbox", params={"kind": "invitation"})
    assert listed.status_code == 200, listed.text
    assert listed.json()["items"]
    assert all(item["kind"] == "invitation" for item in listed.json()["items"])


async def test_reintento_de_correo_pendiente(admin_client: AsyncClient, csrf: str) -> None:
    await _invite(admin_client, csrf, "correo.reintento@example.com")
    listed = await admin_client.get("/admin-api/v1/mail-outbox", params={"status": "pending"})
    job_id = next(
        item["id"] for item in listed.json()["items"]
        if item["recipient"] == "correo.reintento@example.com"
    )

    retried = await admin_client.post(
        f"/admin-api/v1/mail-outbox/{job_id}/retry", headers={"x-csrf-token": csrf}
    )
    assert retried.status_code == 200, retried.text
    assert retried.json()["status"] == "pending"
    assert "body" not in retried.json()


async def test_reintento_de_correo_inexistente(admin_client: AsyncClient, csrf: str) -> None:
    retried = await admin_client.post(
        "/admin-api/v1/mail-outbox/no-existe/retry", headers={"x-csrf-token": csrf}
    )
    assert retried.status_code == 404, retried.text
