"""Restaurar una cuenta de servicio archivada: solo dentro de la gracia y con credencial nueva."""

from __future__ import annotations

from datetime import timedelta

from httpx import AsyncClient

from tests.conftest import ADMIN_PASSWORD
from tests.test_invitaciones_pendientes import clock_client  # noqa: F401  (fixture)


async def _create_and_archive(client: AsyncClient, csrf: str, name: str) -> tuple[str, str]:
    created = await client.post(
        "/admin-api/v1/service-accounts",
        headers={"x-csrf-token": csrf},
        json={
            "name": name,
            "role": "reader",
            "grants": [{"object_type": "*", "action": "read"}],
            "well_scope": [],
        },
    )
    assert created.status_code == 201, created.text
    account_id = created.json()["account"]["id"]
    old_secret = created.json()["credential"]["secret"]
    archived = await client.post(
        f"/admin-api/v1/service-accounts/{account_id}/archive",
        headers={"x-csrf-token": csrf},
    )
    assert archived.status_code == 200, archived.text
    return account_id, old_secret


async def test_restaurar_dentro_de_la_gracia_emite_credencial_nueva(clock_client) -> None:  # noqa: F811
    client, _clock = clock_client
    csrf = client.cookies.get("sentinel_csrf") or ""
    account_id, old_secret = await _create_and_archive(client, csrf, "lector.restaurar")

    restored = await client.post(
        f"/admin-api/v1/service-accounts/{account_id}/restore",
        headers={"x-csrf-token": csrf},
    )
    assert restored.status_code == 200, restored.text
    body = restored.json()
    new_secret = body["credential"]["secret"]
    assert new_secret, "la restauración debe devolver una credencial nueva"
    assert new_secret != old_secret
    assert body["account"]["enabled"] is True
    assert body["account"]["purge_at"] is None


async def test_restaurar_fuera_de_la_gracia_rechaza(clock_client) -> None:  # noqa: F811
    client, clock = clock_client
    csrf = client.cookies.get("sentinel_csrf") or ""
    account_id, _ = await _create_and_archive(client, csrf, "lector.vencido")

    # Periodo de gracia de 3 días. La sesión caduca antes (12 h), así que se vuelve a iniciar.
    clock.advance(timedelta(days=4).total_seconds())
    login = await client.post(
        "/admin-api/v1/auth/sessions",
        json={"email": "admin@example.com", "password": ADMIN_PASSWORD},
    )
    assert login.status_code in (200, 201), login.text
    csrf = client.cookies.get("sentinel_csrf") or ""
    restored = await client.post(
        f"/admin-api/v1/service-accounts/{account_id}/restore",
        headers={"x-csrf-token": csrf},
    )
    assert restored.status_code == 409, restored.text


async def test_restaurar_cuenta_activa_rechaza(clock_client) -> None:  # noqa: F811
    client, _clock = clock_client
    csrf = client.cookies.get("sentinel_csrf") or ""
    created = await client.post(
        "/admin-api/v1/service-accounts",
        headers={"x-csrf-token": csrf},
        json={
            "name": "lector.activo",
            "role": "reader",
            "grants": [{"object_type": "*", "action": "read"}],
            "well_scope": [],
        },
    )
    account_id = created.json()["account"]["id"]
    restored = await client.post(
        f"/admin-api/v1/service-accounts/{account_id}/restore",
        headers={"x-csrf-token": csrf},
    )
    assert restored.status_code == 409, restored.text
