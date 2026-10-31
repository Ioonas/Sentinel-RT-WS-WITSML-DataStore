"""Puertos de configuración, auditoría y cola de correo."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from sentinel.audit_config.domain import AuditEvent, MailJob, ServerConfig


class ServerConfigRepositoryPort(Protocol):
    async def get(self) -> ServerConfig | None: ...

    async def save(self, config: ServerConfig) -> None: ...


class AuditRepositoryPort(Protocol):
    async def add(self, event: AuditEvent) -> None: ...

    async def search(
        self,
        *,
        limit: int = 50,
        cursor: int | None = None,
        actor: str | None = None,
        action: str | None = None,
        object_type: str | None = None,
        object_uid: str | None = None,
        result: str | None = None,
        correlation_id: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> tuple[list[AuditEvent], int | None]: ...


class MailOutboxPort(Protocol):
    async def enqueue(self, job: MailJob) -> None: ...

    async def claim_pending(self, now: datetime, limit: int = 10) -> list[MailJob]: ...

    async def mark_sent(self, job_id: str, sent_at: datetime) -> None: ...

    async def mark_failed(
        self, job_id: str, error: str, next_attempt_at: datetime
    ) -> None: ...

    async def pending_count(self) -> int: ...

    async def oldest_pending_at(self) -> datetime | None: ...
