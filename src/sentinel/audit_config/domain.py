"""Configuración del servidor, capacidades publicadas y auditoría."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


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
    max_data_nodes: int = 10_000
    max_data_points: int = 3_000_000
    growing_timeout_seconds: int = 3_600
    change_detection_seconds: int = 60
    max_request_latest_values: int = 500
    cascaded_delete: bool = True
    support_uom_conversion: bool = False
    updated_at: datetime | None = None
    updated_by: str | None = None


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
