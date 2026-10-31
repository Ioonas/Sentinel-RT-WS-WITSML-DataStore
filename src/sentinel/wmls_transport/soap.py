"""SOAP 1.1 acotado: envelope, operación y respuesta.

El WSDL oficial de WITSML 1.4.1.1 define un binding RPC/encoded. Las operaciones
y sus partes viajan en ``http://www.witsml.org/message/120`` y el ``SOAPAction``
es ``http://www.witsml.org/action/120/Store.<operación>``. Este módulo acepta
también el formato histórico ``<ns>/<operación>`` para no romper clientes
existentes.

No implementa WS-Security ni MTOM; el perfil certificable usa Basic Auth sobre
HTTPS y XML en texto.
"""

from __future__ import annotations

from dataclasses import dataclass

from lxml import etree

from sentinel.shared.errors import ValidationError
from sentinel.xml_schema.namespaces import MESSAGE, MESSAGE_NS, SOAP, SOAP_NS
from sentinel.xml_schema.parser import parse_xml


class SoapEnvelopeError(ValidationError):
    code = "soap_envelope_error"
    http_status = 400


@dataclass(frozen=True)
class SoapRequest:
    operation: str
    parameters: dict[str, str]
    soap_action: str | None = None


def parse_soap_request(payload: bytes, soap_action: str | None = None) -> SoapRequest:
    root = parse_xml(payload)
    if etree.QName(root).localname != "Envelope":
        raise SoapEnvelopeError("El documento no es un Envelope SOAP 1.1.")
    body = root.find(f"{SOAP}Body")
    if body is None:
        raise SoapEnvelopeError("El Envelope no contiene Body.")
    children = [child for child in body if isinstance(child.tag, str)]
    if len(children) != 1:
        raise SoapEnvelopeError("El Body debe contener exactamente una operación.")
    operation_element = children[0]
    operation = etree.QName(operation_element).localname
    parameters: dict[str, str] = {}
    for child in operation_element:
        if not isinstance(child.tag, str):
            continue
        parameters[etree.QName(child).localname] = child.text or ""
    action = _normalize_action(soap_action)
    if action and action != operation:
        raise SoapEnvelopeError(
            f"SOAPAction '{action}' no coincide con la operación '{operation}'."
        )
    return SoapRequest(operation=operation, parameters=parameters, soap_action=action)


def _normalize_action(value: str | None) -> str | None:
    """Reduce un ``SOAPAction`` al nombre WMLS de la operación.

    Acepta ``.../Store.WMLS_GetCap``, ``.../WMLS_GetCap`` y ``WMLS_GetCap``.
    """
    if not value:
        return None
    cleaned = value.strip().strip('"').strip("'").strip()
    if not cleaned:
        return None
    operation = cleaned.rsplit("/", 1)[-1].strip()
    if operation.startswith("Store."):
        operation = operation[len("Store.") :]
    return operation or None


def build_response(operation: str, fields: dict[str, str | int | None]) -> bytes:
    envelope = etree.Element(
        f"{SOAP}Envelope", nsmap={"soapenv": SOAP_NS, "witsml": MESSAGE_NS}
    )
    body = etree.SubElement(envelope, f"{SOAP}Body")
    response = etree.SubElement(body, f"{MESSAGE}{operation}Response")
    for name, value in fields.items():
        element = etree.SubElement(response, f"{MESSAGE}{name}")
        element.text = "" if value is None else str(value)
    return etree.tostring(envelope, encoding="UTF-8", xml_declaration=True)


def build_fault(message: str, *, code: str = "soapenv:Client") -> bytes:
    envelope = etree.Element(f"{SOAP}Envelope", nsmap={"soapenv": SOAP_NS})
    body = etree.SubElement(envelope, f"{SOAP}Body")
    fault = etree.SubElement(body, f"{SOAP}Fault")
    etree.SubElement(fault, "faultcode").text = code
    etree.SubElement(fault, "faultstring").text = message
    return etree.tostring(envelope, encoding="UTF-8", xml_declaration=True)
