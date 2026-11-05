"""Política de contraseñas: longitud, lista de contraseñas comunes y palabras de contexto."""

from __future__ import annotations

from httpx import AsyncClient

from sentinel.identity_access.compromised import context_terms, is_common
from tests.conftest import CONTACT


def test_common_list_is_normalized_and_case_insensitive() -> None:
    assert is_common("password")
    assert is_common("1QAZ2WSX3EDC4RFV")
    assert not is_common("Clave-Operativa-2026")


def test_context_terms_include_product_and_account_fragments() -> None:
    terms = context_terms("administrador@example.com", "Ana Pérez")
    assert "sentinel" in terms
    assert "administrador" in terms
    assert "example" in terms
    assert "ana" not in terms  # fragmentos menores de 4 caracteres se ignoran


async def test_setup_rejects_common_password(client: AsyncClient) -> None:
    response = await client.post(
        "/admin-api/v1/setup",
        json={
            "contact_email": CONTACT["contact_email"],
            "contact_phone": CONTACT["contact_phone"],
            "admin_email": "operador@example.com",
            "admin_name": "Operador",
            "admin_password": "1qAz2wsx3edc4rfv",
        },
    )
    assert response.status_code >= 400
    assert "demasiado común" in response.json()["message"]


async def test_setup_rejects_account_and_product_words(client: AsyncClient) -> None:
    response = await client.post(
        "/admin-api/v1/setup",
        json={
            "contact_email": CONTACT["contact_email"],
            "contact_phone": CONTACT["contact_phone"],
            "admin_email": "administrador@example.com",
            "admin_name": "Administrador",
            "admin_password": "Tr7mx-administrador-2026",
        },
    )
    assert response.status_code >= 400
    assert "datos de la cuenta" in response.json()["message"]


async def test_setup_rejects_product_name_in_password(client: AsyncClient) -> None:
    response = await client.post(
        "/admin-api/v1/setup",
        json={
            "contact_email": CONTACT["contact_email"],
            "contact_phone": CONTACT["contact_phone"],
            "admin_email": "operador@example.com",
            "admin_name": "Operador",
            "admin_password": "Sentinel-Clave-2026",
        },
    )
    assert response.status_code >= 400
    assert "datos de la cuenta" in response.json()["message"]
