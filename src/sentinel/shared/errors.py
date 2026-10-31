"""Errores de dominio independientes del protocolo.

Los adaptadores traducen estos errores a códigos HTTP (administración) o a
códigos WMLS y ``SuppMsgOut`` (SOAP). El núcleo nunca conoce HTTP.
"""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Error base de dominio."""

    code: str = "error"
    http_status: int = 500

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ValidationError(AppError):
    code = "validation_error"
    http_status = 422


class NotFoundError(AppError):
    code = "not_found"
    http_status = 404


class ConflictError(AppError):
    code = "conflict"
    http_status = 409


class AuthenticationError(AppError):
    code = "authentication_failed"
    http_status = 401


class PermissionDenied(AppError):
    code = "permission_denied"
    http_status = 403


class ReauthenticationRequired(PermissionDenied):
    code = "reauth_required"


class RateLimited(AppError):
    code = "rate_limited"
    http_status = 429


class ServiceUnavailable(AppError):
    code = "service_unavailable"
    http_status = 503


class ConfigurationError(AppError):
    code = "configuration_error"
    http_status = 500
