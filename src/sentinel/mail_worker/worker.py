"""Worker SMTP que consume la cola de correo de PostgreSQL.

El envío ocurre fuera de la solicitud HTTP: un fallo de SMTP nunca detiene la
Store API ni la API administrativa (§8).
"""

from __future__ import annotations

import asyncio
import logging
import smtplib
from datetime import timedelta
from email.message import EmailMessage

from sentinel.audit_config.domain import AuditChannel, AuditResult, MailJob
from sentinel.bootstrap.container import Container
from sentinel.bootstrap.settings import Settings

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 10


class MailWorker:
    def __init__(self, container: Container) -> None:
        self._container = container
        self._settings = container.settings

    async def run_once(self) -> int:
        async with self._container.request() as services:
            now = self._container.clock.now()
            jobs = await services.repos.mail.claim_pending(now, limit=10)
            for job in jobs:
                try:
                    await asyncio.to_thread(self._send, job)
                except Exception as exc:  # noqa: BLE001 - se registra sin secretos
                    delay = min(3600, 30 * (2 ** min(job.attempts, 6)))
                    await services.repos.mail.mark_failed(
                        job.id, type(exc).__name__, now + timedelta(seconds=delay)
                    )
                    logger.warning(
                        "Correo %s falló (intento %s): %s",
                        job.id,
                        job.attempts,
                        type(exc).__name__,
                    )
                    await services.audit.record(
                        actor_id=None,
                        actor_name="mail-worker",
                        channel=AuditChannel.MAIL,
                        action="mail.delivery.failed",
                        result=AuditResult.ERROR,
                        correlation_id=f"mail:{job.id}",
                        details={"kind": job.kind, "attempts": job.attempts},
                    )
                else:
                    await services.repos.mail.mark_sent(job.id, now)
                    logger.info("Correo %s enviado a %s", job.id, job.recipient)
            return len(jobs)

    def _send(self, job: MailJob) -> None:
        settings = self._settings
        message = EmailMessage()
        message["From"] = settings.smtp_from
        message["To"] = job.recipient
        message["Subject"] = job.subject
        message.set_content(job.body)

        with smtplib.SMTP(
            settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout_seconds
        ) as client:
            if settings.smtp_starttls:
                client.starttls()
            if settings.smtp_user:
                client.login(settings.smtp_user, settings.smtp_password)
            client.send_message(message)


async def run_forever(settings: Settings | None = None) -> None:
    resolved = settings or Settings()
    container = Container(resolved)
    worker = MailWorker(container)
    logger.info("Worker de correo iniciado (intervalo %ss)", resolved.mail_worker_interval_seconds)
    try:
        while True:
            try:
                processed = await worker.run_once()
            except Exception:  # noqa: BLE001 - el worker no debe morir por un ciclo
                logger.exception("Ciclo del worker de correo falló")
                processed = 0
            if not processed:
                await asyncio.sleep(resolved.mail_worker_interval_seconds)
    finally:
        await container.dispose()
