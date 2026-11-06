"""Inventario WITSML, borrado administrativo y salud operativa."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from sentinel.admin_api.deps import (
    AuthContext,
    audit,
    correlation_id,
    get_services,
    require_csrf,
    require_permission,
    require_recent_auth,
)
from sentinel.admin_api.schemas import (
    DependencyHealthView,
    HealthView,
    MessageView,
    ObjectCreateRequest,
    ObjectDeleteRequest,
    ObjectView,
)
from sentinel.bootstrap.container import RequestServices
from sentinel.identity_access.domain import AdminPermission
from sentinel.shared.errors import ConflictError, ValidationError
from sentinel.witsml_application.domain.codes import WmlsCode
from sentinel.witsml_application.domain.errors import WitsmlError
from sentinel.witsml_application.inventory import ObjectSummary

router = APIRouter(tags=["Operación"])


def _object_view(item: ObjectSummary) -> ObjectView:
    return ObjectView(
        object_type=item.object_type,
        uid=item.uid,
        uid_well=item.uid_well,
        uid_wellbore=item.uid_wellbore,
        name=item.name,
        created_at=item.created_at,
        changed_at=item.changed_at,
        growing=item.growing,
    )


@router.get("/objects", response_model=list[ObjectView])
async def search_objects(
    auth: AuthContext = Depends(require_permission(AdminPermission.OBJECTS_READ)),
    services: RequestServices = Depends(get_services),
    object_type: str = Query(alias="objectType"),
    uid_well: str | None = None,
    uid_wellbore: str | None = None,
    name: str | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[ObjectView]:
    items = await services.inventory.search(
        object_type,
        uid_well=uid_well,
        uid_wellbore=uid_wellbore,
        name=name,
        allowed_wells=auth.principal.readable_wells,
        limit=limit,
    )
    return [_object_view(item) for item in items]


async def _create_object(
    services: RequestServices,
    auth: AuthContext,
    request: Request,
    *,
    object_type: str,
    payload: ObjectCreateRequest,
) -> ObjectView:
    try:
        uid = await services.witsml.create_object_as_admin(
            object_type, uid=payload.uid, uid_well=payload.uid_well, name=payload.name
        )
    except WitsmlError as exc:
        if exc.wmls_code == int(WmlsCode.DUPLICATE_OBJECT):
            raise ConflictError("Ya existe un objeto con ese uid.") from exc
        raise ValidationError(str(exc)) from exc
    await audit(
        services,
        auth,
        action="object.created",
        correlation=correlation_id(request),
        object_type=object_type,
        object_uid=uid,
        details={"uid_well": payload.uid_well, "name": payload.name},
    )
    item = await services.inventory.get(
        object_type, uid, uid_well=payload.uid_well, uid_wellbore=None
    )
    return _object_view(item)


@router.post("/objects/well", response_model=ObjectView, status_code=201)
async def create_well(
    payload: ObjectCreateRequest,
    request: Request,
    auth: AuthContext = Depends(require_recent_auth),
    _: AuthContext = Depends(require_permission(AdminPermission.OBJECTS_WRITE)),
    __: AuthContext = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> ObjectView:
    if payload.uid_well:
        raise ValidationError("Un pozo no admite uid_well; use el alta de pozo lateral.")
    return await _create_object(
        services, auth, request, object_type="well", payload=payload
    )


@router.post("/objects/wellbore", response_model=ObjectView, status_code=201)
async def create_wellbore(
    payload: ObjectCreateRequest,
    request: Request,
    auth: AuthContext = Depends(require_recent_auth),
    _: AuthContext = Depends(require_permission(AdminPermission.OBJECTS_WRITE)),
    __: AuthContext = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
) -> ObjectView:
    if not payload.uid_well:
        raise ValidationError("Indique el uid del pozo al que pertenece el pozo lateral.")
    return await _create_object(
        services, auth, request, object_type="wellbore", payload=payload
    )


@router.get("/objects/{object_type}/{uid}", response_model=ObjectView)
async def get_object(
    object_type: str,
    uid: str,
    _: AuthContext = Depends(require_permission(AdminPermission.OBJECTS_READ)),
    services: RequestServices = Depends(get_services),
    uid_well: str | None = None,
    uid_wellbore: str | None = None,
) -> ObjectView:
    item = await services.inventory.get(
        object_type, uid, uid_well=uid_well, uid_wellbore=uid_wellbore
    )
    return _object_view(item)


@router.get("/objects/{object_type}/{uid}/dependencies", response_model=list[str])
async def get_object_dependencies(
    object_type: str,
    uid: str,
    _: AuthContext = Depends(require_permission(AdminPermission.OBJECTS_READ)),
    services: RequestServices = Depends(get_services),
    uid_well: str | None = None,
    uid_wellbore: str | None = None,
) -> list[str]:
    return await services.inventory.dependencies(
        object_type, uid, uid_well=uid_well, uid_wellbore=uid_wellbore
    )


@router.post("/objects/{object_type}/{uid}/delete", response_model=MessageView)
async def delete_object(
    object_type: str,
    uid: str,
    payload: ObjectDeleteRequest,
    request: Request,
    auth: AuthContext = Depends(require_recent_auth),
    _: AuthContext = Depends(require_permission(AdminPermission.OBJECTS_DELETE)),
    __: AuthContext = Depends(require_csrf),
    services: RequestServices = Depends(get_services),
    uid_well: str | None = None,
    uid_wellbore: str | None = None,
) -> MessageView:
    if payload.confirmation.strip() != uid:
        raise ValidationError(
            "La confirmación debe coincidir exactamente con el uid del objeto."
        )
    await services.inventory.delete(
        object_type,
        uid,
        uid_well=uid_well,
        uid_wellbore=uid_wellbore,
        actor=auth.principal.name,
    )
    await audit(
        services,
        auth,
        action="object.deleted",
        correlation=correlation_id(request),
        object_type=object_type,
        object_uid=uid,
        details={"reason": payload.reason},
    )
    return MessageView(message="Objeto eliminado y registrado en ChangeLog.")


# ----------------------------------------------------------------------
# Salud
# ----------------------------------------------------------------------
@router.get("/health", response_model=HealthView)
async def health(services: RequestServices = Depends(get_services)) -> HealthView:
    return HealthView(status=await services.health.overall())


@router.get("/health/ready", response_model=HealthView)
async def health_ready(
    _: AuthContext = Depends(require_permission(AdminPermission.HEALTH_READ)),
    services: RequestServices = Depends(get_services),
) -> HealthView:
    return HealthView(status="ready" if await services.health.ready() else "not_ready")


@router.get("/health/dependencies", response_model=DependencyHealthView)
async def health_dependencies(
    _: AuthContext = Depends(require_permission(AdminPermission.HEALTH_READ)),
    services: RequestServices = Depends(get_services),
) -> DependencyHealthView:
    dependencies = await services.health.dependencies()
    return DependencyHealthView(
        status=await services.health.overall(), dependencies=dependencies
    )
