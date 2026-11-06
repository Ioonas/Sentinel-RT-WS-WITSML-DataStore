"""Tareas de retención que corren dentro del proceso de la API.

El borrado de cuentas archivadas es idempotente: si una pasada falla, la
siguiente retoma lo pendiente sin duplicar efectos.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from sentinel.audit_config.domain import AuditChannel, AuditResult
from sentinel.bootstrap.container import Container

logger = logging.getLogger(__name__)

RETENTION_INTERVAL = timedelta(hours=1)


async def purge_archived_service_accounts(container: Container) -> int:
    async with container.request() as services:
        purged = await services.identities.purge_expired_archived_accounts()
        for account in purged:
            await services.audit.record(
                actor_id=None,
                actor_name="sistema",
                channel=AuditChannel.SYSTEM,
                action="service-account.purged",
                result=AuditResult.SUCCESS,
                correlation_id=f"retention:{account.id}",
                object_type="service_account",
                object_uid=account.id,
                details={"name": account.name},
            )
    return len(purged)


async def run_retention_forever(
    container: Container, interval: timedelta = RETENTION_INTERVAL
) -> None:
    while True:
        try:
            purged = await purge_archived_service_accounts(container)
            if purged:
                logger.info("Retención: %s cuenta(s) archivada(s) borrada(s)", purged)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - la tarea no debe morir por una pasada fallida
            logger.exception("Ciclo de retención falló")
        await asyncio.sleep(interval.total_seconds())
