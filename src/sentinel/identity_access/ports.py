"""Puertos de identidad y acceso.

Los adaptadores de persistencia implementan estos protocolos; el núcleo de
identidad no conoce SQLAlchemy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from sentinel.identity_access.domain import (
    Grant,
    HumanRole,
    Principal,
    PrincipalKind,
    ServiceRole,
)


@dataclass
class ServiceAccountRecord:
    id: str
    name: str
    role: ServiceRole
    enabled: bool
    credential_hash: str | None
    grants: tuple[Grant, ...] = ()
    well_scope: frozenset[str] | None = None
    created_at: datetime | None = None
    last_used_at: datetime | None = None
    rotated_at: datetime | None = None

    def to_principal(self) -> Principal:
        return Principal(
            id=self.id,
            name=self.name,
            kind=PrincipalKind.SERVICE,
            role=self.role.value,
            grants=self.grants,
            well_scope=self.well_scope,
        )


@dataclass
class AdminUserRecord:
    id: str
    email: str
    display_name: str
    role: HumanRole
    password_hash: str
    enabled: bool = True
    permissions: frozenset[str] = field(default_factory=frozenset)
    must_change_password: bool = False
    created_at: datetime | None = None
    last_login_at: datetime | None = None

    def to_principal(self) -> Principal:
        return Principal(
            id=self.id,
            name=self.email,
            kind=PrincipalKind.HUMAN,
            role=self.role.value,
            permissions=self.permissions,
        )


@dataclass
class SessionRecord:
    token_hash: str
    user_id: str
    csrf_token: str
    created_at: datetime
    expires_at: datetime
    authenticated_at: datetime
    revoked_at: datetime | None = None


@dataclass
class InvitationRecord:
    id: str
    email: str
    role: HumanRole
    token_hash: str
    expires_at: datetime
    created_by: str
    permissions: frozenset[str] = field(default_factory=frozenset)
    accepted_at: datetime | None = None
    created_at: datetime | None = None


@dataclass
class PasswordResetRecord:
    token_hash: str
    user_id: str
    expires_at: datetime
    created_at: datetime
    used_at: datetime | None = None


class IdentityRepositoryPort(Protocol):
    async def get_service_account_by_name(self, name: str) -> ServiceAccountRecord | None: ...

    async def get_service_account(self, account_id: str) -> ServiceAccountRecord | None: ...

    async def list_service_accounts(self) -> list[ServiceAccountRecord]: ...

    async def save_service_account(self, account: ServiceAccountRecord) -> None: ...

    async def delete_service_account(self, account_id: str) -> None: ...

    async def get_admin_user_by_email(self, email: str) -> AdminUserRecord | None: ...

    async def get_admin_user(self, user_id: str) -> AdminUserRecord | None: ...

    async def list_admin_users(self) -> list[AdminUserRecord]: ...

    async def save_admin_user(self, user: AdminUserRecord) -> None: ...

    async def count_admin_users(self) -> int: ...

    async def save_session(self, session: SessionRecord) -> None: ...

    async def get_session(self, token_hash: str) -> SessionRecord | None: ...

    async def revoke_session(self, token_hash: str, revoked_at: datetime) -> None: ...

    async def revoke_user_sessions(self, user_id: str, revoked_at: datetime) -> None: ...

    async def save_invitation(self, invitation: InvitationRecord) -> None: ...

    async def get_invitation_by_token_hash(
        self, token_hash: str
    ) -> InvitationRecord | None: ...

    async def mark_invitation_accepted(
        self, invitation_id: str, accepted_at: datetime
    ) -> None: ...

    async def save_password_reset(self, reset: PasswordResetRecord) -> None: ...

    async def get_password_reset(
        self, token_hash: str
    ) -> PasswordResetRecord | None: ...

    async def mark_password_reset_used(
        self, token_hash: str, used_at: datetime
    ) -> None: ...


class PasswordHasherPort(Protocol):
    def hash(self, secret: str) -> str: ...

    def verify(self, secret: str, hashed: str) -> bool: ...

    def needs_rehash(self, hashed: str) -> bool: ...


class TokenHasherPort(Protocol):
    def hash_token(self, token: str) -> str: ...
