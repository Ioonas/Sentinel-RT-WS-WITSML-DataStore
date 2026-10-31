"""Utilidades compartidas sin dependencias de infraestructura."""

from sentinel.shared.clock import Clock, SystemClock
from sentinel.shared.errors import (
    AppError,
    AuthenticationError,
    ConflictError,
    NotFoundError,
    PermissionDenied,
    ServiceUnavailable,
    ValidationError,
)
from sentinel.shared.ids import IdGenerator, UuidGenerator

__all__ = [
    "AppError",
    "AuthenticationError",
    "Clock",
    "ConflictError",
    "IdGenerator",
    "NotFoundError",
    "PermissionDenied",
    "ServiceUnavailable",
    "SystemClock",
    "UuidGenerator",
    "ValidationError",
]
