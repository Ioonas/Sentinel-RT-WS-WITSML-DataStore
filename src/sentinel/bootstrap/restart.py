"""Reinicio controlado de servicios solicitado desde el panel.

El panel incrementa ``restart_generation`` en la configuración. Cada proceso (API y
worker de correo) guarda la generación con la que arrancó y, si ve un valor mayor,
termina. El supervisor del despliegue (servicio de Windows, systemd, NSSM…) es quien
los vuelve a levantar; sin supervisor, los procesos quedan detenidos.
"""

from __future__ import annotations

import asyncio
import logging
import signal
from collections.abc import Callable

from sentinel.bootstrap.container import Container

logger = logging.getLogger(__name__)

RESTART_POLL_SECONDS = 5


async def current_generation(container: Container) -> int:
    async with container.request() as services:
        return (await services.config.get()).restart_generation


async def wait_for_restart(
    container: Container,
    since: int,
    on_restart: Callable[[], None],
    interval: float = RESTART_POLL_SECONDS,
) -> None:
    """Llama a ``on_restart`` en cuanto la generación supere ``since``."""
    while True:
        await asyncio.sleep(interval)
        try:
            generation = await current_generation(container)
        except Exception:  # noqa: BLE001 - la base puede estar caída; se reintenta
            logger.warning("No se pudo leer la generación de reinicio; se reintenta")
            continue
        if generation > since:
            logger.warning("Reinicio solicitado desde el panel (generación %s)", generation)
            on_restart()
            return


def stop_api_process() -> None:
    """Apaga uvicorn de forma ordenada; el supervisor lo vuelve a levantar."""
    signal.raise_signal(signal.SIGINT)
