"""Punto de entrada ASGI de Sentinel RT&WS WITSML DataStore."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from sentinel.admin_api.app import create_app
from sentinel.bootstrap.container import Container
from sentinel.bootstrap.retention import run_retention_forever
from sentinel.bootstrap.settings import Settings


def build_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or Settings()
    logging.basicConfig(
        level=getattr(logging, resolved.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    container = Container(resolved)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        logging.getLogger(__name__).info(
            "Iniciando %s en entorno %s", "Sentinel RT&WS WITSML DataStore", resolved.env
        )
        retention = asyncio.create_task(run_retention_forever(container))
        try:
            yield
        finally:
            retention.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await retention
            await container.dispose()

    return create_app(container, lifespan=lifespan)


app = build_app()
