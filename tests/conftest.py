"""Fixtures de pruebas de integración con PostgreSQL."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from sentinel.admin_api.app import create_app
from sentinel.bootstrap.container import Container
from sentinel.bootstrap.settings import Settings
from sentinel.persistence.tables import Base

TEST_DSN = os.getenv(
    "SENTINEL_TEST_DSN",
    "postgresql+asyncpg://sentinel_test:sentinel_test@localhost:5432/sentinel_test",
)

ADMIN_PASSWORD = "Sentinel-Dev-2026"
CONTACT = {"contact_email": "ops@example.com", "contact_phone": "+1 555 0100"}


def test_settings() -> Settings:
    return Settings(
        env="test",
        database_url=TEST_DSN,
        require_https=False,
        cookie_secure=False,
        admin_origin="http://testserver",
        public_base_url="http://testserver",
        schema_dir=None,
        smtp_user="",
    )


@pytest_asyncio.fixture
async def container() -> AsyncIterator[Container]:
    resolved = test_settings()
    # En pruebas no se abre conexión SMTP real; el setup usa una comprobación simulada.
    instance = Container(resolved, smtp_check=lambda: None)
    async with instance.engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield instance
    finally:
        await instance.dispose()


@pytest_asyncio.fixture
async def client(container: Container) -> AsyncIterator[AsyncClient]:
    app = create_app(container)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http:
        yield http


@pytest_asyncio.fixture
async def admin_client(client: AsyncClient) -> AsyncClient:
    response = await client.post(
        "/admin-api/v1/setup",
        json={
            "contact_email": CONTACT["contact_email"],
            "contact_phone": CONTACT["contact_phone"],
            "admin_email": "admin@example.com",
            "admin_name": "Administrador",
            "admin_password": ADMIN_PASSWORD,
        },
    )
    assert response.status_code == 201, response.text
    return client


@pytest.fixture
def csrf(admin_client: AsyncClient) -> str:
    return admin_client.cookies.get("sentinel_csrf") or ""


@pytest.fixture
def soap_headers() -> dict[str, str]:
    return {"content-type": "text/xml; charset=utf-8"}
