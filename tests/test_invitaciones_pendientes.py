"""Listado de invitaciones pendientes (UI-06)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

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


async def test_pending_invitations_are_listed_without_secrets_and_expire(clock_client) -> None:
    client, clock = clock_client
    csrf = client.cookies.get("sentinel_csrf") or ""
    created = await client.post(
        "/admin-api/v1/invitations",
        headers={"x-csrf-token": csrf},
        json={"email": "invitado@example.com", "role": "auditor"},
    )
    assert created.status_code == 201, created.text

    listed = await client.get("/admin-api/v1/invitations")
    assert listed.status_code == 200
    items = listed.json()
    assert [item["email"] for item in items] == ["invitado@example.com"]
    assert set(items[0]) == {"id", "email", "role", "created_by", "created_at", "expires_at"}
    assert "token" not in listed.text and "token_hash" not in listed.text

    # Una invitación vencida sigue listada para que el administrador pueda reenviarla.
    # La sesión caduca antes que la invitación (12 h frente a 72 h): se vuelve a iniciar sesión.
    clock.advance(timedelta(hours=73).total_seconds())
    login = await client.post(
        "/admin-api/v1/auth/sessions",
        json={"email": "admin@example.com", "password": ADMIN_PASSWORD},
    )
    assert login.status_code in (200, 201), login.text
    expired = (await client.get("/admin-api/v1/invitations")).json()
    assert [item["email"] for item in expired] == ["invitado@example.com"]
    expires_at = datetime.fromisoformat(expired[0]["expires_at"].replace("Z", "+00:00"))
    assert expires_at <= datetime.fromtimestamp(clock.now().timestamp(), UTC)
