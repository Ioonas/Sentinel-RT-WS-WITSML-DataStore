"""Aplicación FastAPI: WMLS SOAP + API administrativa + OpenAPI."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from sentinel import PRODUCT_NAME, __version__
from sentinel.admin_api.routes import auth, management, operations
from sentinel.bootstrap.container import Container
from sentinel.shared.errors import AppError
from sentinel.witsml_application.domain.codes import WmlsCode
from sentinel.witsml_application.domain.errors import WitsmlError
from sentinel.wmls_transport.router import router as wmls_router

logger = logging.getLogger(__name__)

ADMIN_PREFIX = "/admin-api/v1"

_WMLS_HTTP_STATUS: dict[int, int] = {
    int(WmlsCode.INSUFFICIENT_RIGHTS): 403,
    int(WmlsCode.OBJECT_NOT_EXIST): 404,
    int(WmlsCode.NOT_BOTTOM_LEVEL): 409,
    int(WmlsCode.MISSING_PARENT): 409,
    int(WmlsCode.DUPLICATE_OBJECT): 409,
    int(WmlsCode.MAX_DATA_EXCEEDED): 422,
}


def create_app(
    container: Container,
    *,
    lifespan: Any | None = None,
) -> FastAPI:
    app = FastAPI(
        title=PRODUCT_NAME,
        version=__version__,
        description=(
            "WITSML 1.4.1.1 Store API (SOAP) y API administrativa de "
            f"{PRODUCT_NAME}."
        ),
        openapi_url=f"{ADMIN_PREFIX}/openapi.json",
        docs_url=f"{ADMIN_PREFIX}/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.container = container

    origins = [
        origin.strip()
        for origin in container.settings.admin_origin.split(",")
        if origin.strip()
    ]
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Content-Type", "X-CSRF-Token", "X-Correlation-ID"],
            expose_headers=["X-Correlation-ID"],
        )

    app.include_router(wmls_router)
    app.include_router(auth.router, prefix=ADMIN_PREFIX)
    app.include_router(management.router, prefix=ADMIN_PREFIX)
    app.include_router(operations.router, prefix=ADMIN_PREFIX)

    @app.get("/health", tags=["Salud"])
    async def public_health(request: Request) -> dict[str, str]:
        """Disponibilidad general sin detalle de dependencias (§8)."""
        async with request.app.state.container.request() as services:
            return {"status": await services.health.overall()}

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        status_code = exc.http_status
        if isinstance(exc, WitsmlError):
            status_code = _WMLS_HTTP_STATUS.get(exc.wmls_code, 400)
        return JSONResponse(
            status_code=status_code,
            content={
                "error": exc.code,
                "message": exc.message,
                "details": exc.details,
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Error no controlado en la API administrativa")
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_error",
                "message": "Error interno del servidor.",
                "details": {},
            },
        )

    return app
