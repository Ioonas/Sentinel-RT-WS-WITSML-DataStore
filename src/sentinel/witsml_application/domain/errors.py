"""Errores de aplicación WITSML con su código de retorno."""

from __future__ import annotations

from sentinel.shared.errors import AppError
from sentinel.witsml_application.domain.codes import WmlsCode, base_message


class WitsmlError(AppError):
    code = "witsml_error"
    http_status = 200  # WMLS comunica el error en Result, no en HTTP.

    def __init__(self, wmls_code: WmlsCode, message: str | None = None) -> None:
        self.wmls_code = int(wmls_code)
        super().__init__(message or base_message(int(wmls_code)))


def not_supported(object_type: str) -> WitsmlError:
    return WitsmlError(
        WmlsCode.OBJECT_NOT_SUPPORTED, f"El objeto '{object_type}' no está soportado."
    )


def denied() -> WitsmlError:
    return WitsmlError(WmlsCode.INSUFFICIENT_RIGHTS)


def missing_parent(object_type: str, uid: str) -> WitsmlError:
    return WitsmlError(
        WmlsCode.MISSING_PARENT, f"No existe el padre de {object_type} uid={uid}."
    )
