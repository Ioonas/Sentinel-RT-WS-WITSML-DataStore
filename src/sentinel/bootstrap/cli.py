"""Comandos de línea de comandos del producto."""

from __future__ import annotations

import asyncio
import logging

import uvicorn

from sentinel.bootstrap.settings import Settings


def serve() -> None:
    """Inicia la API administrativa y el endpoint WMLS con uvicorn."""
    settings = Settings()
    uvicorn.run(
        "sentinel.bootstrap.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        proxy_headers=True,
    )


def mail_worker() -> None:
    """Inicia el worker SMTP que consume la cola de correo."""
    from sentinel.mail_worker.worker import run_forever

    logging.basicConfig(
        level=getattr(logging, Settings().log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    asyncio.run(run_forever())


if __name__ == "__main__":
    serve()
