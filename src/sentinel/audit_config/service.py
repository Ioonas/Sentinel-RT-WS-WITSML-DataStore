"""Casos de uso de configuración, auditoría y correo.

``ConfigService`` es la única fuente de la metadata de producto: setup,
administración y ``WMLS_GetCap`` leen de aquí (DRY, §6).
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import replace

from sentinel.audit_config.domain import (
    AuditChannel,
    AuditEvent,
    AuditResult,
    MailJob,
    MailKind,
    ServerConfig,
)
from sentinel.audit_config.ports import (
    AuditRepositoryPort,
    MailOutboxPort,
    ServerConfigRepositoryPort,
)
from sentinel.identity_access.domain import HumanRole
from sentinel.identity_access.service import IdentityService
from sentinel.shared.clock import Clock
from sentinel.shared.errors import ConflictError, ValidationError
from sentinel.shared.ids import IdGenerator

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE = re.compile(r"^[+()0-9.\-\s]{6,32}$")


class ConfigService:
    def __init__(self, repository: ServerConfigRepositoryPort, clock: Clock) -> None:
        self._repo = repository
        self._clock = clock

    async def get(self) -> ServerConfig:
        config = await self._repo.get()
        if config is None:
            config = ServerConfig()
            await self._repo.save(config)
        return config

    async def update_contact(
        self, *, email: str, phone: str, actor: str
    ) -> ServerConfig:
        self.validate_contact(email, phone)
        config = await self.get()
        config.contact_email = email.strip()
        config.contact_phone = phone.strip()
        config.updated_at = self._clock.now()
        config.updated_by = actor
        await self._repo.save(config)
        return config

    async def update_cascaded_delete(self, *, enabled: bool, actor: str) -> ServerConfig:
        config = await self.get()
        config.cascaded_delete = enabled
        config.updated_at = self._clock.now()
        config.updated_by = actor
        await self._repo.save(config)
        return config

    async def complete_setup(
        self,
        *,
        email: str,
        phone: str,
        actor: str,
        cascaded_delete: bool = False,
    ) -> ServerConfig:
        config = await self.get()
        if config.setup_completed:
            raise ConflictError("La configuración inicial ya fue completada.")
        self.validate_contact(email, phone)
        config.contact_email = email.strip()
        config.contact_phone = phone.strip()
        config.cascaded_delete = cascaded_delete
        config.setup_completed = True
        config.updated_at = self._clock.now()
        config.updated_by = actor
        await self._repo.save(config)
        return config

    @staticmethod
    def validate_contact(email: str, phone: str) -> None:
        if not email or not _EMAIL.match(email.strip()):
            raise ValidationError("El correo de contacto no es válido.")
        if not phone or not _PHONE.match(phone.strip()):
            raise ValidationError("El teléfono de contacto no es válido.")


class AuditService:
    def __init__(
        self,
        repository: AuditRepositoryPort,
        clock: Clock,
    ) -> None:
        self._repo = repository
        self._clock = clock

    async def record(
        self,
        *,
        actor_id: str | None,
        actor_name: str,
        channel: AuditChannel,
        action: str,
        result: AuditResult = AuditResult.SUCCESS,
        correlation_id: str,
        object_type: str | None = None,
        object_uid: str | None = None,
        duration_ms: int | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        await self._repo.add(
            AuditEvent(
                actor_id=actor_id,
                actor_name=actor_name,
                channel=channel,
                action=action,
                result=result,
                correlation_id=correlation_id,
                occurred_at=self._clock.now(),
                object_type=object_type,
                object_uid=object_uid,
                duration_ms=duration_ms,
                details=_redact(details or {}),
            )
        )

    async def search(self, **kwargs) -> tuple[list[AuditEvent], int | None]:
        return await self._repo.search(**kwargs)


class SetupService:
    """Primer arranque: contacto público + primer superadministrador.

    No usa credenciales predeterminadas (§4) y es idempotente solo en el
    sentido de que rechaza una segunda ejecución.
    """

    def __init__(
        self,
        config: ConfigService,
        identities: IdentityService,
        audit: AuditService,
        clock: Clock,
    ) -> None:
        self._config = config
        self._identities = identities
        self._audit = audit
        self._clock = clock

    async def status(self) -> bool:
        config = await self._config.get()
        return config.setup_completed

    async def run(
        self,
        *,
        contact_email: str,
        contact_phone: str,
        admin_email: str,
        admin_name: str,
        admin_password: str,
        cascaded_delete: bool = False,
        correlation_id: str,
    ) -> None:
        if await self.status():
            raise ConflictError("La configuración inicial ya fue completada.")
        ConfigService.validate_contact(contact_email, contact_phone)
        user = await self._identities.create_admin_user(
            email=admin_email,
            display_name=admin_name,
            role=HumanRole.SUPERADMIN,
            password=admin_password,
        )
        await self._config.complete_setup(
            email=contact_email,
            phone=contact_phone,
            actor=user.email,
            cascaded_delete=cascaded_delete,
        )
        await self._audit.record(
            actor_id=user.id,
            actor_name=user.email,
            channel=AuditChannel.ADMIN,
            action="setup.completed",
            correlation_id=correlation_id,
            details={"contact_email": contact_email, "admin_email": admin_email},
        )


class MailService:
    """Encola correo en PostgreSQL; el worker SMTP lo envía fuera de la solicitud."""

    def __init__(
        self,
        outbox: MailOutboxPort,
        clock: Clock,
        ids: IdGenerator,
        public_base_url: str,
    ) -> None:
        self._outbox = outbox
        self._clock = clock
        self._ids = ids
        self._base = public_base_url.rstrip("/")

    async def enqueue_invitation(self, recipient: str, token: str) -> None:
        link = f"{self._base}/admin/accept-invitation?token={token}"
        await self._outbox.enqueue(
            MailJob(
                id=self._ids.new_uid(),
                kind=MailKind.INVITATION.value,
                recipient=recipient,
                subject="Invitación a Sentinel RT&WS WITSML DataStore",
                body=(
                    "Ha sido invitado a Sentinel RT&WS WITSML DataStore.\n"
                    f"Establezca su contraseña con este enlace de un solo uso: {link}\n"
                    "Si no esperaba esta invitación, ignore este mensaje."
                ),
                created_at=self._clock.now(),
            )
        )

    async def enqueue_recovery(self, recipient: str, token: str) -> None:
        link = f"{self._base}/admin/reset-password?token={token}"
        await self._outbox.enqueue(
            MailJob(
                id=self._ids.new_uid(),
                kind=MailKind.RECOVERY.value,
                recipient=recipient,
                subject="Recuperación de acceso - Sentinel RT&WS WITSML DataStore",
                body=(
                    "Solicitud de recuperación de acceso.\n"
                    f"Use este enlace de un solo uso: {link}\n"
                    "Si no realizó la solicitud, ignore este mensaje."
                ),
                created_at=self._clock.now(),
            )
        )


def _redact(details: dict[str, object]) -> dict[str, object]:
    """Elimina cualquier clave sensible antes de persistir auditoría (§8)."""
    forbidden = {
        "password",
        "secret",
        "token",
        "authorization",
        "credential",
        "cookie",
        "xml",
        "xmlin",
        "xmlout",
    }
    return {
        key: value
        for key, value in details.items()
        if key.lower() not in forbidden and "password" not in key.lower()
    }


def config_with(config: ServerConfig, **changes: object) -> ServerConfig:
    return replace(config, **changes)


class HealthService:
    """Estado operativo separado por dependencia (§8).

    No expone detalles sensibles: solo el estado y contadores agregados.
    """

    def __init__(
        self,
        *,
        probe: Probe,
        mail: MailOutboxPort,
        clock: Clock,
    ) -> None:
        self._probe = probe
        self._mail = mail
        self._clock = clock

    async def dependencies(self) -> dict[str, dict[str, object]]:
        postgres: dict[str, object] = {"status": "ok"}
        try:
            await self._probe()
        except Exception as exc:  # noqa: BLE001 - se reporta sin detalles sensibles
            postgres = {"status": "unavailable", "error": type(exc).__name__}
        pending = await self._mail.pending_count()
        oldest = await self._mail.oldest_pending_at()
        mail_status = "ok"
        if oldest is not None:
            age = (self._clock.now() - oldest).total_seconds()
            if age > 600:
                mail_status = "degraded"
        return {
            "wmls": {"status": "ok"},
            "admin_api": {"status": "ok"},
            "postgresql": postgres,
            "mail": {"status": mail_status, "pending": pending},
        }

    async def overall(self) -> str:
        dependencies = await self.dependencies()
        statuses = {item["status"] for item in dependencies.values()}
        if "unavailable" in statuses:
            return "unavailable"
        if "degraded" in statuses:
            return "degraded"
        return "available"

    async def ready(self) -> bool:
        dependencies = await self.dependencies()
        return dependencies["postgresql"]["status"] == "ok"


Probe = Callable[[], Awaitable[None]]
