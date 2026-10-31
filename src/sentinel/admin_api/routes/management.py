"""Configuración, identidades, roles, acceso y auditoría."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request, status

from sentinel.admin_api.deps import (
    AuthContext,
    audit,
    correlation_id,
    get_auth,
    get_services,
    require_csrf,
    require_permission,
    require_recent_auth,
    require_superadmin,
    user_view,
)
from sentinel.admin_api.schemas import (
    AccessView,
    AdminUserUpdate,
    AuditEventView,
    AuditPage,
    ContactUpdateRequest,
    CredentialView,
    GrantIn,
    GrantView,
    InvitationCreate,
    InvitationView,
    MessageView,
    PermissionView,
    RoleView,
    ServerConfigView,
    ServiceAccountCreate,
    ServiceAccountCreatedView,
    ServiceAccountUpdate,
    ServiceAccountView,
    UserView,
)
from sentinel.audit_config.domain import AuditEvent, ServerConfig
from sentinel.bootstrap.container import RequestServices
from sentinel.identity_access.domain import (
    ALL_ADMIN_PERMISSIONS,
    ROLE_PERMISSIONS,
    AdminPermission,
    Grant,
)
from sentinel.identity_access.ports import AdminUserRecord, ServiceAccountRecord

router = APIRouter(tags=["Administración"])


def _grant_view(grant: Grant) -> GrantView:
    return GrantView(
        object_type=grant.object_type,
        action=grant.action.value,
        uid_well=grant.uid_well,
    )


def _grant_model(grant: GrantIn) -> Grant:
    return Grant(object_type=grant.object_type, action=grant.action, uid_well=grant.uid_well)


def _account_view(account: ServiceAccountRecord) -> ServiceAccountView:
    return ServiceAccountView(
        id=account.id,
        name=account.name,
        role=account.role.value,
        enabled=account.enabled,
        grants=[_grant_view(grant) for grant in account.grants],
        well_scope=sorted(account.well_scope) if account.well_scope else None,
        created_at=account.created_at,
        last_used_at=account.last_used_at,
        rotated_at=account.rotated_at,
    )


def _config_view(config: ServerConfig) -> ServerConfigView:
    return ServerConfigView(
        contact_name=config.contact_name,
        contact_email=config.contact_email,
        contact_phone=config.contact_phone,
        description=config.description,
        product_name=config.product_name,
        vendor=config.vendor,
        version=config.version,
        schema_version=config.schema_version,
        api_version=config.api_version,
        setup_completed=config.setup_completed,
        max_data_nodes=config.max_data_nodes,
        max_data_points=config.max_data_points,
        growing_timeout_seconds=config.growing_timeout_seconds,
        change_detection_seconds=config.change_detection_seconds,
        max_request_latest_values=config.max_request_latest_values,
        cascaded_delete=config.cascaded_delete,
        support_uom_conversion=config.support_uom_conversion,
        updated_at=config.updated_at,
        updated_by=config.updated_by,
    )


def _audit_view(event: AuditEvent) -> AuditEventView:
    return AuditEventView(
        id=event.id or 0,
        occurred_at=event.occurred_at,
        actor_id=event.actor_id,
        actor_name=event.actor_name,
        channel=event.channel.value,
        action=event.action,
        object_type=event.object_type,
        object_uid=event.object_uid,
        result=event.result.value,
        correlation_id=event.correlation_id,
        duration_ms=event.duration_ms,
        details=event.details,
    )


# ----------------------------------------------------------------------
# Configuración del servidor
# ----------------------------------------------------------------------
@router.get("/server-config", response_model=ServerConfigView)
async def get_server_config(
    _: AuthContext = Depends(get_auth),
    services: RequestServices = Depends(get_services),
) -> ServerConfigView:
    return _config_view(await services.config.get())


@router.put("/server-config/contact", response_model=ServerConfigView)
async def update_contact(
    payload: ContactUpdateRequest,
    request: Request,
    auth: AuthContext = Depends(require_superadmin),
    _: AuthContext = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> ServerConfigView:
    config = await services.config.update_contact(
        email=payload.contact_email,
        phone=payload.contact_phone,
        actor=auth.principal.name,
    )
    await audit(
        services,
        auth,
        action="server-config.contact.updated",
        correlation=correlation_id(request),
    )
    return _config_view(config)


# ----------------------------------------------------------------------
# Cuentas de servicio y credenciales
# ----------------------------------------------------------------------
@router.get("/service-accounts", response_model=list[ServiceAccountView])
async def list_service_accounts(
    _: AuthContext = Depends(require_permission(AdminPermission.IDENTITY_WRITE)),
    services: RequestServices = Depends(get_services),
) -> list[ServiceAccountView]:
    return [_account_view(item) for item in await services.identities.list_service_accounts()]


@router.post(
    "/service-accounts",
    response_model=ServiceAccountCreatedView,
    status_code=status.HTTP_201_CREATED,
)
async def create_service_account(
    payload: ServiceAccountCreate,
    request: Request,
    auth: AuthContext = Depends(require_permission(AdminPermission.IDENTITY_WRITE)),
    _: AuthContext = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> ServiceAccountCreatedView:
    account, secret = await services.identities.create_service_account(
        name=payload.name,
        role=payload.role,
        grants=[_grant_model(grant) for grant in payload.grants],
        well_scope=set(payload.well_scope) if payload.well_scope else None,
    )
    await audit(
        services,
        auth,
        action="service-account.created",
        correlation=correlation_id(request),
        object_type="service_account",
        object_uid=account.id,
        details={"name": account.name, "role": account.role.value},
    )
    return ServiceAccountCreatedView(
        account=_account_view(account), credential=CredentialView(secret=secret)
    )


@router.get("/service-accounts/{account_id}", response_model=ServiceAccountView)
async def get_service_account(
    account_id: str,
    _: AuthContext = Depends(require_permission(AdminPermission.IDENTITY_WRITE)),
    services: RequestServices = Depends(get_services),
) -> ServiceAccountView:
    return _account_view(await services.identities.get_service_account(account_id))


@router.patch("/service-accounts/{account_id}", response_model=ServiceAccountView)
async def update_service_account(
    account_id: str,
    payload: ServiceAccountUpdate,
    request: Request,
    auth: AuthContext = Depends(require_permission(AdminPermission.IDENTITY_WRITE)),
    _: AuthContext = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> ServiceAccountView:
    account = await services.identities.update_service_account(
        account_id,
        enabled=payload.enabled,
        grants=(
            [_grant_model(grant) for grant in payload.grants]
            if payload.grants is not None
            else None
        ),
        well_scope=set(payload.well_scope) if payload.well_scope is not None else None,
        role=payload.role,
    )
    await audit(
        services,
        auth,
        action="service-account.updated",
        correlation=correlation_id(request),
        object_type="service_account",
        object_uid=account.id,
        details={"enabled": account.enabled, "role": account.role.value},
    )
    return _account_view(account)


@router.post(
    "/service-accounts/{account_id}/rotate-credential",
    response_model=CredentialView,
)
async def rotate_credential(
    account_id: str,
    request: Request,
    auth: AuthContext = Depends(require_permission(AdminPermission.IDENTITY_WRITE)),
    _: AuthContext = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> CredentialView:
    secret = await services.identities.rotate_credential(account_id)
    await audit(
        services,
        auth,
        action="service-account.credential.rotated",
        correlation=correlation_id(request),
        object_type="service_account",
        object_uid=account_id,
    )
    return CredentialView(secret=secret)


@router.post(
    "/service-accounts/{account_id}/revoke-credential",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_credential(
    account_id: str,
    request: Request,
    auth: AuthContext = Depends(require_permission(AdminPermission.IDENTITY_WRITE)),
    _: AuthContext = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> None:
    await services.identities.revoke_credential(account_id)
    await audit(
        services,
        auth,
        action="service-account.credential.revoked",
        correlation=correlation_id(request),
        object_type="service_account",
        object_uid=account_id,
    )


# ----------------------------------------------------------------------
# Usuarios administrativos e invitaciones
# ----------------------------------------------------------------------
@router.get("/admin-users", response_model=list[UserView])
async def list_admin_users(
    _: AuthContext = Depends(require_permission(AdminPermission.IDENTITY_WRITE)),
    services: RequestServices = Depends(get_services),
) -> list[UserView]:
    return [user_view(user) for user in await services.identities.list_admin_users()]


@router.get("/admin-users/{user_id}", response_model=UserView)
async def get_admin_user(
    user_id: str,
    _: AuthContext = Depends(require_permission(AdminPermission.IDENTITY_WRITE)),
    services: RequestServices = Depends(get_services),
) -> UserView:
    return user_view(await services.identities.get_admin_user(user_id))


@router.patch("/admin-users/{user_id}", response_model=UserView)
async def update_admin_user(
    user_id: str,
    payload: AdminUserUpdate,
    request: Request,
    auth: AuthContext = Depends(require_recent_auth),
    _: AuthContext = Depends(require_permission(AdminPermission.IDENTITY_WRITE)),
    __: AuthContext = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> UserView:
    user = await services.identities.update_admin_user(
        user_id,
        enabled=payload.enabled,
        role=payload.role,
        permissions=set(payload.permissions) if payload.permissions is not None else None,
        display_name=payload.display_name,
    )
    await audit(
        services,
        auth,
        action="admin-user.updated",
        correlation=correlation_id(request),
        object_type="admin_user",
        object_uid=user.id,
        details={"enabled": user.enabled, "role": user.role.value},
    )
    return user_view(user)


@router.post(
    "/invitations",
    response_model=InvitationView,
    status_code=status.HTTP_201_CREATED,
)
async def create_invitation(
    payload: InvitationCreate,
    request: Request,
    auth: AuthContext = Depends(require_recent_auth),
    _: AuthContext = Depends(require_permission(AdminPermission.IDENTITY_WRITE)),
    __: AuthContext = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> InvitationView:
    invitation, token = await services.identities.create_invitation(
        email=payload.email,
        role=payload.role,
        created_by=auth.principal.id,
        permissions=set(payload.permissions) if payload.permissions else None,
    )
    await services.mail.enqueue_invitation(invitation.email, token)
    await audit(
        services,
        auth,
        action="invitation.created",
        correlation=correlation_id(request),
        object_type="invitation",
        object_uid=invitation.id,
        details={"email": invitation.email, "role": invitation.role.value},
    )
    settings = request.app.state.container.settings
    return InvitationView(
        id=invitation.id,
        email=invitation.email,
        role=invitation.role.value,
        expires_at=invitation.expires_at,
        token=token if settings.is_development else None,
    )


# ----------------------------------------------------------------------
# Roles, permisos y acceso efectivo
# ----------------------------------------------------------------------
@router.get("/roles", response_model=list[RoleView])
async def list_roles(
    _: AuthContext = Depends(require_permission(AdminPermission.ROLES_READ)),
) -> list[RoleView]:
    return [
        RoleView(name=role, permissions=sorted(permissions))
        for role, permissions in ROLE_PERMISSIONS.items()
    ]


@router.get("/permissions", response_model=list[PermissionView])
async def list_permissions(
    _: AuthContext = Depends(require_permission(AdminPermission.ROLES_READ)),
) -> list[PermissionView]:
    return [PermissionView(name=name) for name in sorted(ALL_ADMIN_PERMISSIONS)]


@router.get("/access", response_model=list[AccessView])
async def list_access(
    _: AuthContext = Depends(require_permission(AdminPermission.ROLES_READ)),
    services: RequestServices = Depends(get_services),
) -> list[AccessView]:
    result: list[AccessView] = []
    for user in await services.identities.list_admin_users():
        result.append(_admin_access(user))
    for account in await services.identities.list_service_accounts():
        result.append(
            AccessView(
                identity=account.name,
                kind="service",
                role=account.role.value,
                permissions=[],
                grants=[_grant_view(grant) for grant in account.grants],
            )
        )
    return result


def _admin_access(user: AdminUserRecord) -> AccessView:
    return AccessView(
        identity=user.email,
        kind="human",
        role=user.role.value,
        permissions=sorted(user.permissions),
        grants=[],
    )


# ----------------------------------------------------------------------
# Auditoría
# ----------------------------------------------------------------------
@router.get("/audit-events", response_model=AuditPage)
async def search_audit_events(
    _: AuthContext = Depends(require_permission(AdminPermission.AUDIT_READ)),
    services: RequestServices = Depends(get_services),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: int | None = Query(default=None, ge=1),
    actor: str | None = None,
    action: str | None = None,
    object_type: str | None = None,
    object_uid: str | None = None,
    result: str | None = None,
    correlation_id_value: str | None = Query(default=None, alias="correlation_id"),
    start: datetime | None = None,
    end: datetime | None = None,
) -> AuditPage:
    events, next_cursor = await services.audit.search(
        limit=limit,
        cursor=cursor,
        actor=actor,
        action=action,
        object_type=object_type,
        object_uid=object_uid,
        result=result,
        correlation_id=correlation_id_value,
        start=start,
        end=end,
    )
    return AuditPage(items=[_audit_view(event) for event in events], next_cursor=next_cursor)


@router.get("/mail-outbox/pending", response_model=MessageView)
async def mail_outbox_status(
    _: AuthContext = Depends(require_permission(AdminPermission.HEALTH_READ)),
    services: RequestServices = Depends(get_services),
) -> MessageView:
    pending = await services.repos.mail.pending_count()
    return MessageView(message=f"Correos pendientes: {pending}")
