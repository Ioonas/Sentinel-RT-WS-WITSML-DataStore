"""Un superadministrador restablece la contraseña de otro usuario: el enlace va por correo."""

from __future__ import annotations

from httpx import AsyncClient

from tests.test_invitaciones_pendientes import clock_client  # noqa: F401  (fixture)


async def _create_second_admin(client: AsyncClient, csrf: str) -> str:
    invited = await client.post(
        "/admin-api/v1/invitations",
        headers={"x-csrf-token": csrf},
        json={"email": "otro.admin@example.com", "role": "auditor"},
    )
    assert invited.status_code == 201, invited.text
    token = invited.json()["token"]
    accepted = await client.post(
        "/admin-api/v1/invitations/accept",
        json={
            "token": token,
            "password": "Clave-segura-de-prueba-2026",
            "display_name": "Otro administrador",
        },
    )
    assert accepted.status_code in (200, 201), accepted.text
    listed = await client.get("/admin-api/v1/admin-users")
    return next(u["id"] for u in listed.json() if u["email"] == "otro.admin@example.com")


async def test_superadmin_restablece_contrasena_por_correo(clock_client) -> None:  # noqa: F811
    client, _clock = clock_client
    csrf = client.cookies.get("sentinel_csrf") or ""
    target_id = await _create_second_admin(client, csrf)

    reset = await client.post(
        f"/admin-api/v1/admin-users/{target_id}/reset-password",
        headers={"x-csrf-token": csrf},
    )
    assert reset.status_code == 200, reset.text
    # La respuesta nunca incluye el enlace ni una contraseña temporal.
    assert "token" not in reset.text
    assert "http" not in reset.text

    outbox = await client.get("/admin-api/v1/mail-outbox", params={"kind": "recovery"})
    assert any(
        item["recipient"] == "otro.admin@example.com" for item in outbox.json()["items"]
    )


async def test_no_permite_restablecer_la_propia_cuenta(clock_client) -> None:  # noqa: F811
    client, _clock = clock_client
    csrf = client.cookies.get("sentinel_csrf") or ""
    me = await client.get("/admin-api/v1/profile")
    own_id = me.json()["user"]["id"]

    reset = await client.post(
        f"/admin-api/v1/admin-users/{own_id}/reset-password",
        headers={"x-csrf-token": csrf},
    )
    assert reset.status_code == 409, reset.text


async def test_usuario_inexistente_devuelve_404(clock_client) -> None:  # noqa: F811
    client, _clock = clock_client
    csrf = client.cookies.get("sentinel_csrf") or ""
    reset = await client.post(
        "/admin-api/v1/admin-users/no-existe/reset-password",
        headers={"x-csrf-token": csrf},
    )
    assert reset.status_code == 404, reset.text
