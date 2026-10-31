"""Pruebas de la API administrativa y del primer arranque."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from tests.conftest import ADMIN_PASSWORD, CONTACT

pytestmark = pytest.mark.integration


async def test_setup_is_single_use_and_creates_session(admin_client: AsyncClient) -> None:
    status = await admin_client.get("/admin-api/v1/setup/status")
    assert status.json() == {"setup_completed": True}

    duplicate = await admin_client.post(
        "/admin-api/v1/setup",
        json={
            "contact_email": "other@example.com",
            "contact_phone": "+1 555 0199",
            "admin_email": "other@example.com",
            "admin_name": "Otro",
            "admin_password": ADMIN_PASSWORD,
        },
    )
    assert duplicate.status_code == 409

    profile = await admin_client.get("/admin-api/v1/profile")
    assert profile.status_code == 200
    assert profile.json()["user"]["email"] == "admin@example.com"


async def test_login_is_generic_for_invalid_credentials(client: AsyncClient) -> None:
    await client.post(
        "/admin-api/v1/setup",
        json={
            "contact_email": CONTACT["contact_email"],
            "contact_phone": CONTACT["contact_phone"],
            "admin_email": "admin@example.com",
            "admin_name": "Administrador",
            "admin_password": ADMIN_PASSWORD,
        },
    )
    response = await client.post(
        "/admin-api/v1/auth/sessions",
        json={"email": "admin@example.com", "password": "wrong-password"},
    )
    assert response.status_code == 401
    assert response.json()["message"] == "Credenciales inválidas."


async def test_contact_update_requires_csrf_and_superadmin(
    admin_client: AsyncClient, csrf: str
) -> None:
    missing = await admin_client.put(
        "/admin-api/v1/server-config/contact",
        json={"contact_email": "new@example.com", "contact_phone": "+1 555 0111"},
    )
    assert missing.status_code == 403

    response = await admin_client.put(
        "/admin-api/v1/server-config/contact",
        headers={"x-csrf-token": csrf},
        json={"contact_email": "new@example.com", "contact_phone": "+1 555 0111"},
    )
    assert response.status_code == 200
    assert response.json()["contact_email"] == "new@example.com"

    config = await admin_client.get("/admin-api/v1/server-config")
    assert config.json()["contact_phone"] == "+1 555 0111"


async def test_service_account_secret_is_returned_once(
    admin_client: AsyncClient, csrf: str
) -> None:
    response = await admin_client.post(
        "/admin-api/v1/service-accounts",
        headers={"x-csrf-token": csrf},
        json={
            "name": "acme.reader",
            "role": "reader",
            "grants": [{"object_type": "*", "action": "read"}],
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["credential"]["secret"].startswith("srtws_")

    listing = await admin_client.get("/admin-api/v1/service-accounts")
    assert listing.status_code == 200
    assert listing.json()[0]["name"] == "acme.reader"
    assert "secret" not in listing.json()[0]


async def test_roles_permissions_and_audit(admin_client: AsyncClient) -> None:
    roles = await admin_client.get("/admin-api/v1/roles")
    assert roles.status_code == 200
    names = {item["name"] for item in roles.json()}
    assert "superadministrador" in names

    permissions = await admin_client.get("/admin-api/v1/permissions")
    assert permissions.status_code == 200
    assert any(item["name"] == "admin.audit.read" for item in permissions.json())

    audit = await admin_client.get("/admin-api/v1/audit-events")
    assert audit.status_code == 200
    actions = {item["action"] for item in audit.json()["items"]}
    assert "setup.completed" in actions


async def test_health_endpoints(admin_client: AsyncClient) -> None:
    public = await admin_client.get("/health")
    assert public.status_code == 200
    assert public.json()["status"] == "available"

    dependencies = await admin_client.get("/admin-api/v1/health/dependencies")
    assert dependencies.status_code == 200
    body = dependencies.json()
    assert body["dependencies"]["postgresql"]["status"] == "ok"
    assert "mail" in body["dependencies"]


async def test_logout_revokes_session(admin_client: AsyncClient, csrf: str) -> None:
    response = await admin_client.delete(
        "/admin-api/v1/auth/sessions", headers={"x-csrf-token": csrf}
    )
    assert response.status_code == 204

    profile = await admin_client.get("/admin-api/v1/profile")
    assert profile.status_code == 401
