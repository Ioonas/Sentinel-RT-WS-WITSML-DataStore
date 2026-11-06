"""Casos de uso de identidad y acceso.

Este módulo es núcleo: no importa adaptadores. Recibe puertos por inyección.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from sentinel.identity_access.compromised import (
    contains_context_term,
    context_terms,
    is_common,
)
from sentinel.identity_access.domain import (
    ALL_ADMIN_PERMISSIONS,
    AdminPermission,
    Grant,
    HumanRole,
    Principal,
    ServiceRole,
    WitsmlAction,
    permissions_for_role,
)
from sentinel.identity_access.ports import (
    AdminUserRecord,
    IdentityRepositoryPort,
    InvitationRecord,
    PasswordHasherPort,
    PasswordResetRecord,
    ServiceAccountRecord,
    SessionRecord,
    TokenHasherPort,
)
from sentinel.shared.clock import Clock
from sentinel.shared.errors import (
    AuthenticationError,
    ConflictError,
    NotFoundError,
    PermissionDenied,
    ValidationError,
)
from sentinel.shared.ids import IdGenerator

_ACCOUNT_NAME = re.compile(r"^[A-Za-z0-9._-]{3,64}$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_SERVICE_CREDENTIAL = re.compile(r"[A-Za-z0-9._-]+")
# Clientes WMLS que codifican Basic en base64 sin saltos de línea (por ejemplo, la
# herramienta wPCTT) solo aceptan cabeceras de 76 caracteres base64 como máximo.
# Eso equivale a "usuario:credencial" de hasta 57 bytes.
_MAX_BASIC_PAIR_BYTES = 57
_MIN_SERVICE_CREDENTIAL = 15

SESSION_TTL = timedelta(hours=12)
REAUTH_WINDOW = timedelta(minutes=15)
# Bloqueo por cuenta: tras MAX_FAILED_ATTEMPTS contraseñas incorrectas seguidas,
# la cuenta no acepta intentos durante LOCKOUT_DURATION.
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION = timedelta(minutes=15)


def _is_locked(locked_until: datetime | None, now: datetime) -> bool:
    return locked_until is not None and locked_until > now


def _register_failure(record, now: datetime) -> None:
    record.failed_attempts += 1
    if record.failed_attempts >= MAX_FAILED_ATTEMPTS:
        record.locked_until = now + LOCKOUT_DURATION
        record.failed_attempts = 0
INVITATION_TTL = timedelta(hours=72)
# Tiempo que una cuenta archivada permanece antes de su borrado automático.
ARCHIVE_GRACE = timedelta(days=3)


@dataclass(frozen=True)
class LoginResult:
    token: str
    csrf_token: str
    principal: Principal
    expires_at: datetime


def session_reference(token_hash: str) -> str:
    """Referencia opaca y estable de una sesión; no expone el hash guardado."""
    return hashlib.sha256(f"session-ref:{token_hash}".encode()).hexdigest()[:32]


class IdentityService:
    def __init__(
        self,
        repository: IdentityRepositoryPort,
        hasher: PasswordHasherPort,
        token_hasher: TokenHasherPort,
        clock: Clock,
        ids: IdGenerator,
    ) -> None:
        self._repo = repository
        self._hasher = hasher
        self._tokens = token_hasher
        self._clock = clock
        self._ids = ids

    # ------------------------------------------------------------------
    # Cuentas de servicio (HTTP Basic en WMLS)
    # ------------------------------------------------------------------
    async def authenticate_service_account(
        self, name: str, secret: str
    ) -> Principal | None:
        account = await self._repo.get_service_account_by_name(name)
        if account is None or not account.enabled or not account.credential_hash:
            # Verificación ficticia para no filtrar por tiempo si la cuenta no existe.
            self._hasher.verify(secret, "$argon2id$v=19$m=65536,t=3,p=2$aaaaaaaaaaaaaaaa$")
            return None
        now = self._clock.now()
        if account.is_retired(now):
            return None
        if _is_locked(account.locked_until, now):
            # Mismo coste que un intento real para no revelar el estado del bloqueo.
            self._hasher.verify(secret, account.credential_hash)
            return None
        if not self._hasher.verify(secret, account.credential_hash):
            _register_failure(account, now)
            await self._repo.save_service_account(account)
            return None
        account.failed_attempts = 0
        account.locked_until = None
        account.last_used_at = now
        await self._repo.save_service_account(account)
        return account.to_principal()

    async def create_service_account(
        self,
        *,
        name: str,
        role: ServiceRole,
        grants: list[Grant],
        well_scope: set[str] | None,
        can_cascade_delete: bool = False,
        replaces: ServiceAccountRecord | None = None,
        replacement_grace: timedelta = timedelta(days=7),
        credential: str | None = None,
    ) -> tuple[ServiceAccountRecord, str | None]:
        """Crea la cuenta. Devuelve el secreto generado, o None si lo definió el administrador."""
        if not _ACCOUNT_NAME.match(name):
            raise ValidationError(
                "El nombre de la cuenta debe tener 3-64 caracteres [A-Za-z0-9._-]."
            )
        if await self._repo.get_service_account_by_name(name) is not None:
            raise ConflictError("Ya existe una cuenta de servicio con ese nombre.")
        self._validate_grants(role, grants)
        if replaces is not None and replaces.replaced_by_id is not None:
            raise ConflictError("La cuenta indicada ya fue reemplazada.")
        if replaces is not None and replaces.is_archived:
            raise ConflictError("La cuenta indicada está archivada.")
        if credential is None:
            secret = self._new_secret()
            returned: str | None = secret
        else:
            self._validate_service_credential(name, credential)
            secret = credential
            returned = None
        now = self._clock.now()
        account = ServiceAccountRecord(
            id=self._ids.new_uid(),
            name=name,
            role=role,
            enabled=True,
            credential_hash=self._hasher.hash(secret),
            grants=tuple(grants),
            # None = sin restricción (todos los pozos); un conjunto vacío = ningún pozo.
            well_scope=frozenset(well_scope) if well_scope is not None else None,
            created_at=now,
            rotated_at=now,
            can_cascade_delete=can_cascade_delete,
        )
        await self._repo.save_service_account(account)
        if replaces is not None:
            # La cuenta anterior sigue activa durante la transición y luego se retira.
            replaces.replaced_by_id = account.id
            replaces.replacement_expires_at = now + replacement_grace
            await self._repo.save_service_account(replaces)
        return account, returned

    async def update_service_account(
        self,
        account_id: str,
        *,
        enabled: bool | None = None,
        grants: list[Grant] | None = None,
        well_scope: set[str] | None = None,
        role: ServiceRole | None = None,
    ) -> ServiceAccountRecord:
        account = await self._repo.get_service_account(account_id)
        if account is None:
            raise NotFoundError("Cuenta de servicio no encontrada.")
        if account.is_archived:
            raise ConflictError("La cuenta está archivada y no se puede modificar.")
        effective_role = role or account.role
        effective_grants = tuple(grants) if grants is not None else account.grants
        self._validate_grants(effective_role, list(effective_grants))
        account.role = effective_role
        account.grants = effective_grants
        if well_scope is not None:
            account.well_scope = frozenset(well_scope)
        if enabled is not None:
            account.enabled = enabled
        await self._repo.save_service_account(account)
        return account

    async def add_well_to_scope(self, account_id: str, uid: str) -> None:
        """Incorpora al alcance de la cuenta un pozo que ella misma acaba de crear."""
        account = await self._repo.get_service_account(account_id)
        if account is None or account.well_scope is None:
            return
        account.well_scope = account.well_scope | {uid}
        await self._repo.save_service_account(account)

    async def rotate_credential(
        self, account_id: str, *, credential: str | None = None
    ) -> str | None:
        """Genera una credencial nueva, o usa la indicada. Devuelve el secreto generado o None."""
        account = await self._repo.get_service_account(account_id)
        if account is None:
            raise NotFoundError("Cuenta de servicio no encontrada.")
        if account.is_archived:
            raise ConflictError("La cuenta está archivada y no se puede modificar.")
        if credential is None:
            secret = self._new_secret()
            returned: str | None = secret
        else:
            self._validate_service_credential(account.name, credential)
            secret = credential
            returned = None
        account.credential_hash = self._hasher.hash(secret)
        account.rotated_at = self._clock.now()
        account.enabled = True
        await self._repo.save_service_account(account)
        return returned

    async def archive_service_account(self, account_id: str) -> ServiceAccountRecord:
        """Archiva la cuenta: deja de autenticar y sale de la lista, pero conserva su registro."""
        account = await self._repo.get_service_account(account_id)
        if account is None:
            raise NotFoundError("Cuenta de servicio no encontrada.")
        if account.is_archived:
            raise ConflictError("La cuenta ya está archivada.")
        account.archived_at = self._clock.now()
        account.enabled = False
        account.credential_hash = None
        await self._repo.save_service_account(account)
        return account

    async def revoke_credential(self, account_id: str) -> None:
        account = await self._repo.get_service_account(account_id)
        if account is None:
            raise NotFoundError("Cuenta de servicio no encontrada.")
        account.credential_hash = None
        account.enabled = False
        await self._repo.save_service_account(account)

    async def purge_expired_archived_accounts(self) -> list[ServiceAccountRecord]:
        """Borra las cuentas archivadas cuyo periodo de gracia ya venció.

        Es idempotente: una cuenta borrada no vuelve a aparecer en la siguiente pasada.
        """
        cutoff = self._clock.now() - ARCHIVE_GRACE
        accounts = await self._repo.list_service_accounts()
        expired = [
            account
            for account in accounts
            if account.archived_at is not None and account.archived_at <= cutoff
        ]
        for account in expired:
            await self._repo.delete_service_account(account.id)
        return expired

    async def list_service_accounts(
        self, *, include_archived: bool = False
    ) -> list[ServiceAccountRecord]:
        # Por defecto las archivadas no aparecen; su registro se conserva siempre.
        accounts = await self._repo.list_service_accounts()
        if include_archived:
            return accounts
        return [account for account in accounts if not account.is_archived]

    async def get_service_account(self, account_id: str) -> ServiceAccountRecord:
        account = await self._repo.get_service_account(account_id)
        if account is None:
            raise NotFoundError("Cuenta de servicio no encontrada.")
        return account

    # ------------------------------------------------------------------
    # Sesiones humanas
    # ------------------------------------------------------------------
    async def login(self, email: str, password: str) -> LoginResult:
        user = await self._repo.get_admin_user_by_email(email.strip().lower())
        if user is None or not user.enabled:
            # Mensaje genérico: no se revela si la cuenta existe o está deshabilitada.
            raise AuthenticationError("Credenciales inválidas.")
        now = self._clock.now()
        if _is_locked(user.locked_until, now):
            self._hasher.verify(password, user.password_hash)
            raise AuthenticationError("Credenciales inválidas.")
        if not self._hasher.verify(password, user.password_hash):
            _register_failure(user, now)
            await self._repo.save_admin_user(user)
            raise AuthenticationError("Credenciales inválidas.")
        user.failed_attempts = 0
        user.locked_until = None
        if self._hasher.needs_rehash(user.password_hash):
            user.password_hash = self._hasher.hash(password)
        user.last_login_at = now
        await self._repo.save_admin_user(user)

        token = self._ids.new_token()
        csrf = self._ids.new_token(24)
        expires_at = now + SESSION_TTL
        await self._repo.save_session(
            SessionRecord(
                token_hash=self._tokens.hash_token(token),
                user_id=user.id,
                csrf_token=csrf,
                created_at=now,
                expires_at=expires_at,
                authenticated_at=now,
            )
        )
        return LoginResult(
            token=token,
            csrf_token=csrf,
            principal=await self.human_principal(user),
            expires_at=expires_at,
        )

    async def resolve_session(self, token: str) -> tuple[Principal, SessionRecord] | None:
        if not token:
            return None
        session = await self._repo.get_session(self._tokens.hash_token(token))
        if session is None or session.revoked_at is not None:
            return None
        if session.expires_at <= self._clock.now():
            return None
        user = await self._repo.get_admin_user(session.user_id)
        if user is None or not user.enabled:
            return None
        return await self.human_principal(user), session

    async def human_principal(self, user: AdminUserRecord) -> Principal:
        """Identidad de un usuario administrativo, con su alcance de pozos.

        Falla cerrada: sin vínculo a una cuenta de servicio habilitada, una persona no ve
        ningún pozo. El superadministrador no tiene restricción.
        """
        if user.role == HumanRole.SUPERADMIN:
            return user.to_principal(well_scope=None)
        scope: frozenset[str] = frozenset()
        if user.role == HumanRole.LINKED_READER and user.linked_service_account_id:
            account = await self._repo.get_service_account(user.linked_service_account_id)
            if (
                account is not None
                and account.enabled
                and not account.is_archived
                and account.well_scope is not None
            ):
                scope = account.well_scope
        principal = user.to_principal(well_scope=scope)
        if user.role == HumanRole.LINKED_READER:
            # Los permisos del rol vinculado son fijos: no dependen de lo guardado.
            principal = replace(principal, permissions=permissions_for_role(user.role.value))
        return principal

    async def reauthenticate(self, *, user_id: str, password: str, token_hash: str) -> None:
        """Renueva la ventana de reautenticación de la sesión actual."""
        user = await self._repo.get_admin_user(user_id)
        if user is None or not user.enabled:
            raise AuthenticationError("Credenciales inválidas.")
        now = self._clock.now()
        if _is_locked(user.locked_until, now):
            self._hasher.verify(password, user.password_hash)
            raise AuthenticationError("Credenciales inválidas.")
        if not self._hasher.verify(password, user.password_hash):
            _register_failure(user, now)
            await self._repo.save_admin_user(user)
            raise AuthenticationError("Credenciales inválidas.")
        user.failed_attempts = 0
        user.locked_until = None
        await self._repo.save_admin_user(user)
        await self._repo.update_session_authenticated_at(token_hash, now)

    async def list_own_sessions(self, user_id: str) -> list[SessionRecord]:
        return await self._repo.list_user_sessions(user_id, self._clock.now())

    async def revoke_own_session(
        self, *, user_id: str, reference: str, current_token_hash: str
    ) -> SessionRecord:
        now = self._clock.now()
        sessions = await self._repo.list_user_sessions(user_id, now)
        target = next(
            (s for s in sessions if session_reference(s.token_hash) == reference), None
        )
        if target is None:
            raise NotFoundError("Sesión no encontrada.")
        if target.token_hash == current_token_hash:
            raise ConflictError("Para cerrar la sesión actual use «Cerrar sesión».")
        await self._repo.revoke_session(target.token_hash, now)
        return target

    async def revoke_other_own_sessions(
        self, *, user_id: str, current_token_hash: str
    ) -> int:
        return await self._repo.revoke_other_user_sessions(
            user_id, current_token_hash, self._clock.now()
        )

    async def logout(self, token: str) -> None:
        if token:
            await self._repo.revoke_session(
                self._tokens.hash_token(token), self._clock.now()
            )

    # ------------------------------------------------------------------
    # Usuarios administrativos e invitaciones
    # ------------------------------------------------------------------
    async def create_admin_user(
        self,
        *,
        email: str,
        display_name: str,
        role: HumanRole,
        password: str,
        permissions: set[str] | None = None,
        must_change_password: bool = False,
    ) -> AdminUserRecord:
        normalized = email.strip().lower()
        if not _EMAIL.match(normalized):
            raise ValidationError("El correo no tiene un formato válido.")
        if await self._repo.get_admin_user_by_email(normalized) is not None:
            raise ConflictError("Ya existe un usuario administrativo con ese correo.")
        self._validate_password(password, context=context_terms(normalized, display_name))
        delegated = self._validate_delegated_permissions(role, permissions)
        user = AdminUserRecord(
            id=self._ids.new_uid(),
            email=normalized,
            display_name=display_name.strip() or normalized,
            role=role,
            password_hash=self._hasher.hash(password),
            enabled=True,
            permissions=permissions_for_role(role.value, sorted(delegated)),
            must_change_password=must_change_password,
            created_at=self._clock.now(),
        )
        await self._repo.save_admin_user(user)
        return user

    async def update_admin_user(
        self,
        user_id: str,
        *,
        enabled: bool | None = None,
        role: HumanRole | None = None,
        permissions: set[str] | None = None,
        display_name: str | None = None,
    ) -> AdminUserRecord:
        user = await self._repo.get_admin_user(user_id)
        if user is None:
            raise NotFoundError("Usuario administrativo no encontrado.")
        effective_role = role or user.role
        if effective_role == HumanRole.LINKED_READER and user.role != HumanRole.LINKED_READER:
            raise ValidationError(
                "Este rol solo se asigna al dar acceso web desde una cuenta de servicio."
            )
        delegated = self._validate_delegated_permissions(effective_role, permissions)
        if effective_role != user.role:
            if user.role == HumanRole.LINKED_READER:
                user.linked_service_account_id = None
            user.role = effective_role
            user.permissions = permissions_for_role(effective_role.value, sorted(delegated))
        elif permissions is not None:
            user.permissions = permissions_for_role(effective_role.value, sorted(delegated))
        if display_name is not None:
            user.display_name = display_name.strip() or user.email
        if enabled is not None:
            user.enabled = enabled
            if not enabled:
                await self._repo.revoke_user_sessions(user_id, self._clock.now())
        await self._repo.save_admin_user(user)
        return user

    async def change_password(
        self, user_id: str, current_password: str, new_password: str
    ) -> None:
        user = await self._repo.get_admin_user(user_id)
        if user is None:
            raise NotFoundError("Usuario no encontrado.")
        if not self._hasher.verify(current_password, user.password_hash):
            raise AuthenticationError("La contraseña actual no es válida.")
        self._validate_password(new_password, context=context_terms(user.email, user.display_name))
        user.password_hash = self._hasher.hash(new_password)
        user.must_change_password = False
        await self._repo.save_admin_user(user)
        # Cambiar contraseña revoca sesiones activas (spec §8).
        await self._repo.revoke_user_sessions(user_id, self._clock.now())

    async def create_invitation(
        self,
        *,
        email: str,
        role: HumanRole,
        created_by: str,
        permissions: set[str] | None = None,
    ) -> tuple[InvitationRecord, str]:
        if role == HumanRole.LINKED_READER:
            raise ValidationError(
                "Este rol solo se asigna al dar acceso web desde una cuenta de servicio."
            )
        normalized = email.strip().lower()
        if not _EMAIL.match(normalized):
            raise ValidationError("El correo no tiene un formato válido.")
        if await self._repo.get_admin_user_by_email(normalized) is not None:
            raise ConflictError("Ya existe un usuario con ese correo.")
        return await self._issue_invitation(
            email=normalized,
            role=role,
            created_by=created_by,
            permissions=permissions,
        )

    async def invite_linked_user(
        self, *, account_id: str, email: str, created_by: str
    ) -> tuple[InvitationRecord, str]:
        """Invitación de acceso web: la persona verá solo los pozos de la cuenta."""
        account = await self._repo.get_service_account(account_id)
        if account is None:
            raise NotFoundError("Cuenta de servicio no encontrada.")
        if account.is_archived or not account.enabled:
            raise ConflictError("La cuenta está deshabilitada o archivada.")
        if account.well_scope is None:
            raise ConflictError(
                "La cuenta ve todos los pozos. Defina un alcance antes de dar acceso web."
            )
        normalized = email.strip().lower()
        if not _EMAIL.match(normalized):
            raise ValidationError("El correo no tiene un formato válido.")
        if await self._repo.get_admin_user_by_email(normalized) is not None:
            raise ConflictError("Ya existe un usuario con ese correo.")
        if any(item.email == normalized for item in await self._repo.list_pending_invitations()):
            raise ConflictError(
                "Ya hay una invitación pendiente para ese correo. Reénviela o cancélela."
            )
        return await self._issue_invitation(
            email=normalized,
            role=HumanRole.LINKED_READER,
            created_by=created_by,
            permissions=None,
            linked_service_account_id=account.id,
        )

    async def linked_account_name(self, user: AdminUserRecord) -> str | None:
        if user.role != HumanRole.LINKED_READER or not user.linked_service_account_id:
            return None
        account = await self._repo.get_service_account(user.linked_service_account_id)
        return account.name if account is not None else None

    async def list_web_access(
        self, account_id: str
    ) -> tuple[list[AdminUserRecord], list[InvitationRecord]]:
        """Personas con acceso y las invitaciones pendientes vinculadas a la cuenta."""
        if await self._repo.get_service_account(account_id) is None:
            raise NotFoundError("Cuenta de servicio no encontrada.")
        users = await self._repo.list_admin_users_linked_to(account_id)
        pending = [
            item
            for item in await self._repo.list_pending_invitations()
            if item.linked_service_account_id == account_id
        ]
        return users, pending

    async def remove_web_access(self, *, account_id: str, user_id: str) -> AdminUserRecord:
        """Desvincula a la persona: deja de ver pozos y se cierran sus sesiones."""
        user = await self._repo.get_admin_user(user_id)
        if user is None or user.linked_service_account_id != account_id:
            raise NotFoundError("La persona no tiene acceso web vinculado a esta cuenta.")
        user.linked_service_account_id = None
        await self._repo.save_admin_user(user)
        await self._repo.revoke_user_sessions(user.id, self._clock.now())
        return user

    async def _issue_invitation(
        self,
        *,
        email: str,
        role: HumanRole,
        created_by: str,
        permissions: set[str] | None,
        linked_service_account_id: str | None = None,
    ) -> tuple[InvitationRecord, str]:
        delegated = self._validate_delegated_permissions(role, permissions)
        token = self._ids.new_token()
        now = self._clock.now()
        invitation = InvitationRecord(
            id=self._ids.new_uid(),
            email=email,
            role=role,
            token_hash=self._tokens.hash_token(token),
            expires_at=now + INVITATION_TTL,
            created_by=created_by,
            permissions=permissions_for_role(role.value, sorted(delegated)),
            created_at=now,
            linked_service_account_id=linked_service_account_id,
        )
        await self._repo.save_invitation(invitation)
        return invitation, token

    async def revoke_invitation(self, invitation_id: str) -> InvitationRecord:
        invitation = await self._open_invitation(invitation_id)
        await self._repo.mark_invitation_revoked(invitation.id, self._clock.now())
        return invitation

    async def resend_invitation(
        self, invitation_id: str, *, created_by: str
    ) -> tuple[InvitationRecord, str]:
        """Revoca la invitación anterior y emite una nueva con token y vencimiento propios."""
        previous = await self._open_invitation(invitation_id)
        if await self._repo.get_admin_user_by_email(previous.email) is not None:
            raise ConflictError("Ya existe un usuario con ese correo.")
        # Solo el rol administrador conserva permisos explícitos; los demás toman los del rol.
        delegated = set(previous.permissions) if previous.role == HumanRole.ADMIN else None
        await self._repo.mark_invitation_revoked(previous.id, self._clock.now())
        return await self._issue_invitation(
            email=previous.email,
            role=previous.role,
            created_by=created_by,
            permissions=delegated,
            linked_service_account_id=previous.linked_service_account_id,
        )

    async def _open_invitation(self, invitation_id: str) -> InvitationRecord:
        invitation = await self._repo.get_invitation(invitation_id)
        if invitation is None:
            raise NotFoundError("Invitación no encontrada.")
        if invitation.accepted_at is not None:
            raise ConflictError("La invitación ya fue aceptada.")
        if invitation.revoked_at is not None:
            raise ConflictError("La invitación ya fue cancelada o reemplazada.")
        return invitation

    async def accept_invitation(
        self, token: str, password: str, display_name: str | None = None
    ) -> AdminUserRecord:
        invitation = await self._repo.get_invitation_by_token_hash(
            self._tokens.hash_token(token)
        )
        now = self._clock.now()
        if (
            invitation is None
            or invitation.accepted_at is not None
            or invitation.revoked_at is not None
            or invitation.expires_at <= now
        ):
            raise ValidationError("La invitación no es válida o ha expirado.")
        self._validate_password(password, context=context_terms(invitation.email, display_name))
        if await self._repo.get_admin_user_by_email(invitation.email) is not None:
            raise ConflictError("Ya existe un usuario con ese correo.")
        user = AdminUserRecord(
            id=self._ids.new_uid(),
            email=invitation.email,
            display_name=display_name or invitation.email,
            role=invitation.role,
            password_hash=self._hasher.hash(password),
            enabled=True,
            permissions=invitation.permissions,
            created_at=now,
            linked_service_account_id=invitation.linked_service_account_id,
        )
        await self._repo.save_admin_user(user)
        await self._repo.mark_invitation_accepted(invitation.id, now)
        return user

    async def list_pending_invitations(self) -> list[InvitationRecord]:
        return await self._repo.list_pending_invitations()

    async def list_admin_users(self) -> list[AdminUserRecord]:
        return await self._repo.list_admin_users()

    async def get_admin_user(self, user_id: str) -> AdminUserRecord:
        user = await self._repo.get_admin_user(user_id)
        if user is None:
            raise NotFoundError("Usuario administrativo no encontrado.")
        return user

    async def request_password_reset(
        self, email: str
    ) -> tuple[str | None, AdminUserRecord | None]:
        """Devuelve el token solo si la cuenta existe y está habilitada.

        El adaptador responde siempre de forma genérica para no enumerar cuentas.
        """
        user = await self._repo.get_admin_user_by_email(email.strip().lower())
        if user is None or not user.enabled:
            return None, None
        token = self._ids.new_token()
        now = self._clock.now()
        await self._repo.save_password_reset(
            PasswordResetRecord(
                token_hash=self._tokens.hash_token(token),
                user_id=user.id,
                expires_at=now + timedelta(hours=1),
                created_at=now,
            )
        )
        return token, user

    async def reset_password(self, token: str, new_password: str) -> None:
        reset = await self._repo.get_password_reset(self._tokens.hash_token(token))
        now = self._clock.now()
        if reset is None or reset.used_at is not None or reset.expires_at <= now:
            raise ValidationError("El enlace de recuperación no es válido o expiró.")
        user = await self._repo.get_admin_user(reset.user_id)
        if user is None:
            raise ValidationError("El enlace de recuperación no es válido o expiró.")
        self._validate_password(new_password, context=context_terms(user.email, user.display_name))
        user.password_hash = self._hasher.hash(new_password)
        user.must_change_password = False
        await self._repo.save_admin_user(user)
        await self._repo.mark_password_reset_used(reset.token_hash, now)
        await self._repo.revoke_user_sessions(user.id, now)

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------
    def _new_secret(self) -> str:
        return f"srtws_{self._ids.new_token(32)}"

    def _validate_service_credential(self, name: str, credential: str) -> None:
        if not _SERVICE_CREDENTIAL.fullmatch(credential):
            raise ValidationError(
                "La credencial solo puede contener letras, números, punto, guion y guion bajo."
            )
        max_length = _MAX_BASIC_PAIR_BYTES - len(name) - 1
        if max_length < _MIN_SERVICE_CREDENTIAL:
            raise ValidationError(
                "El nombre es demasiado largo para una credencial compatible con clientes WMLS."
            )
        if len(credential) > max_length:
            raise ValidationError(
                f"Con este nombre, la credencial puede tener como máximo {max_length} caracteres "
                "para que los clientes WMLS la acepten."
            )
        self._validate_password(credential, context=context_terms(name))

    def _validate_password(self, password: str, *, context: frozenset[str] = frozenset()) -> None:
        if len(password) < 15:
            raise ValidationError("La contraseña debe tener al menos 15 caracteres.")
        if is_common(password):
            raise ValidationError(
                "La contraseña es demasiado común o aparece en brechas conocidas."
            )
        if contains_context_term(password, context):
            raise ValidationError(
                "La contraseña no puede contener datos de la cuenta ni del producto."
            )

    def _validate_grants(self, role: ServiceRole, grants: list[Grant]) -> None:
        if not grants:
            raise ValidationError("La cuenta de servicio requiere al menos un permiso.")
        for grant in grants:
            if grant.object_type not in (
                "*",
                "well",
                "wellbore",
                "log",
                "mudLog",
                "trajectory",
            ):
                raise ValidationError(f"Tipo de objeto no soportado: {grant.object_type}")
            if role == ServiceRole.READER and grant.action != WitsmlAction.READ:
                raise ValidationError(
                    "Una cuenta reader solo puede recibir permisos de lectura."
                )

    def _validate_delegated_permissions(
        self, role: HumanRole, permissions: set[str] | None
    ) -> set[str]:
        delegated = set(permissions or ())
        unknown = delegated - ALL_ADMIN_PERMISSIONS
        if unknown:
            raise ValidationError(f"Permisos desconocidos: {sorted(unknown)}")
        if role != HumanRole.ADMIN and delegated:
            raise ValidationError(
                "Solo el rol administrador acepta permisos delegados explícitos."
            )
        return delegated


def ensure_permission(principal: Principal, permission: AdminPermission) -> None:
    if not principal.has(permission):
        raise PermissionDenied("No tiene permiso para esta operación.")
