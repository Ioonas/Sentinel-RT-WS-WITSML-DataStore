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


def _by_name(rows: list[dict]) -> dict[str, dict]:
    return {row["name"]: row for row in rows}


async def test_restart_requires_csrf(admin_client: AsyncClient) -> None:
    rejected = await admin_client.post(
        "/admin-api/v1/server-config/restart", json={"service": "api"}
    )
    assert rejected.status_code == 403


async def test_restart_is_per_service(admin_client: AsyncClient, csrf: str) -> None:
    before = _by_name((await admin_client.get("/admin-api/v1/server-config/services")).json())

    accepted = await admin_client.post(
        "/admin-api/v1/server-config/restart",
        headers={"x-csrf-token": csrf},
        json={"service": "api"},
    )
    assert accepted.status_code == 202, accepted.text
    assert [row["name"] for row in accepted.json()] == ["api"]
    assert accepted.json()[0]["requested_generation"] == before["api"]["requested_generation"] + 1

    after = _by_name((await admin_client.get("/admin-api/v1/server-config/services")).json())
    assert (
        after["mail-worker"]["requested_generation"]
        == before["mail-worker"]["requested_generation"]
    )


async def test_restart_all_bumps_every_service(admin_client: AsyncClient, csrf: str) -> None:
    before = _by_name((await admin_client.get("/admin-api/v1/server-config/services")).json())
    accepted = await admin_client.post(
        "/admin-api/v1/server-config/restart", headers={"x-csrf-token": csrf}, json={}
    )
    assert accepted.status_code == 202, accepted.text
    after = _by_name(accepted.json())
    for name in ("api", "mail-worker"):
        assert after[name]["requested_generation"] == before[name]["requested_generation"] + 1


async def test_restart_rejects_unknown_service(admin_client: AsyncClient, csrf: str) -> None:
    response = await admin_client.post(
        "/admin-api/v1/server-config/restart",
        headers={"x-csrf-token": csrf},
        json={"service": "base-de-datos"},
    )
    assert response.status_code == 422


async def test_services_list_reports_both_processes(admin_client: AsyncClient) -> None:
    rows = _by_name((await admin_client.get("/admin-api/v1/server-config/services")).json())
    assert set(rows) == {"api", "mail-worker"}
    assert rows["api"]["stale"] is True  # ningún proceso de prueba envía heartbeat
