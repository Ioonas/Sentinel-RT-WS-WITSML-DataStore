"""Dependencias de la API administrativa: sesión, CSRF y permisos."""

from __future__ import annotations

import hmac
import time
import uuid
from collections import defaultdict, deque
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import timedelta

from fastapi import Depends, Request, Response

from sentinel.admin_api.schemas import UserView
from sentinel.audit_config.domain import AuditChannel, AuditResult
from sentinel.bootstrap.container import RequestServices
from sentinel.identity_access.domain import AdminPermission, Principal
from sentinel.identity_access.ports import AdminUserRecord, SessionRecord
from sentinel.identity_access.service import REAUTH_WINDOW
from sentinel.shared.errors import (
    AuthenticationError,
    PermissionDenied,
    RateLimited,
    ReauthenticationRequired,
)


@dataclass(frozen=True)
class AuthContext:
    principal: Principal
    session: SessionRecord
    token: str


async def get_services(request: Request) -> AsyncIterator[RequestServices]:
    container = request.app.state.container
    async with container.request() as services:
        yield services


async def get_auth(
    request: Request, services: RequestServices = Depends(get_services)
) -> AuthContext:
    settings = request.app.state.container.settings
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise AuthenticationError("Se requiere una sesión administrativa.")
    resolved = await services.identities.resolve_session(token)
    if resolved is None:
        raise AuthenticationError("La sesión es inválida o ha expirado.")
    principal, session = resolved
    return AuthContext(principal=principal, session=session, token=token)


async def require_csrf(
    request: Request, auth: AuthContext = Depends(get_auth)
) -> AuthContext:
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return auth
    settings = request.app.state.container.settings
    header = request.headers.get("x-csrf-token") or ""
    cookie = request.cookies.get(settings.csrf_cookie_name) or ""
    expected = auth.session.csrf_token
    if not (
        header
        and cookie
        and hmac.compare_digest(header, expected)
        and hmac.compare_digest(cookie, expected)
    ):
        raise PermissionDenied("Token CSRF ausente o inválido.")
    return auth


def require_permission(permission: AdminPermission):
    async def dependency(auth: AuthContext = Depends(get_auth)) -> AuthContext:
        if not auth.principal.has(permission):
            raise PermissionDenied("No tiene permiso para esta operación.")
        return auth

    return dependency


def require_superadmin(auth: AuthContext = Depends(get_auth)) -> AuthContext:
    if not auth.principal.is_superadmin:
        raise PermissionDenied("Requiere superadministrador.")
    return auth


def require_recent_auth(auth: AuthContext = Depends(get_auth)) -> AuthContext:
    from datetime import UTC, datetime

    from sentinel.bootstrap.container import Container  # noqa: F401

    now = datetime.now(UTC)
    if now - auth.session.authenticated_at > REAUTH_WINDOW:
        raise ReauthenticationRequired(
            "La operación requiere reautenticación reciente."
        )
    return auth


def correlation_id(request: Request) -> str:
    return request.headers.get("x-correlation-id") or str(uuid.uuid4())


def user_view(user: AdminUserRecord) -> UserView:
    return UserView(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=user.role.value,
        permissions=sorted(user.permissions),
        enabled=user.enabled,
        must_change_password=user.must_change_password,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )


def set_session_cookies(
    response: Response, request: Request, token: str, csrf: str
) -> None:
    settings = request.app.state.container.settings
    max_age = int(timedelta(hours=12).total_seconds())
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        settings.csrf_cookie_name,
        csrf,
        max_age=max_age,
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookies(response: Response, request: Request) -> None:
    settings = request.app.state.container.settings
    response.delete_cookie(settings.session_cookie_name, path="/")
    response.delete_cookie(settings.csrf_cookie_name, path="/")


async def audit(
    services: RequestServices,
    auth: AuthContext,
    *,
    action: str,
    correlation: str,
    result: AuditResult = AuditResult.SUCCESS,
    object_type: str | None = None,
    object_uid: str | None = None,
    details: dict[str, object] | None = None,
) -> None:
    await services.audit.record(
        actor_id=auth.principal.id,
        actor_name=auth.principal.name,
        channel=AuditChannel.ADMIN,
        action=action,
        result=result,
        correlation_id=correlation,
        object_type=object_type,
        object_uid=object_uid,
        details=details or {},
    )


_attempts: dict[str, deque[float]] = defaultdict(deque)


def rate_limit(request: Request, bucket: str, *, limit: int = 10, window: int = 60) -> None:
    settings = request.app.state.container.settings
    effective_limit = 100 if settings.is_development else limit
    client = request.client.host if request.client else "unknown"
    key = f"{bucket}:{client}"
    now = time.monotonic()
    attempts = _attempts[key]
    while attempts and now - attempts[0] > window:
        attempts.popleft()
    if len(attempts) >= effective_limit:
        raise RateLimited("Demasiados intentos. Intente más tarde.")
    attempts.append(now)
