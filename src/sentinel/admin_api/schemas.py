"""Contratos Pydantic de la API administrativa (OpenAPI)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from sentinel.identity_access.domain import HumanRole, ServiceRole, WitsmlAction


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GrantIn(StrictModel):
    object_type: str = Field(pattern=r"^(well|wellbore|log|mudLog|trajectory|\*)$")
    action: WitsmlAction
    uid_well: str | None = None


class GrantView(BaseModel):
    object_type: str
    action: str
    uid_well: str | None = None


class UserView(BaseModel):
    id: str
    email: str
    display_name: str
    role: str
    permissions: list[str]
    enabled: bool
    must_change_password: bool
    created_at: datetime | None = None
    last_login_at: datetime | None = None


class SessionView(BaseModel):
    user: UserView
    expires_at: datetime | None = None


class LoginRequest(StrictModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=1024)


class SetupStatusView(BaseModel):
    setup_completed: bool


class SetupRequest(StrictModel):
    contact_email: str = Field(min_length=3, max_length=255)
    contact_phone: str = Field(min_length=6, max_length=32)
    admin_email: str = Field(min_length=3, max_length=255)
    admin_name: str = Field(min_length=1, max_length=255)
    admin_password: str = Field(min_length=12, max_length=1024)


class ContactUpdateRequest(StrictModel):
    contact_email: str = Field(min_length=3, max_length=255)
    contact_phone: str = Field(min_length=6, max_length=32)


class ServerConfigView(BaseModel):
    contact_name: str
    contact_email: str
    contact_phone: str
    description: str
    product_name: str
    vendor: str
    version: str
    schema_version: str
    api_version: str
    setup_completed: bool
    max_data_nodes: int
    max_data_points: int
    growing_timeout_seconds: int
    change_detection_seconds: int
    max_request_latest_values: int
    cascaded_delete: bool
    support_uom_conversion: bool
    updated_at: datetime | None = None
    updated_by: str | None = None


class ServiceAccountCreate(StrictModel):
    name: str = Field(min_length=3, max_length=64)
    role: ServiceRole
    grants: list[GrantIn] = Field(min_length=1)
    well_scope: list[str] | None = None


class ServiceAccountUpdate(StrictModel):
    enabled: bool | None = None
    role: ServiceRole | None = None
    grants: list[GrantIn] | None = None
    well_scope: list[str] | None = None


class ServiceAccountView(BaseModel):
    id: str
    name: str
    role: str
    enabled: bool
    grants: list[GrantView]
    well_scope: list[str] | None
    created_at: datetime | None = None
    last_used_at: datetime | None = None
    rotated_at: datetime | None = None


class CredentialView(BaseModel):
    secret: str
    message: str = "El secreto se muestra una sola vez."


class ServiceAccountCreatedView(BaseModel):
    account: ServiceAccountView
    credential: CredentialView


class InvitationCreate(StrictModel):
    email: str = Field(min_length=3, max_length=255)
    role: HumanRole
    permissions: list[str] | None = None


class InvitationView(BaseModel):
    id: str
    email: str
    role: str
    expires_at: datetime
    token: str | None = None


class AcceptInvitationRequest(StrictModel):
    token: str = Field(min_length=10, max_length=512)
    password: str = Field(min_length=12, max_length=1024)
    display_name: str | None = Field(default=None, max_length=255)


class AdminUserUpdate(StrictModel):
    enabled: bool | None = None
    role: HumanRole | None = None
    permissions: list[str] | None = None
    display_name: str | None = Field(default=None, max_length=255)


class RecoveryRequest(StrictModel):
    email: str = Field(min_length=3, max_length=255)


class ResetPasswordRequest(StrictModel):
    token: str = Field(min_length=10, max_length=512)
    new_password: str = Field(min_length=12, max_length=1024)


class PasswordChangeRequest(StrictModel):
    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=12, max_length=1024)


class RoleView(BaseModel):
    name: str
    permissions: list[str]


class PermissionView(BaseModel):
    name: str


class AccessView(BaseModel):
    identity: str
    kind: str
    role: str
    permissions: list[str]
    grants: list[GrantView]


class ObjectView(BaseModel):
    object_type: str
    uid: str
    uid_well: str | None
    uid_wellbore: str | None
    name: str | None
    created_at: datetime
    changed_at: datetime
    growing: bool


class ObjectDeleteRequest(StrictModel):
    reason: str = Field(min_length=5, max_length=500)
    confirmation: str = Field(min_length=1, max_length=128)


class AuditEventView(BaseModel):
    id: int
    occurred_at: datetime
    actor_id: str | None
    actor_name: str
    channel: str
    action: str
    object_type: str | None
    object_uid: str | None
    result: str
    correlation_id: str
    duration_ms: int | None
    details: dict


class AuditPage(BaseModel):
    items: list[AuditEventView]
    next_cursor: int | None


class HealthView(BaseModel):
    status: str


class DependencyHealthView(BaseModel):
    status: str
    dependencies: dict[str, dict]


class MessageView(BaseModel):
    message: str
