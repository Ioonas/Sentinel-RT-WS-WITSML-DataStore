"""Configuración del servidor, capacidades publicadas y auditoría."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

# Máximo de Integer en PostgreSQL: en la práctica, sin límite operativo.
UNLIMITED_DATA = 2_147_483_647


class AuditResult(StrEnum):
    SUCCESS = "success"
    DENIED = "denied"
    ERROR = "error"


class AuditChannel(StrEnum):
    WMLS = "wmls"
    ADMIN = "admin"
    SYSTEM = "system"
    MAIL = "mail"


@dataclass
class ServerConfig:
    """Única fuente de verdad de la metadata de ``capServer`` (DRY, §6)."""

    contact_name: str = "Sentinel RT&WS WITSML DataStore"
    contact_email: str = ""
    contact_phone: str = ""
    description: str = "Sentinel RT&WS WITSML DataStore 1.4.1.1"
    product_name: str = "Sentinel RT&WS WITSML DataStore"
    vendor: str = "Sentinel Real Time & Web Services"
    version: str = "1.0.3"
    schema_version: str = "1.4.1.1"
    api_version: str = "1.4.1"
    setup_completed: bool = False
    # Referencia aprobada en D-17 del expediente (§ Valores de GetCap).
    max_data_nodes: int = UNLIMITED_DATA
    max_data_points: int = UNLIMITED_DATA
    growing_timeout_seconds: int = 3_600
    change_detection_seconds: int = 60
    max_request_latest_values: int = 500
    cascaded_delete: bool = True
    support_uom_conversion: bool = False
    # Correo: remitente vacío = el de entorno (SENTINEL_SMTP_FROM).
    mail_from: str = ""
    mail_max_attempts: int = 5
    mail_backoff_base_seconds: int = 30
    updated_at: datetime | None = None
    updated_by: str | None = None


SERVICE_API = "api"
SERVICE_MAIL_WORKER = "mail-worker"
SERVICE_NAMES: tuple[str, ...] = (SERVICE_API, SERVICE_MAIL_WORKER)


@dataclass
class ServiceRecord:
    """Estado de un proceso del servidor: lo reporta el propio proceso (heartbeat)."""

    name: str
    requested_generation: int = 0
    requested_at: datetime | None = None
    requested_by: str | None = None
    pid: int | None = None
    # running | draining | restarting | stopped (vacío si nunca reportó)
    state: str = "stopped"
    in_flight: int = 0
    started_at: datetime | None = None
    heartbeat_at: datetime | None = None
    last_error: str | None = None


@dataclass
class AuditEvent:
    actor_id: str | None
    actor_name: str
    channel: AuditChannel
    action: str
    result: AuditResult
    correlation_id: str
    occurred_at: datetime
    object_type: str | None = None
    object_uid: str | None = None
    duration_ms: int | None = None
    details: dict[str, object] = field(default_factory=dict)
    id: int | None = None


@dataclass
class MailJob:
    id: str
    kind: str
    recipient: str
    subject: str
    body: str
    status: str = "pending"
    attempts: int = 0
    next_attempt_at: datetime | None = None
    last_error: str | None = None
    created_at: datetime | None = None


class MailKind(StrEnum):
    INVITATION = "invitation"
    RECOVERY = "recovery"
    SESSIONS_CLOSED = "sessions_closed"
    ACCOUNT_DELETED = "account_deleted"
