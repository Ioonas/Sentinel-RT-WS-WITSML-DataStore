"""Configuración de correo editable y reinicio controlado de servicios."""

from __future__ import annotations

from httpx import AsyncClient

MAIL = {
    "mail_from": "avisos@example.com",
    "mail_max_attempts": 7,
    "mail_backoff_base_seconds": 60,
}


async def test_mail_update_requires_csrf(admin_client: AsyncClient) -> None:
    response = await admin_client.put("/admin-api/v1/server-config/mail", json=MAIL)
    assert response.status_code == 403


async def test_mail_update_applies_and_is_visible(admin_client: AsyncClient, csrf: str) -> None:
    response = await admin_client.put(
        "/admin-api/v1/server-config/mail", headers={"x-csrf-token": csrf}, json=MAIL
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["mail_from"] == "avisos@example.com"
    assert body["mail_max_attempts"] == 7
    assert body["mail_backoff_base_seconds"] == 60


async def test_mail_rejects_invalid_values(admin_client: AsyncClient, csrf: str) -> None:
    for payload in (
        {**MAIL, "mail_max_attempts": 0},
        {**MAIL, "mail_max_attempts": 51},
        {**MAIL, "mail_backoff_base_seconds": 0},
    ):
        response = await admin_client.put(
            "/admin-api/v1/server-config/mail", headers={"x-csrf-token": csrf}, json=payload
        )
        assert response.status_code == 422, (payload, response.text)

    invalid_sender = await admin_client.put(
        "/admin-api/v1/server-config/mail",
        headers={"x-csrf-token": csrf},
        json={**MAIL, "mail_from": "no-es-correo"},
    )
    assert invalid_sender.status_code == 422, invalid_sender.text


async def test_restart_requires_csrf_and_bumps_generation(
    admin_client: AsyncClient, csrf: str
) -> None:
    before = (await admin_client.get("/admin-api/v1/server-config")).json()["restart_generation"]

    rejected = await admin_client.post("/admin-api/v1/server-config/restart")
    assert rejected.status_code == 403

    accepted = await admin_client.post(
        "/admin-api/v1/server-config/restart", headers={"x-csrf-token": csrf}
    )
    assert accepted.status_code == 202, accepted.text
    assert accepted.json()["restart_generation"] == before + 1
