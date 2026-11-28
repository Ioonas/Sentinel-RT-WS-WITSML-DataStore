"""Comandos de línea de comandos del producto."""

from __future__ import annotations

import asyncio
import logging
import os

import uvicorn

from sentinel.bootstrap.settings import Settings


def _serve(role: str) -> None:
    # El módulo de la app se importa dentro de uvicorn; el rol se fija antes por entorno.
    os.environ["SENTINEL_API_ROLE"] = role
    settings = Settings()
    port = settings.witsml_port if role == "witsml" else settings.admin_port
    uvicorn.run(
        "sentinel.bootstrap.main:app",
        host=settings.host,
        port=port,
        log_level=settings.log_level.lower(),
        proxy_headers=True,
    )


def serve_witsml() -> None:
    """Store API WITSML (SOAP). Va detrás de nginx en la ruta /witsml."""
    _serve("witsml")


def serve_admin() -> None:
    """API administrativa y tareas de retención; la sirve el panel."""
    _serve("admin")


def serve() -> None:
    """Compatibilidad: arranca el rol configurado en SENTINEL_API_ROLE."""
    _serve(Settings().api_role)


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
