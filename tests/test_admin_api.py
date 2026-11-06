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


async def test_service_account_accepts_admin_defined_credential(
    admin_client: AsyncClient, csrf: str
) -> None:
    response = await admin_client.post(
        "/admin-api/v1/service-accounts",
        headers={"x-csrf-token": csrf},
        json={
            "name": "wcat.certification",
            "role": "writer",
            "can_cascade_delete": True,
            "grants": [
                {"object_type": "*", "action": "read"},
                {"object_type": "*", "action": "write"},
                {"object_type": "*", "action": "delete"},
            ],
            "credential": "Operativa-Certif-2026-A",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["credential"]["secret"] is None
    assert body["account"]["can_cascade_delete"] is True


@pytest.mark.parametrize(
    "credential",
    [
        "Corta-1",                      # menos de 15 caracteres
        "Clave con espacios 2026",      # caracteres no permitidos
        "A" * 46,                       # "acme.reader:" + 46 supera 57 bytes
    ],
)
async def test_service_account_rejects_invalid_admin_credential(
    admin_client: AsyncClient, csrf: str, credential: str
) -> None:
    response = await admin_client.post(
        "/admin-api/v1/service-accounts",
        headers={"x-csrf-token": csrf},
        json={
            "name": "acme.reader",
            "role": "reader",
            "grants": [{"object_type": "*", "action": "read"}],
            "credential": credential,
        },
    )
    assert response.status_code == 422, response.text


async def test_rotate_accepts_admin_defined_credential_and_archive_hides_account(
    admin_client: AsyncClient, csrf: str
) -> None:
    created = await admin_client.post(
        "/admin-api/v1/service-accounts",
        headers={"x-csrf-token": csrf},
        json={
            "name": "acme.rotor",
            "role": "reader",
            "grants": [{"object_type": "*", "action": "read"}],
        },
    )
    assert created.status_code == 201, created.text
    account_id = created.json()["account"]["id"]

    rotated = await admin_client.post(
        f"/admin-api/v1/service-accounts/{account_id}/rotate-credential",
        headers={"x-csrf-token": csrf},
        json={"credential": "Operativa-Rotada-2026"},
    )
    assert rotated.status_code == 200, rotated.text
    assert rotated.json()["secret"] is None

    archived = await admin_client.post(
        f"/admin-api/v1/service-accounts/{account_id}/archive",
        headers={"x-csrf-token": csrf},
    )
    assert archived.status_code == 200, archived.text
    assert archived.json()["archived_at"] is not None
    assert archived.json()["enabled"] is False

    listing = await admin_client.get("/admin-api/v1/service-accounts")
    assert all(item["id"] != account_id for item in listing.json())

    again = await admin_client.post(
        f"/admin-api/v1/service-accounts/{account_id}/archive",
        headers={"x-csrf-token": csrf},
    )
    assert again.status_code == 409

    rotate_archived = await admin_client.post(
        f"/admin-api/v1/service-accounts/{account_id}/rotate-credential",
        headers={"x-csrf-token": csrf},
    )
    assert rotate_archived.status_code == 409

    patch_archived = await admin_client.patch(
        f"/admin-api/v1/service-accounts/{account_id}",
        headers={"x-csrf-token": csrf},
        json={"enabled": True},
    )
    assert patch_archived.status_code == 409


async def test_invitation_can_be_revoked_and_resent(
    admin_client: AsyncClient, csrf: str
) -> None:
    headers = {"x-csrf-token": csrf}
    created = await admin_client.post(
        "/admin-api/v1/invitations",
        headers=headers,
        json={"email": "auditoria.reenvio@example.com", "role": "auditor"},
    )
    assert created.status_code == 201, created.text
    first_id = created.json()["id"]

    resent = await admin_client.post(
        f"/admin-api/v1/invitations/{first_id}/resend", headers=headers
    )
    assert resent.status_code == 201, resent.text
    second_id = resent.json()["id"]
    assert second_id != first_id

    # El reenvío invalida la invitación anterior: no puede reenviarse ni cancelarse de nuevo.
    stale_resend = await admin_client.post(
        f"/admin-api/v1/invitations/{first_id}/resend", headers=headers
    )
    assert stale_resend.status_code == 409
    stale_revoke = await admin_client.post(
        f"/admin-api/v1/invitations/{first_id}/revoke", headers=headers
    )
    assert stale_revoke.status_code == 409

    revoked = await admin_client.post(
        f"/admin-api/v1/invitations/{second_id}/revoke", headers=headers
    )
    assert revoked.status_code == 200, revoked.text

    listing = await admin_client.get("/admin-api/v1/invitations")
    assert listing.status_code == 200
    assert all(item["id"] not in {first_id, second_id} for item in listing.json())

    revoke_again = await admin_client.post(
        f"/admin-api/v1/invitations/{second_id}/revoke", headers=headers
    )
    assert revoke_again.status_code == 409
    resend_revoked = await admin_client.post(
        f"/admin-api/v1/invitations/{second_id}/resend", headers=headers
    )
    assert resend_revoked.status_code == 409


async def test_profile_sessions_protect_current_session(
    admin_client: AsyncClient, csrf: str
) -> None:
    headers = {"x-csrf-token": csrf}
    listed = await admin_client.get("/admin-api/v1/profile/sessions")
    assert listed.status_code == 200, listed.text
    current = [item for item in listed.json() if item["current"]]
    assert len(current) == 1

    own = await admin_client.delete(
        f"/admin-api/v1/profile/sessions/{current[0]['reference']}", headers=headers
    )
    assert own.status_code == 409

    missing = await admin_client.delete(
        "/admin-api/v1/profile/sessions/no-existe", headers=headers
    )
    assert missing.status_code == 404

    others = await admin_client.post(
        "/admin-api/v1/profile/sessions/revoke-others", headers=headers
    )
    assert others.status_code == 200, others.text

    # La sesión actual sigue activa tras cerrar las demás.
    profile = await admin_client.get("/admin-api/v1/profile")
    assert profile.status_code == 200


async def test_archived_service_accounts_listed_only_on_request(
    admin_client: AsyncClient, csrf: str
) -> None:
    headers = {"x-csrf-token": csrf}
    created = await admin_client.post(
        "/admin-api/v1/service-accounts",
        headers=headers,
        json={
            "name": "acme.archivado",
            "role": "reader",
            "grants": [{"object_type": "*", "action": "read"}],
        },
    )
    assert created.status_code == 201, created.text
    account_id = created.json()["account"]["id"]
    archived = await admin_client.post(
        f"/admin-api/v1/service-accounts/{account_id}/archive", headers=headers
    )
    assert archived.status_code == 200, archived.text

    default = await admin_client.get("/admin-api/v1/service-accounts")
    assert all(item["id"] != account_id for item in default.json())

    full = await admin_client.get(
        "/admin-api/v1/service-accounts", params={"include_archived": "true"}
    )
    assert full.status_code == 200
    match = [item for item in full.json() if item["id"] == account_id]
    assert len(match) == 1 and match[0]["archived_at"] is not None
    assert match[0]["purge_at"] is not None


async def test_admin_routes_manage_user_sessions(admin_client: AsyncClient, csrf: str) -> None:
    headers = {"x-csrf-token": csrf}
    me = (await admin_client.get("/admin-api/v1/profile")).json()["user"]["id"]

    listed = await admin_client.get(f"/admin-api/v1/admin-users/{me}/sessions")
    assert listed.status_code == 200, listed.text
    current = [item for item in listed.json() if item["current"]]
    assert len(current) == 1

    own = await admin_client.delete(
        f"/admin-api/v1/admin-users/{me}/sessions/{current[0]['reference']}", headers=headers
    )
    assert own.status_code == 409

    closed = await admin_client.post(
        f"/admin-api/v1/admin-users/{me}/sessions/revoke-all", headers=headers
    )
    assert closed.status_code == 200, closed.text

    # La sesión que opera no se cierra al revocar todas las de su usuario.
    profile = await admin_client.get("/admin-api/v1/profile")
    assert profile.status_code == 200

    missing = await admin_client.get("/admin-api/v1/admin-users/no-existe/sessions")
    assert missing.status_code == 404


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
