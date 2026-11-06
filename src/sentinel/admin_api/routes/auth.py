"""Sesión humana, primer arranque, invitaciones y recuperación de acceso."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status

from sentinel.admin_api.deps import (
    AuthContext,
    audit,
    clear_session_cookies,
    correlation_id,
    get_auth,
    get_services,
    rate_limit,
    require_csrf,
    set_session_cookies,
    user_view,
)
from sentinel.admin_api.schemas import (
    AcceptInvitationRequest,
    LoginRequest,
    MessageView,
    PasswordChangeRequest,
    ProfileSessionView,
    ReauthRequest,
    RecoveryRequest,
    ResetPasswordRequest,
    SessionView,
    SetupRequest,
    SetupStatusView,
    UserView,
)
from sentinel.audit_config.domain import AuditChannel, AuditResult
from sentinel.bootstrap.container import RequestServices
from sentinel.identity_access.domain import ALL_ADMIN_PERMISSIONS
from sentinel.identity_access.service import session_reference
from sentinel.shared.errors import AuthenticationError

router = APIRouter(tags=["Sesión administrativa"])


@router.get("/setup/status", response_model=SetupStatusView)
async def setup_status(
    services: RequestServices = Depends(get_services),
) -> SetupStatusView:
    """Estado público del primer arranque (no revela configuración)."""
    return SetupStatusView(setup_completed=await services.setup.status())


@router.post(
    "/setup",
    response_model=SessionView,
    status_code=status.HTTP_201_CREATED,
)
async def run_setup(
    payload: SetupRequest,
    request: Request,
    response: Response,
    services: RequestServices = Depends(get_services),
) -> SessionView:
    """Configura contacto y crea el primer superadministrador.

    Solo puede ejecutarse una vez; no existen credenciales predeterminadas.
    """
    rate_limit(request, "setup", limit=5)
    correlation = correlation_id(request)
    await services.setup.run(
        contact_email=payload.contact_email,
        contact_phone=payload.contact_phone,
        admin_email=payload.admin_email,
        admin_name=payload.admin_name,
        admin_password=payload.admin_password,
        correlation_id=correlation,
        server_name=payload.server_name,
        server_description=payload.server_description,
    )
    result = await services.identities.login(
        payload.admin_email, payload.admin_password
    )
    set_session_cookies(response, request, result.token, result.csrf_token)
    user = await services.identities.get_admin_user(result.principal.id)
    await services.audit.record(
        actor_id=result.principal.id,
        actor_name=result.principal.name,
        channel=AuditChannel.ADMIN,
        action="setup.session",
        correlation_id=correlation,
    )
    return SessionView(user=user_view(user), expires_at=result.expires_at)


@router.post("/auth/sessions", response_model=SessionView)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    services: RequestServices = Depends(get_services),
) -> SessionView:
    rate_limit(request, "login", limit=10)
    correlation = correlation_id(request)
    try:
        result = await services.identities.login(payload.email, payload.password)
    except AuthenticationError:
        await services.audit.record(
            actor_id=None,
            actor_name=payload.email.strip().lower(),
            channel=AuditChannel.ADMIN,
            action="auth.login",
            result=AuditResult.DENIED,
            correlation_id=correlation,
            details={"reason": "invalid_credentials"},
        )
        # Se confirma solo la auditoría para conservarla tras el 401.
        await services.session.commit()
        raise
    set_session_cookies(response, request, result.token, result.csrf_token)
    user = await services.identities.get_admin_user(result.principal.id)
    await services.audit.record(
        actor_id=result.principal.id,
        actor_name=result.principal.name,
        channel=AuditChannel.ADMIN,
        action="auth.login",
        correlation_id=correlation,
    )
    return SessionView(user=user_view(user), expires_at=result.expires_at)


@router.post("/auth/reauthentication", status_code=status.HTTP_204_NO_CONTENT)
async def reauthenticate(
    payload: ReauthRequest,
    request: Request,
    auth: AuthContext = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> Response:
    """Confirma la contraseña para renovar la ventana de operaciones sensibles."""
    rate_limit(request, "reauth", limit=10)
    correlation = correlation_id(request)
    try:
        await services.identities.reauthenticate(
            user_id=auth.principal.id,
            password=payload.password,
            token_hash=auth.session.token_hash,
        )
    except AuthenticationError:
        await audit(
            services,
            auth,
            action="auth.reauthentication.failed",
            correlation=correlation,
            result=AuditResult.DENIED,
        )
        raise
    await audit(services, auth, action="auth.reauthentication", correlation=correlation)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/auth/sessions", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    auth: AuthContext = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> Response:
    await services.identities.logout(auth.token)
    await audit(
        services,
        auth,
        action="auth.logout",
        correlation=correlation_id(request),
    )
    clear_session_cookies(response, request)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post("/auth/recovery", response_model=MessageView)
async def request_recovery(
    payload: RecoveryRequest,
    request: Request,
    services: RequestServices = Depends(get_services),
) -> MessageView:
    """Solicitud genérica: nunca confirma si la cuenta existe."""
    rate_limit(request, "recovery", limit=5)
    token, user = await services.identities.request_password_reset(payload.email)
    if token is not None and user is not None:
        await services.mail.enqueue_recovery(user.email, token)
        await services.audit.record(
            actor_id=user.id,
            actor_name=user.email,
            channel=AuditChannel.ADMIN,
            action="auth.recovery.requested",
            correlation_id=correlation_id(request),
        )
    return MessageView(
        message="Si la cuenta existe, recibirá un enlace de recuperación."
    )


@router.post("/auth/reset-password", response_model=MessageView)
async def reset_password(
    payload: ResetPasswordRequest,
    request: Request,
    services: RequestServices = Depends(get_services),
) -> MessageView:
    rate_limit(request, "reset-password", limit=5)
    await services.identities.reset_password(payload.token, payload.new_password)
    await services.audit.record(
        actor_id=None,
        actor_name="anonymous",
        channel=AuditChannel.ADMIN,
        action="auth.password.reset",
        correlation_id=correlation_id(request),
    )
    return MessageView(message="La contraseña fue restablecida.")


@router.post(
    "/invitations/accept",
    response_model=UserView,
    status_code=status.HTTP_201_CREATED,
)
async def accept_invitation(
    payload: AcceptInvitationRequest,
    request: Request,
    services: RequestServices = Depends(get_services),
) -> UserView:
    rate_limit(request, "accept-invitation", limit=5)
    user = await services.identities.accept_invitation(
        payload.token, payload.password, payload.display_name
    )
    await services.audit.record(
        actor_id=user.id,
        actor_name=user.email,
        channel=AuditChannel.ADMIN,
        action="invitation.accepted",
        correlation_id=correlation_id(request),
    )
    return user_view(user)


@router.get("/profile", response_model=SessionView)
async def get_profile(
    auth: AuthContext = Depends(get_auth),
    services: RequestServices = Depends(get_services),
) -> SessionView:
    user = await services.identities.get_admin_user(auth.principal.id)
    principal = auth.principal
    return SessionView(
        user=user_view(user),
        expires_at=auth.session.expires_at,
        linked_service_account=await services.identities.linked_account_name(user),
        permissions=sorted(ALL_ADMIN_PERMISSIONS)
        if principal.is_superadmin
        else sorted(principal.permissions),
        is_superadmin=principal.is_superadmin,
    )


async def _notify_sessions_closed(services: RequestServices, user_id: str, closed: int) -> None:
    user = await services.identities.get_admin_user(user_id)
    await services.mail.enqueue_sessions_closed(user.email, closed)


@router.get("/profile/sessions", response_model=list[ProfileSessionView])
async def list_profile_sessions(
    auth: AuthContext = Depends(get_auth),
    services: RequestServices = Depends(get_services),
) -> list[ProfileSessionView]:
    sessions = await services.identities.list_own_sessions(auth.principal.id)
    return [
        ProfileSessionView(
            reference=session_reference(item.token_hash),
            created_at=item.created_at,
            authenticated_at=item.authenticated_at,
            expires_at=item.expires_at,
            current=item.token_hash == auth.session.token_hash,
        )
        for item in sessions
    ]


@router.delete("/profile/sessions/{reference}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_profile_session(
    reference: str,
    request: Request,
    auth: AuthContext = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> Response:
    await services.identities.revoke_own_session(
        user_id=auth.principal.id,
        reference=reference,
        current_token_hash=auth.session.token_hash,
    )
    await audit(
        services,
        auth,
        action="profile.session.revoked",
        correlation=correlation_id(request),
        object_type="session",
        object_uid=reference,
    )
    await _notify_sessions_closed(services, auth.principal.id, 1)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/profile/sessions/revoke-others", response_model=MessageView)
async def revoke_other_profile_sessions(
    request: Request,
    auth: AuthContext = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> MessageView:
    closed = await services.identities.revoke_other_own_sessions(
        user_id=auth.principal.id, current_token_hash=auth.session.token_hash
    )
    await audit(
        services,
        auth,
        action="profile.sessions.revoked_others",
        correlation=correlation_id(request),
        details={"closed": closed},
    )
    if closed:
        await _notify_sessions_closed(services, auth.principal.id, closed)
    return MessageView(message=f"Se cerraron {closed} sesión(es) adicional(es).")


@router.post("/profile/password", response_model=MessageView)
async def change_own_password(
    payload: PasswordChangeRequest,
    request: Request,
    auth: AuthContext = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> MessageView:
    await services.identities.change_password(
        auth.principal.id, payload.current_password, payload.new_password
    )
    await audit(
        services,
        auth,
        action="profile.password.changed",
        correlation=correlation_id(request),
    )
    return MessageView(
        message="Contraseña actualizada. Inicie sesión nuevamente con la nueva contraseña."
    )


@router.delete("/profile/session", status_code=status.HTTP_204_NO_CONTENT)
async def logout_profile(
    request: Request,
    response: Response,
    auth: AuthContext = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> Response:
    await services.identities.logout(auth.token)
    await audit(
        services,
        auth,
        action="auth.logout",
        correlation=correlation_id(request),
    )
    clear_session_cookies(response, request)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
