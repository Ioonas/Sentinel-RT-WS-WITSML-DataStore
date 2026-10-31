"""Adaptador de entrada SOAP WMLS sobre FastAPI/Starlette."""

from __future__ import annotations

import base64
import binascii
import logging
import uuid

from fastapi import APIRouter, Request, Response
from fastapi.responses import PlainTextResponse

from sentinel.bootstrap.container import Container
from sentinel.shared.errors import ValidationError
from sentinel.wmls_transport.operations import execute
from sentinel.wmls_transport.soap import (
    SoapEnvelopeError,
    build_fault,
    build_response,
    parse_soap_request,
)
from sentinel.wmls_transport.wsdl import build_wsdl

logger = logging.getLogger(__name__)
router = APIRouter(tags=["WITSML Store API"])

SOAP_CONTENT_TYPES = (
    "text/xml",
    "application/soap+xml",
    "application/xml",
)


@router.get("/witsml", response_class=PlainTextResponse)
async def get_wsdl(request: Request) -> Response:
    container: Container = request.app.state.container
    return PlainTextResponse(
        build_wsdl(container.settings.public_base_url),
        media_type="text/xml",
    )


@router.post("/witsml")
async def wmls_endpoint(request: Request) -> Response:
    container: Container = request.app.state.container
    settings = container.settings

    if not _is_https(request, settings.require_https, settings.trust_forwarded_proto):
        return PlainTextResponse(
            "WMLS requiere HTTPS. El acceso por HTTP sin TLS está deshabilitado.",
            status_code=403,
        )

    content_type = (request.headers.get("content-type") or "").split(";")[0].strip()
    if content_type not in SOAP_CONTENT_TYPES:
        return PlainTextResponse(
            "Content-Type no soportado; se esperaba SOAP 1.1 XML.",
            status_code=415,
        )

    credentials = _basic_credentials(request.headers.get("authorization"))
    if credentials is None:
        return _unauthorized("Se requieren credenciales HTTP Basic.")

    correlation_id = request.headers.get("x-correlation-id") or str(uuid.uuid4())
    payload = await request.body()

    try:
        soap_request = parse_soap_request(payload, request.headers.get("soapaction"))
    except SoapEnvelopeError as exc:
        return _fault(str(exc), status_code=400)

    try:
        async with container.request() as services:
            principal = await services.identities.authenticate_service_account(
                *credentials
            )
            if principal is None:
                return _unauthorized("Credenciales inválidas o cuenta deshabilitada.")
            fields = await execute(
                services.witsml,
                principal,
                soap_request.operation,
                soap_request.parameters,
                correlation_id,
            )
    except ValidationError as exc:
        return _fault(str(exc), status_code=400)
    except Exception:  # noqa: BLE001 - se registra sin secretos
        logger.exception("Error no controlado en WMLS (correlación %s)", correlation_id)
        return _fault("Error interno del servidor WMLS.", status_code=500)

    response = build_response(soap_request.operation, fields)
    return Response(
        content=response,
        media_type="text/xml; charset=utf-8",
        headers={"X-Correlation-ID": correlation_id},
    )


def _is_https(request: Request, require_https: bool, trust_forwarded: bool) -> bool:
    if not require_https:
        return True
    if request.url.scheme == "https":
        return True
    if trust_forwarded:
        forwarded = request.headers.get("x-forwarded-proto", "")
        return forwarded.split(",")[0].strip().lower() == "https"
    return False


def _basic_credentials(header: str | None) -> tuple[str, str] | None:
    if not header or not header.lower().startswith("basic "):
        return None
    try:
        decoded = base64.b64decode(header[6:].strip(), validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return None
    if ":" not in decoded:
        return None
    username, password = decoded.split(":", 1)
    if not username or not password:
        return None
    return username, password


def _unauthorized(message: str) -> Response:
    return PlainTextResponse(
        message,
        status_code=401,
        headers={"WWW-Authenticate": 'Basic realm="Sentinel WITSML DataStore"'},
    )


def _fault(message: str, *, status_code: int) -> Response:
    return Response(
        content=build_fault(message),
        status_code=status_code,
        media_type="text/xml; charset=utf-8",
    )
