"""Puertos de configuración, auditoría y cola de correo."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from sentinel.audit_config.domain import AuditEvent, MailJob, ServerConfig, ServiceRecord


class ServerConfigRepositoryPort(Protocol):
    async def get(self) -> ServerConfig | None: ...

    async def save(self, config: ServerConfig) -> None: ...


class ServiceControlPort(Protocol):
    async def list_services(self) -> list[ServiceRecord]: ...

    async def get_service(self, name: str) -> ServiceRecord | None: ...

    async def request_restart(
        self, names: list[str], actor: str, now: datetime
    ) -> list[ServiceRecord]: ...

    async def heartbeat(
        self,
        name: str,
        *,
        pid: int,
        state: str,
        in_flight: int,
        started_at: datetime | None,
        now: datetime,
        last_error: str | None,
    ) -> None: ...


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
        self, job_id: str, error: str, next_attempt_at: datetime, max_attempts: int = 5
    ) -> None: ...

    async def pending_count(self) -> int: ...

    async def get_job(self, job_id: str) -> MailJob | None: ...

    async def list_jobs(
        self,
        *,
        status: str | None,
        kind: str | None,
        before: datetime | None,
        limit: int,
    ) -> list[MailJob]: ...

    async def retry_job(self, job_id: str, now: datetime) -> bool: ...

    async def oldest_pending_at(self) -> datetime | None: ...
