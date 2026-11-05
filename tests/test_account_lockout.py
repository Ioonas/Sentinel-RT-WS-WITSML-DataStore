"""Bloqueo temporal de cuentas tras intentos fallidos repetidos.

Cubre el login administrativo y la autenticación HTTP Basic de WMLS. El reloj
es controlable para comprobar que el bloqueo expira a los 15 minutos.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from sentinel.admin_api.app import create_app
from sentinel.bootstrap.container import Container
from sentinel.persistence.tables import Base
from sentinel.shared.clock import FixedClock
from tests.conftest import ADMIN_PASSWORD, CONTACT
from tests.conftest import test_settings as build_settings
from tests.test_wmls_soap import create_writer, soap

WRONG_PASSWORD = "Contraseña-incorrecta-1"
MAX_ATTEMPTS = 5


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(datetime(2026, 11, 5, 10, 0, tzinfo=UTC))


@pytest_asyncio.fixture
async def lockout_client(clock: FixedClock) -> AsyncIterator[AsyncClient]:
    instance = Container(build_settings(), clock=clock)
    async with instance.engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    app = create_app(instance)
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://testserver") as http:
            response = await http.post(
                "/admin-api/v1/setup",
                json={
                    "contact_email": CONTACT["contact_email"],
                    "contact_phone": CONTACT["contact_phone"],
                    "admin_email": "admin@example.com",
                    "admin_name": "Administrador",
                    "admin_password": ADMIN_PASSWORD,
                },
            )
            assert response.status_code in (200, 201)
            yield http
    finally:
        await instance.dispose()


async def _login(client: AsyncClient, password: str) -> int:
    response = await client.post(
        "/admin-api/v1/auth/sessions",
        json={"email": "admin@example.com", "password": password},
    )
    return response.status_code


async def test_admin_login_locks_after_repeated_failures(
    lockout_client: AsyncClient, clock: FixedClock
) -> None:
    for _ in range(MAX_ATTEMPTS):
        assert await _login(lockout_client, WRONG_PASSWORD) == 401

    # Bloqueado: ni siquiera la contraseña correcta abre sesión, y el mensaje es el mismo.
    locked = await lockout_client.post(
        "/admin-api/v1/auth/sessions",
        json={"email": "admin@example.com", "password": ADMIN_PASSWORD},
    )
    assert locked.status_code == 401
    assert locked.json()["message"] == "Credenciales inválidas."

    clock.advance(15 * 60 + 1)
    assert await _login(lockout_client, ADMIN_PASSWORD) == 200


async def test_admin_successful_login_resets_failure_counter(
    lockout_client: AsyncClient,
) -> None:
    for _ in range(MAX_ATTEMPTS - 1):
        assert await _login(lockout_client, WRONG_PASSWORD) == 401
    assert await _login(lockout_client, ADMIN_PASSWORD) == 200
    # Tras el acierto el contador vuelve a cero: otros cuatro fallos no bloquean.
    for _ in range(MAX_ATTEMPTS - 1):
        assert await _login(lockout_client, WRONG_PASSWORD) == 401
    assert await _login(lockout_client, ADMIN_PASSWORD) == 200


async def test_wmls_basic_auth_locks_service_account(
    lockout_client: AsyncClient, clock: FixedClock
) -> None:
    assert await _login(lockout_client, ADMIN_PASSWORD) == 200
    csrf = lockout_client.cookies.get("sentinel_csrf") or ""
    secret = await create_writer(lockout_client, csrf)

    for _ in range(MAX_ATTEMPTS):
        response = await soap(lockout_client, "GetVersion", "secreto-erroneo-123456")
        assert response.status_code == 401

    # Con la cuenta bloqueada, el secreto correcto también se rechaza.
    locked = await soap(lockout_client, "GetVersion", secret)
    assert locked.status_code == 401

    clock.advance(15 * 60 + 1)
    unlocked = await soap(lockout_client, "GetVersion", secret)
    assert unlocked.status_code == 200


def test_lockout_window_is_fifteen_minutes() -> None:
    from sentinel.identity_access.service import LOCKOUT_DURATION, MAX_FAILED_ATTEMPTS

    assert MAX_FAILED_ATTEMPTS == MAX_ATTEMPTS
    assert timedelta(minutes=15) == LOCKOUT_DURATION
