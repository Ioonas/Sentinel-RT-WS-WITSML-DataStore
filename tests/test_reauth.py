"""Reautenticación reciente para operaciones sensibles."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from sentinel.admin_api.app import create_app
from sentinel.bootstrap.container import Container
from sentinel.persistence.tables import Base
from sentinel.shared.clock import FixedClock
from tests.conftest import ADMIN_PASSWORD, CONTACT
from tests.conftest import test_settings as build_settings

SETUP_BODY = {
    "contact_email": CONTACT["contact_email"],
    "contact_phone": CONTACT["contact_phone"],
    "admin_email": "admin@example.com",
    "admin_name": "Administrador",
    "admin_password": ADMIN_PASSWORD,
}


@pytest_asyncio.fixture
async def clock_client() -> AsyncIterator[tuple[AsyncClient, FixedClock]]:
    clock = FixedClock(datetime(2026, 11, 5, 12, 0, tzinfo=UTC))
    instance = Container(build_settings(), clock=clock, smtp_check=lambda: None)
    async with instance.engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    transport = ASGITransport(app=create_app(instance))
    try:
        async with AsyncClient(transport=transport, base_url="http://testserver") as http:
            assert (await http.post("/admin-api/v1/setup", json=SETUP_BODY)).status_code == 201
            yield http, clock
    finally:
        await instance.dispose()


async def test_sensitive_operation_requires_recent_reauthentication(clock_client) -> None:
    client, clock = clock_client
    csrf = client.cookies.get("sentinel_csrf") or ""
    user_id = (await client.get("/admin-api/v1/admin-users")).json()[0]["id"]
    body = {"display_name": "Administrador revisado"}

    # Recién autenticado: la operación sensible se permite.
    assert (
        await client.patch(
            f"/admin-api/v1/admin-users/{user_id}", headers={"x-csrf-token": csrf}, json=body
        )
    ).status_code == 200

    # Pasados 15 minutos la ventana vence y el servidor exige reautenticación.
    clock.advance(15 * 60 + 1)
    expired = await client.patch(
        f"/admin-api/v1/admin-users/{user_id}", headers={"x-csrf-token": csrf}, json=body
    )
    assert expired.status_code == 403
    assert expired.json()["error"] == "reauth_required"

    # Contraseña incorrecta no renueva la ventana.
    wrong = await client.post(
        "/admin-api/v1/auth/reauthentication",
        headers={"x-csrf-token": csrf},
        json={"password": "x-incorrecta"},
    )
    assert wrong.status_code == 401
    still_expired = await client.patch(
        f"/admin-api/v1/admin-users/{user_id}", headers={"x-csrf-token": csrf}, json=body
    )
    assert still_expired.json()["error"] == "reauth_required"

    # Contraseña correcta renueva la ventana y la operación vuelve a permitirse.
    ok = await client.post(
        "/admin-api/v1/auth/reauthentication",
        headers={"x-csrf-token": csrf},
        json={"password": ADMIN_PASSWORD},
    )
    assert ok.status_code == 204
    assert (
        await client.patch(
            f"/admin-api/v1/admin-users/{user_id}", headers={"x-csrf-token": csrf}, json=body
        )
    ).status_code == 200
