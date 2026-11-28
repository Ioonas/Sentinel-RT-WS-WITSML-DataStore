"""Punto de entrada ASGI de Sentinel RT&WS WITSML DataStore."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from sentinel.admin_api.app import ADMIN_PREFIX, create_app
from sentinel.audit_config.domain import SERVICE_API
from sentinel.bootstrap.container import Container
from sentinel.bootstrap.restart import RequestGuard, ServiceLifecycle, watch_api_restart
from sentinel.bootstrap.retention import run_retention_forever
from sentinel.bootstrap.settings import Settings


def build_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or Settings()
    logging.basicConfig(
        level=getattr(logging, resolved.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    container = Container(resolved)
    lifecycle = ServiceLifecycle(container, SERVICE_API)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        logging.getLogger(__name__).info(
            "Iniciando %s en entorno %s", "Sentinel RT&WS WITSML DataStore", resolved.env
        )
        retention = asyncio.create_task(run_retention_forever(container))
        await lifecycle.start()
        watcher = asyncio.create_task(watch_api_restart(lifecycle))
        try:
            yield
        finally:
            watcher.cancel()
            retention.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await retention
            with contextlib.suppress(asyncio.CancelledError):
                await watcher
            await lifecycle.stop()
            await container.dispose()

    app = create_app(container, lifespan=lifespan)
    app.add_middleware(
        RequestGuard,
        lifecycle=lifecycle,
        guarded_prefixes=("/witsml", ADMIN_PREFIX),
    )
    return app


app = build_app()
