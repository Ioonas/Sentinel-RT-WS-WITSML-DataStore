"""Publicación del WSDL.

Si el WSDL oficial de Energistics está instalado, se publica sin cambios salvo
``soap:address/location``. Si no, se genera un contrato RPC/encoded equivalente
para desarrollo y pruebas; la certificación exige el WSDL oficial (fase 0).
"""

from __future__ import annotations

import re
from pathlib import Path

from sentinel.xml_schema.namespaces import ACTION_NS, MESSAGE_NS, WSDL_NS

OFFICIAL_WSDL = Path("schemas") / "witsml" / "witsmlStoreAPI_v1.4.1.1.wsdl"

_OPERATIONS: dict[str, tuple[str, ...]] = {
    "WMLS_GetVersion": (),
    "WMLS_GetCap": ("OptionsIn",),
    "WMLS_GetBaseMsg": ("ReturnValueIn",),
    "WMLS_GetFromStore": ("WMLtypeIn", "QueryIn", "OptionsIn", "CapabilitiesIn"),
    "WMLS_AddToStore": ("WMLtypeIn", "XMLin", "OptionsIn", "CapabilitiesIn"),
    "WMLS_UpdateInStore": ("WMLtypeIn", "XMLin", "OptionsIn", "CapabilitiesIn"),
    "WMLS_DeleteFromStore": ("WMLtypeIn", "QueryIn", "OptionsIn", "CapabilitiesIn"),
}

_RESPONSE_PARTS: dict[str, tuple[str, ...]] = {
    "WMLS_GetVersion": ("Result",),
    "WMLS_GetCap": ("Result", "CapabilitiesOut", "SuppMsgOut"),
    "WMLS_GetBaseMsg": ("Result",),
    "WMLS_GetFromStore": ("Result", "XMLout", "SuppMsgOut"),
    "WMLS_AddToStore": ("Result", "SuppMsgOut"),
    "WMLS_UpdateInStore": ("Result", "SuppMsgOut"),
    "WMLS_DeleteFromStore": ("Result", "SuppMsgOut"),
}

_ADDRESS_PATTERN = re.compile(
    r"(<soap:address\b[^>]*\blocation\s*=\s*)(['\"])[^'\"]*\2"
)


def build_wsdl(public_base_url: str) -> str:
    official = _read_official()
    address = f"{public_base_url.rstrip('/')}/witsml"
    if official is not None:
        published, replacements = _ADDRESS_PATTERN.subn(
            lambda match: f"{match.group(1)}{match.group(2)}{address}{match.group(2)}",
            official,
        )
        if replacements != 1:
            raise RuntimeError(
                "El WSDL oficial no contiene exactamente un soap:address publicable."
            )
        return published
    return _generate(address)


def _read_official() -> str | None:
    for candidate in (
        Path(__file__).resolve().parents[3] / OFFICIAL_WSDL,
        Path.cwd() / OFFICIAL_WSDL,
    ):
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8")
    return None


def _generate(address: str) -> str:
    lines = [
        "<?xml version='1.0' encoding='UTF-8' ?>",
        (
            f"<definitions name='WMLS' targetNamespace='{WSDL_NS}' "
            f"xmlns:wsdlns='{WSDL_NS}'"
        ),
        "     xmlns:soap='http://schemas.xmlsoap.org/wsdl/soap/'",
        "     xmlns:xsd='http://www.w3.org/2001/XMLSchema'",
        "     xmlns='http://schemas.xmlsoap.org/wsdl/'>",
        "  <documentation>Contrato WITSML 1.4.1.1 generado por Sentinel.</documentation>",
    ]
    for operation, inputs in _OPERATIONS.items():
        lines.append(f"  <message name='Store.{operation}'>")
        for part in inputs:
            lines.append(f"     <part name='{part}' type='xsd:string' />")
        lines.append("  </message>")
        lines.append(f"  <message name='Store.{operation}Response'>")
        for part in _RESPONSE_PARTS[operation]:
            part_type = "xsd:string"
            if part == "Result" and operation not in (
                "WMLS_GetVersion",
                "WMLS_GetBaseMsg",
            ):
                part_type = "xsd:short"
            lines.append(f"     <part name='{part}' type='{part_type}' />")
        lines.append("  </message>")
    lines.append("  <portType name='StoreSoapPort'>")
    for operation in _OPERATIONS:
        lines.append(f"    <operation name='{operation}'>")
        lines.append(f"      <input message='wsdlns:Store.{operation}' />")
        lines.append(f"      <output message='wsdlns:Store.{operation}Response' />")
        lines.append("    </operation>")
    lines.append("  </portType>")
    lines.append(
        "  <binding name='StoreSoapBinding' type='wsdlns:StoreSoapPort'>"
    )
    lines.append(
        "    <soap:binding style='rpc' "
        "transport='http://schemas.xmlsoap.org/soap/http' />"
    )
    for operation in _OPERATIONS:
        lines.append(f"    <operation name='{operation}'>")
        lines.append(
            f"      <soap:operation soapAction='{ACTION_NS}/Store.{operation}' />"
        )
        for direction in ("input", "output"):
            lines.append(f"      <{direction}>")
            lines.append(
                f"        <soap:body use='encoded' namespace='{MESSAGE_NS}' "
                "encodingStyle='http://schemas.xmlsoap.org/soap/encoding/' />"
            )
            lines.append(f"      </{direction}>")
        lines.append("    </operation>")
    lines.append("  </binding>")
    lines.append("  <service name='WMLS'>")
    lines.append(
        "    <port name='StoreSoapPort' binding='wsdlns:StoreSoapBinding'>"
    )
    lines.append(f"      <soap:address location='{address}' />")
    lines.append("    </port>")
    lines.append("  </service>")
    lines.append("</definitions>")
    return "\n".join(lines)
