"""Traducción de operaciones WMLS a casos de uso del núcleo."""

from __future__ import annotations

from sentinel import SCHEMA_VERSION
from sentinel.identity_access.domain import Principal
from sentinel.shared.errors import ValidationError
from sentinel.witsml_application.domain.codes import WmlsCode
from sentinel.witsml_application.domain.errors import WitsmlError
from sentinel.witsml_application.service import WitsmlStoreService
from sentinel.xml_schema.documents import option_value

SUPPORTED_OPERATIONS = frozenset(
    {
        "WMLS_GetVersion",
        "WMLS_GetCap",
        "WMLS_GetBaseMsg",
        "WMLS_GetFromStore",
        "WMLS_AddToStore",
        "WMLS_UpdateInStore",
        "WMLS_DeleteFromStore",
    }
)


async def execute(
    service: WitsmlStoreService,
    principal: Principal,
    operation: str,
    parameters: dict[str, str],
    correlation_id: str,
) -> dict[str, str | int]:
    try:
        return await _execute(service, principal, operation, parameters, correlation_id)
    except WitsmlError as exc:
        return _error_fields(operation, exc.wmls_code, exc.message)
    except ValidationError as exc:
        code = (
            WmlsCode.QUERY_TEMPLATE_NONCONFORMING
            if operation == "WMLS_GetFromStore"
            else WmlsCode.INPUT_TEMPLATE_NONCONFORMING
        )
        return _error_fields(operation, int(code), exc.message)


async def _execute(
    service: WitsmlStoreService,
    principal: Principal,
    operation: str,
    parameters: dict[str, str],
    correlation_id: str,
) -> dict[str, str | int]:
    if operation == "WMLS_GetVersion":
        return {"Result": await service.get_version()}

    if operation == "WMLS_GetCap":
        _validate_data_version(parameters.get("OptionsIn", ""))
        return {
            "CapabilitiesOut": await service.get_capabilities(),
            "SuppMsgOut": "",
            "Result": int(WmlsCode.SUCCESS),
        }

    if operation == "WMLS_GetBaseMsg":
        raw = (
            parameters.get("ReturnValueIn")
            or parameters.get("ErrorCodeIn")
            or ""
        ).strip()
        if not raw:
            return _error_fields(
                operation, int(WmlsCode.INVALID_RETURN_VALUE), None
            )
        try:
            code = int(raw)
        except ValueError:
            return _error_fields(
                operation, int(WmlsCode.INVALID_RETURN_VALUE), None
            )
        return {"Result": await service.get_base_message(code)}

    _validate_data_version(parameters.get("OptionsIn", ""))
    object_type = (parameters.get("WMLtypeIn") or "").strip()
    if not object_type:
        return _error_fields(operation, int(WmlsCode.MISSING_WMLTYPE), None)

    if operation == "WMLS_GetFromStore":
        query = parameters.get("QueryIn") or ""
        if not query.strip():
            return _error_fields(operation, int(WmlsCode.MISSING_INPUT_TEMPLATE), None)
        result = await service.get_from_store(
            principal,
            object_type=object_type,
            query_xml=query,
            options_xml=parameters.get("OptionsIn"),
            correlation_id=correlation_id,
        )
        return {
            "XMLout": result.xml_out or "",
            "SuppMsgOut": result.supp_msg or "",
            "Result": result.code,
        }

    if operation == "WMLS_AddToStore":
        xml_in = parameters.get("XMLin") or ""
        if not xml_in.strip():
            return _error_fields(operation, int(WmlsCode.MISSING_INPUT_TEMPLATE), None)
        result = await service.add_to_store(
            principal,
            object_type=object_type,
            xml_in=xml_in,
            options_xml=parameters.get("OptionsIn"),
            correlation_id=correlation_id,
        )
        return {"SuppMsgOut": result.supp_msg or "", "Result": result.code}

    if operation == "WMLS_UpdateInStore":
        xml_in = parameters.get("XMLin") or ""
        if not xml_in.strip():
            return _error_fields(operation, int(WmlsCode.MISSING_INPUT_TEMPLATE), None)
        result = await service.update_in_store(
            principal,
            object_type=object_type,
            xml_in=xml_in,
            options_xml=parameters.get("OptionsIn"),
            correlation_id=correlation_id,
        )
        return {"SuppMsgOut": result.supp_msg or "", "Result": result.code}

    if operation == "WMLS_DeleteFromStore":
        query = parameters.get("QueryIn") or ""
        if not query.strip():
            return _error_fields(operation, int(WmlsCode.MISSING_INPUT_TEMPLATE), None)
        result = await service.delete_from_store(
            principal,
            object_type=object_type,
            query_xml=query,
            options_xml=parameters.get("OptionsIn"),
            correlation_id=correlation_id,
        )
        return {"SuppMsgOut": result.supp_msg or "", "Result": result.code}

    raise WitsmlError(WmlsCode.QUERY_NOT_SUPPORTED, f"Operación no soportada: {operation}")


def _validate_data_version(options: str) -> None:
    normalized = _normalize_version(option_value(options, "dataVersion"))
    if normalized is None:
        return
    if normalized != SCHEMA_VERSION:
        raise WitsmlError(
            WmlsCode.DATA_VERSION_NOT_SUPPORTED,
            f"dataVersion no soportado: {normalized}.",
        )


def _normalize_version(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _error_fields(
    operation: str, code: int, message: str | None
) -> dict[str, str | int]:
    from sentinel.witsml_application.domain.codes import base_message

    text = message or base_message(code)
    fields: dict[str, str | int] = {"Result": code}
    if operation == "WMLS_GetFromStore":
        fields["XMLout"] = ""
        fields["SuppMsgOut"] = text
    elif operation in ("WMLS_AddToStore", "WMLS_UpdateInStore", "WMLS_DeleteFromStore"):
        fields["SuppMsgOut"] = text
    else:
        fields["Result"] = code
    return fields
