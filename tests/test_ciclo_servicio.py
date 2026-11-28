"""Ciclo de vida de un proceso: drena, reinicia o cancela; y el guardia HTTP."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace

from sentinel.audit_config.domain import ServiceRecord
from sentinel.bootstrap.restart import STATE_DRAINING, RequestGuard, ServiceLifecycle


class FakeServiceControl:
    def __init__(self) -> None:
        self.record = ServiceRecord(name="api", requested_generation=0)
        self.beats: list[dict] = []

    async def get_record(self, name: str) -> ServiceRecord:
        return self.record

    async def heartbeat(self, name: str, **kwargs) -> None:
        self.beats.append(kwargs)


class FakeContainer:
    def __init__(self) -> None:
        self.services = FakeServiceControl()
        self.clock = SimpleNamespace(now=lambda: datetime.now(UTC))

    @asynccontextmanager
    async def request(self):
        yield SimpleNamespace(services=self.services)


async def test_reinicia_cuando_no_hay_operaciones_en_curso() -> None:
    container = FakeContainer()
    lifecycle = ServiceLifecycle(container, "api", poll_seconds=0.02, drain_timeout=5)
    await lifecycle.start()
    try:
        lifecycle.in_flight = 1
        container.services.record.requested_generation = 1
        await asyncio.sleep(0.15)
        assert lifecycle.draining is True
        assert container.services.beats[-1]["state"] == STATE_DRAINING

        lifecycle.in_flight = 0
        await asyncio.wait_for(lifecycle.restart_event.wait(), timeout=2)
    finally:
        await lifecycle.stop()


async def test_cancela_si_las_operaciones_no_terminan_a_tiempo() -> None:
    container = FakeContainer()
    lifecycle = ServiceLifecycle(container, "api", poll_seconds=0.02, drain_timeout=0.1)
    await lifecycle.start()
    try:
        lifecycle.in_flight = 1
        container.services.record.requested_generation = 1
        await asyncio.sleep(0.4)
        assert not lifecycle.restart_event.is_set()
        assert lifecycle.draining is False
        assert lifecycle._last_error is not None and "cancelado" in lifecycle._last_error

        # Una nueva solicitud vuelve a intentarlo.
        lifecycle.in_flight = 0
        container.services.record.requested_generation = 2
        await asyncio.wait_for(lifecycle.restart_event.wait(), timeout=2)
    finally:
        await lifecycle.stop()


async def test_guardia_rechaza_trabajo_nuevo_mientras_drena() -> None:
    lifecycle = SimpleNamespace(draining=True, in_flight=0)
    calls: list[str] = []

    async def inner(scope, receive, send):
        calls.append(scope["path"])

    sent: list[dict] = []

    async def send(message):
        sent.append(message)

    guard = RequestGuard(inner, lifecycle=lifecycle, guarded_prefixes=("/witsml", "/admin-api/v1"))
    await guard({"type": "http", "path": "/witsml", "method": "POST"}, None, send)
    assert calls == []
    assert sent[0]["status"] == 503

    lifecycle.draining = False
    await guard({"type": "http", "path": "/witsml", "method": "POST"}, None, send)
    assert calls == ["/witsml"]
    assert lifecycle.in_flight == 0


async def test_guardia_no_cuenta_lecturas_del_panel() -> None:
    lifecycle = SimpleNamespace(draining=True, in_flight=0)
    calls: list[str] = []

    async def inner(scope, receive, send):
        calls.append(scope["path"])

    async def send(message):
        return None

    guard = RequestGuard(inner, lifecycle=lifecycle, guarded_prefixes=("/witsml", "/admin-api/v1"))
    await guard({"type": "http", "path": "/admin-api/v1/objects", "method": "GET"}, None, send)
    assert calls == ["/admin-api/v1/objects"]
