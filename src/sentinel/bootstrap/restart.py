"""Reinicio controlado de servicios solicitado desde el panel.

Cada proceso (API WITSML y API administrativa, worker de correo) tiene un registro en
``service_status``. El panel incrementa ``requested_generation`` del servicio elegido.
El proceso lo detecta en su heartbeat y:

1. entra en modo *drenaje*: la API rechaza solicitudes nuevas de escritura y WMLS con
   503; el worker no toma más lotes;
2. espera a que sus operaciones en curso terminen (``in_flight == 0``);
3. si no terminan dentro de ``DRAIN_TIMEOUT_SECONDS``, cancela el reinicio y lo reporta
   en ``last_error``; si terminan, sale para que su supervisor lo vuelva a levantar.

El supervisor (``sentinel.bootstrap.supervisor``) es quien relanza los procesos.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
from typing import Any

from sentinel.bootstrap.container import Container

logger = logging.getLogger(__name__)

POLL_SECONDS = 2.0
DRAIN_TIMEOUT_SECONDS = 300.0

STATE_RUNNING = "running"
STATE_DRAINING = "draining"
STATE_RESTARTING = "restarting"

DECISION_NONE = "none"
DECISION_DRAIN = "drain"
DECISION_RESTART = "restart"
DECISION_CANCEL = "cancel"


def restart_decision(
    *, requested: int, handled: int, in_flight: int, waited: float, timeout: float
) -> str:
    """Qué hacer con una solicitud de reinicio pendiente. Función pura para probarla."""
    if requested <= handled:
        return DECISION_NONE
    if in_flight == 0:
        return DECISION_RESTART
    if waited >= timeout:
        return DECISION_CANCEL
    return DECISION_DRAIN


class ServiceLifecycle:
    """Heartbeat, detección de reinicios y conteo de operaciones en curso de un proceso."""

    def __init__(
        self,
        container: Container,
        name: str,
        *,
        poll_seconds: float = POLL_SECONDS,
        drain_timeout: float = DRAIN_TIMEOUT_SECONDS,
    ) -> None:
        self._container = container
        self.name = name
        self._poll = poll_seconds
        self._timeout = drain_timeout
        self.in_flight = 0
        self.draining = False
        self.restart_event = asyncio.Event()
        self._handled = 0
        self._started_at = None
        self._last_error: str | None = None
        self._state = STATE_RUNNING
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        async with self._container.request() as services:
            record = await services.services.get_record(self.name)
            self._handled = record.requested_generation if record else 0
            self._started_at = self._container.clock.now()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _run(self) -> None:
        waited = 0.0
        while True:
            await asyncio.sleep(self._poll)
            try:
                async with self._container.request() as services:
                    record = await services.services.get_record(self.name)
                    requested = record.requested_generation if record else 0
                    decision = restart_decision(
                        requested=requested,
                        handled=self._handled,
                        in_flight=self.in_flight,
                        waited=waited,
                        timeout=self._timeout,
                    )
                    if decision == DECISION_DRAIN:
                        self.draining = True
                        self._state = STATE_DRAINING
                        waited += self._poll
                    elif decision == DECISION_RESTART:
                        self._state = STATE_RESTARTING
                        await self._heartbeat(services)
                        logger.warning(
                            "Reinicio solicitado; %s sin operaciones en curso", self.name
                        )
                        self.restart_event.set()
                        return
                    elif decision == DECISION_CANCEL:
                        self._handled = requested
                        self._last_error = (
                            f"Reinicio cancelado: {self.in_flight} operación(es) en curso "
                            f"tras {self._timeout:.0f} s"
                        )
                        logger.warning(self._last_error)
                        self.draining = False
                        self._state = STATE_RUNNING
                        waited = 0.0
                    else:
                        self.draining = False
                        self._state = STATE_RUNNING
                        waited = 0.0
                    await self._heartbeat(services)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - la base puede estar caída; se reintenta
                logger.warning("No se pudo leer o reportar el estado de %s", self.name)

    async def _heartbeat(self, services: Any) -> None:
        await services.services.heartbeat(
            self.name,
            pid=os.getpid(),
            state=self._state,
            in_flight=self.in_flight,
            started_at=self._started_at,
            last_error=self._last_error,
        )


class RequestGuard:
    """Cuenta operaciones en curso de la API y rechaza trabajo nuevo mientras drena.

    Cuenta WMLS y escrituras administrativas (no GET). Las lecturas del panel no
    bloquean el reinicio.
    """

    RETRY_AFTER_SECONDS = "30"

    def __init__(
        self, app: Any, *, lifecycle: ServiceLifecycle, guarded_prefixes: tuple[str, ...]
    ) -> None:
        self._app = app
        self._lifecycle = lifecycle
        self._prefixes = guarded_prefixes

    def _guarded(self, scope: dict[str, Any]) -> bool:
        path = scope.get("path", "")
        if path.startswith(self._prefixes[0]):
            return True
        return scope.get("method", "GET") not in ("GET", "HEAD", "OPTIONS") and path.startswith(
            self._prefixes[1]
        )

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http" or not self._guarded(scope):
            await self._app(scope, receive, send)
            return
        if self._lifecycle.draining:
            await _reject(send, self.RETRY_AFTER_SECONDS)
            return
        self._lifecycle.in_flight += 1
        try:
            await self._app(scope, receive, send)
        finally:
            self._lifecycle.in_flight -= 1


async def _reject(send: Any, retry_after: str) -> None:
    body = b'{"detail":"Servicio en reinicio; intente de nuevo en unos segundos."}'
    await send(
        {
            "type": "http.response.start",
            "status": 503,
            "headers": [
                (b"content-type", b"application/json"),
                (b"retry-after", retry_after.encode()),
                (b"content-length", str(len(body)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


async def watch_api_restart(lifecycle: ServiceLifecycle) -> None:
    """Cuando hay reinicio, apaga uvicorn de forma ordenada; el supervisor lo relanza."""
    await lifecycle.restart_event.wait()
    signal.raise_signal(signal.SIGINT)
