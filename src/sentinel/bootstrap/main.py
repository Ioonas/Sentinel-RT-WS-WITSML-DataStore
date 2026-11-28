"""Punto de entrada ASGI de Sentinel RT&WS WITSML DataStore.

Cada proceso sirve un rol: ``witsml`` (Store API WMLS) o ``admin`` (API administrativa,
panel y tareas de retención). Se elige con ``SENTINEL_API_ROLE``.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from sentinel.admin_api.app import ADMIN_PREFIX, create_app
from sentinel.audit_config.domain import SERVICE_ADMIN, SERVICE_WITSML
from sentinel.bootstrap.container import Container
from sentinel.bootstrap.restart import RequestGuard, ServiceLifecycle, watch_api_restart
from sentinel.bootstrap.retention import run_retention_forever
from sentinel.bootstrap.settings import Settings

ROLE_SERVICE = {"witsml": SERVICE_WITSML, "admin": SERVICE_ADMIN}


def build_app(settings: Settings | None = None, *, role: str | None = None) -> FastAPI:
    resolved = settings or Settings()
    active_role = role or resolved.api_role
    if active_role not in ROLE_SERVICE:
        raise ValueError(f"Rol de API desconocido: {active_role}")
    logging.basicConfig(
        level=getattr(logging, resolved.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    container = Container(resolved)
    lifecycle = ServiceLifecycle(container, ROLE_SERVICE[active_role])

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        logging.getLogger(__name__).info(
            "Iniciando %s (rol %s) en entorno %s",
            "Sentinel RT&WS WITSML DataStore",
            active_role,
            resolved.env,
        )
        # La retención corre una sola vez: solo en el proceso administrativo.
        retention = (
            asyncio.create_task(run_retention_forever(container))
            if active_role == "admin"
            else None
        )
        await lifecycle.start()
        watcher = asyncio.create_task(watch_api_restart(lifecycle))
        try:
            yield
        finally:
            watcher.cancel()
            if retention is not None:
                retention.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await retention
            with contextlib.suppress(asyncio.CancelledError):
                await watcher
            await lifecycle.stop()
            await container.dispose()

    app = create_app(container, lifespan=lifespan, role=active_role)
    app.add_middleware(
        RequestGuard,
        lifecycle=lifecycle,
        guarded_prefixes=("/witsml", ADMIN_PREFIX),
    )
    return app


app = build_app()
