"""Identidades, roles y permisos.

Reglas del spec (§5): se deniega por defecto, la autorización se valida en cada
operación y el alcance por pozo (``uidWell``) es opcional. Los roles humanos y
las cuentas de servicio son independientes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class PrincipalKind(StrEnum):
    HUMAN = "human"
    SERVICE = "service"
    SYSTEM = "system"


class WitsmlAction(StrEnum):
    READ = "read"
    WRITE = "write"
    DELETE = "delete"


class AdminPermission(StrEnum):
    CONFIG_WRITE = "admin.config.write"
    IDENTITY_WRITE = "admin.identities.write"
    AUDIT_READ = "admin.audit.read"
    OBJECTS_READ = "admin.objects.read"
    OBJECTS_DELETE = "admin.objects.delete"
    HEALTH_READ = "admin.health.read"
    ROLES_READ = "admin.roles.read"


class HumanRole(StrEnum):
    SUPERADMIN = "superadministrador"
    ADMIN = "administrador"
    AUDITOR = "auditor"
    OPERATOR = "operador"
    SECURITY_ADMIN = "administrador_seguridad"


class ServiceRole(StrEnum):
    READER = "reader"
    WRITER = "writer"


ALL_ADMIN_PERMISSIONS: frozenset[str] = frozenset(p.value for p in AdminPermission)

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    HumanRole.SUPERADMIN.value: ALL_ADMIN_PERMISSIONS,
    HumanRole.AUDITOR.value: frozenset(
        {AdminPermission.AUDIT_READ.value, AdminPermission.OBJECTS_READ.value,
         AdminPermission.ROLES_READ.value}
    ),
    HumanRole.OPERATOR.value: frozenset(
        {AdminPermission.OBJECTS_READ.value, AdminPermission.HEALTH_READ.value,
         AdminPermission.ROLES_READ.value}
    ),
    HumanRole.SECURITY_ADMIN.value: frozenset(
        {AdminPermission.IDENTITY_WRITE.value, AdminPermission.ROLES_READ.value,
         AdminPermission.AUDIT_READ.value, AdminPermission.HEALTH_READ.value}
    ),
    # El rol administrador solo recibe los permisos que un superadministrador le
    # delegue explícitamente (columna permissions del usuario).
    HumanRole.ADMIN.value: frozenset(),
}

SUPPORTED_WITSML_OBJECTS: tuple[str, ...] = (
    "well",
    "wellbore",
    "log",
    "mudLog",
    "trajectory",
)


@dataclass(frozen=True)
class Grant:
    """Permiso WMLS por objeto y acción, opcionalmente acotado a un pozo."""

    object_type: str
    action: WitsmlAction
    uid_well: str | None = None

    def allows(self, action: WitsmlAction, object_type: str, uid_well: str | None) -> bool:
        if self.action != action:
            return False
        if self.object_type not in ("*", object_type):
            return False
        return not (self.uid_well is not None and self.uid_well != uid_well)
    def to_dict(self) -> dict[str, str | None]:
        return {
            "object_type": self.object_type,
            "action": self.action.value,
            "uid_well": self.uid_well,
        }


@dataclass(frozen=True)
class Principal:
    """Identidad autenticada que ejecuta una operación."""

    id: str
    name: str
    kind: PrincipalKind
    role: str
    permissions: frozenset[str] = field(default_factory=frozenset)
    grants: tuple[Grant, ...] = ()
    well_scope: frozenset[str] | None = None
    # Solo cuentas de servicio con este indicador pueden borrar en cascada (WMLS -414 si no).
    can_cascade_delete: bool = False

    @property
    def is_superadmin(self) -> bool:
        return self.kind == PrincipalKind.HUMAN and self.role == HumanRole.SUPERADMIN.value

    @property
    def is_system(self) -> bool:
        return self.kind == PrincipalKind.SYSTEM

    def has(self, permission: AdminPermission | str) -> bool:
        if self.is_superadmin:
            return True
        value = permission.value if isinstance(permission, AdminPermission) else permission
        return value in self.permissions

    def allows_witsml(
        self, action: WitsmlAction, object_type: str, uid_well: str | None
    ) -> bool:
        if self.is_superadmin or self.is_system:
            return True
        if uid_well is None:
            # Consulta global: basta con tener la acción para el tipo; el
            # repositorio aplica el alcance por pozo al filtrar.
            return self.has_grant(action, object_type)
        if self.well_scope is not None and uid_well not in self.well_scope:
            return False
        return any(grant.allows(action, object_type, uid_well) for grant in self.grants)

    def has_grant(self, action: WitsmlAction, object_type: str) -> bool:
        if self.is_superadmin or self.is_system:
            return True
        return any(
            grant.action == action and grant.object_type in ("*", object_type)
            for grant in self.grants
        )

    @property
    def readable_wells(self) -> frozenset[str] | None:
        """Pozos que el actor puede leer; ``None`` significa sin restricción."""
        if self.is_superadmin or self.is_system:
            return None
        if self.well_scope is not None:
            scoped = {
                grant.uid_well for grant in self.grants if grant.uid_well is not None
            }
            return frozenset(scoped & set(self.well_scope)) if scoped else frozenset(
                self.well_scope
            )
        if any(grant.uid_well is None for grant in self.grants):
            return None
        scoped = {grant.uid_well for grant in self.grants if grant.uid_well is not None}
        return frozenset(scoped) if scoped else None


def permissions_for_role(role: str, delegated: list[str] | None = None) -> frozenset[str]:
    if role == HumanRole.ADMIN.value:
        return frozenset(delegated or ())
    return ROLE_PERMISSIONS.get(role, frozenset())
