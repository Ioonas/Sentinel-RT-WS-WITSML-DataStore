"""Primer arranque (nombre, descripción, SMTP) y borrado en cascada por cuenta."""

from __future__ import annotations

import base64
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from sentinel.admin_api.app import create_app
from sentinel.bootstrap.container import Container
from sentinel.persistence.tables import Base
from sentinel.shared.clock import FixedClock
from sentinel.shared.errors import ValidationError
from tests.conftest import ADMIN_PASSWORD, CONTACT
from tests.conftest import test_settings as build_settings
from tests.test_wmls_soap import WELL, create_writer, envelope, field, result, soap

SETUP_BODY = {
    "contact_email": CONTACT["contact_email"],
    "contact_phone": CONTACT["contact_phone"],
    "admin_email": "admin@example.com",
    "admin_name": "Administrador",
    "admin_password": ADMIN_PASSWORD,
}
WELL_QUERY = '<wells xmlns="http://www.witsml.org/schemas/1series"><well uid="w-1"/></wells>'


def _failing_smtp() -> None:
    raise ValidationError("Falta configurar SMTP: SENTINEL_SMTP_HOST.")


async def _build(clock: FixedClock, smtp_check) -> Container:
    instance = Container(build_settings(), clock=clock, smtp_check=smtp_check)
    async with instance.engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    return instance


@pytest_asyncio.fixture
async def clock() -> FixedClock:
    return FixedClock(datetime(2026, 11, 5, 11, 0, tzinfo=UTC))


@pytest_asyncio.fixture
async def client(clock: FixedClock) -> AsyncIterator[AsyncClient]:
    instance = await _build(clock, lambda: None)
    transport = ASGITransport(app=create_app(instance))
    try:
        async with AsyncClient(transport=transport, base_url="http://testserver") as http:
            response = await http.post("/admin-api/v1/setup", json=SETUP_BODY)
            assert response.status_code == 201
            yield http
    finally:
        await instance.dispose()


async def test_setup_stores_chosen_name_and_description(clock: FixedClock) -> None:
    instance = await _build(clock, lambda: None)
    transport = ASGITransport(app=create_app(instance))
    try:
        async with AsyncClient(transport=transport, base_url="http://testserver") as http:
            body = {
                **SETUP_BODY,
                "server_name": "Servidor de certificación",
                "server_description": "Entorno de pruebas WITSML 1.4.1.1",
            }
            assert (await http.post("/admin-api/v1/setup", json=body)).status_code == 201
            config = (await http.get("/admin-api/v1/server-config")).json()
            assert config["contact_name"] == "Servidor de certificación"
            assert config["description"] == "Entorno de pruebas WITSML 1.4.1.1"
    finally:
        await instance.dispose()


async def test_setup_requires_smtp_and_stays_incomplete(clock: FixedClock) -> None:
    instance = await _build(clock, _failing_smtp)
    transport = ASGITransport(app=create_app(instance))
    try:
        async with AsyncClient(transport=transport, base_url="http://testserver") as http:
            response = await http.post("/admin-api/v1/setup", json=SETUP_BODY)
            assert response.status_code >= 400
            assert "SMTP" in response.json()["message"]
            status = await http.get("/admin-api/v1/setup/status")
            assert status.json()["setup_completed"] is False
    finally:
        await instance.dispose()


async def test_superadmin_changes_service_info_after_setup(client: AsyncClient) -> None:
    csrf = client.cookies.get("sentinel_csrf") or ""
    response = await client.put(
        "/admin-api/v1/server-config/service-info",
        headers={"x-csrf-token": csrf},
        json={"name": "Servidor de pruebas", "description": "Entorno de certificación"},
    )
    assert response.status_code == 200
    assert response.json()["contact_name"] == "Servidor de pruebas"


async def test_cascade_flag_is_immutable_after_creation(client: AsyncClient) -> None:
    csrf = client.cookies.get("sentinel_csrf") or ""
    await create_writer(client, csrf)
    accounts = (await client.get("/admin-api/v1/service-accounts")).json()
    response = await client.patch(
        f"/admin-api/v1/service-accounts/{accounts[0]['id']}",
        headers={"x-csrf-token": csrf},
        json={"can_cascade_delete": False},
    )
    assert response.status_code == 422


async def _call_as(client: AsyncClient, name: str, secret: str, operation: str, params: dict):
    token = base64.b64encode(f"{name}:{secret}".encode()).decode()
    return await client.post(
        "/witsml",
        content=envelope(operation, params),
        headers={"content-type": "text/xml; charset=utf-8", "authorization": f"Basic {token}"},
    )


async def test_cascade_requires_account_permission(client: AsyncClient) -> None:
    csrf = client.cookies.get("sentinel_csrf") or ""
    writer = await create_writer(client, csrf)
    created = await client.post(
        "/admin-api/v1/service-accounts",
        headers={"x-csrf-token": csrf},
        json={
            "name": "acme.sincascada",
            "role": "writer",
            "grants": [
                {"object_type": "*", "action": "write"},
                {"object_type": "*", "action": "delete"},
            ],
        },
    )
    assert created.status_code == 201
    limited_secret = created.json()["credential"]["secret"]
    added = await soap(
        client, "WMLS_AddToStore", writer, {"WMLtypeIn": "well", "XMLin": WELL, "OptionsIn": ""}
    )
    assert result(added) == 1

    denied = await _call_as(
        client,
        "acme.sincascada",
        limited_secret,
        "WMLS_DeleteFromStore",
        {"WMLtypeIn": "well", "QueryIn": WELL_QUERY, "OptionsIn": "cascadedDelete=true"},
    )
    assert result(denied) == -414, field(denied, "SuppMsgOut")

    allowed = await soap(
        client,
        "WMLS_DeleteFromStore",
        writer,
        {"WMLtypeIn": "well", "QueryIn": WELL_QUERY, "OptionsIn": "cascadedDelete=true"},
    )
    assert result(allowed) == 1


async def test_replaced_account_stops_after_grace(client: AsyncClient, clock: FixedClock) -> None:
    csrf = client.cookies.get("sentinel_csrf") or ""
    old_secret = await create_writer(client, csrf)
    old_id = (await client.get("/admin-api/v1/service-accounts")).json()[0]["id"]
    created = await client.post(
        "/admin-api/v1/service-accounts",
        headers={"x-csrf-token": csrf},
        json={
            "name": "acme.nuevo",
            "role": "writer",
            "grants": [{"object_type": "*", "action": "read"}],
            "replaces_account_id": old_id,
            "replacement_grace_days": 7,
        },
    )
    assert created.status_code == 201
    new_secret = created.json()["credential"]["secret"]
    assert created.json()["account"]["can_cascade_delete"] is False

    assert (await soap(client, "WMLS_GetVersion", old_secret)).status_code == 200
    clock.advance(7 * 24 * 3600 + 1)
    assert (await soap(client, "WMLS_GetVersion", old_secret)).status_code == 401
    new_response = await _call_as(client, "acme.nuevo", new_secret, "WMLS_GetVersion", {})
    assert new_response.status_code == 200


def test_check_smtp_names_missing_settings() -> None:
    from sentinel.mail_worker.probe import check_smtp

    settings = build_settings()
    try:
        check_smtp(settings)
    except ValidationError as exc:
        assert "SENTINEL_SMTP_USER" in str(exc.message if hasattr(exc, "message") else exc)
    else:
        raise AssertionError("check_smtp debe rechazar la configuración vacía")
