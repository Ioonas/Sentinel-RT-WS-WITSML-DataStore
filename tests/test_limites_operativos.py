"""Límites operativos editables por el superadministrador."""

from __future__ import annotations

from httpx import AsyncClient

LIMITS = {
    "max_data_nodes": 5000,
    "max_data_points": 250000,
    "growing_timeout_seconds": 1800,
    "change_detection_seconds": 30,
    "max_request_latest_values": 200,
}


async def test_limits_update_requires_csrf(admin_client: AsyncClient) -> None:
    response = await admin_client.put("/admin-api/v1/server-config/limits", json=LIMITS)
    assert response.status_code == 403


async def test_limits_update_applies_and_is_visible(admin_client: AsyncClient, csrf: str) -> None:
    response = await admin_client.put(
        "/admin-api/v1/server-config/limits", headers={"x-csrf-token": csrf}, json=LIMITS
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["max_data_nodes"] == 5000
    assert body["max_data_points"] == 250000
    assert body["growing_timeout_seconds"] == 1800
    assert body["change_detection_seconds"] == 30
    assert body["max_request_latest_values"] == 200

    config = await admin_client.get("/admin-api/v1/server-config")
    assert config.json()["max_data_nodes"] == 5000


async def test_limits_reject_out_of_range_values(admin_client: AsyncClient, csrf: str) -> None:
    for field, value in (
        ("max_data_nodes", 0),
        ("max_data_points", 2_147_483_648),
        ("change_detection_seconds", -1),
    ):
        payload = {**LIMITS, field: value}
        response = await admin_client.put(
            "/admin-api/v1/server-config/limits", headers={"x-csrf-token": csrf}, json=payload
        )
        assert response.status_code == 422, (field, response.text)
