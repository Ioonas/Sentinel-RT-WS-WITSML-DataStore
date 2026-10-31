"""Namespaces oficiales de WITSML 1.4.1.1, SOAP 1.1 y WSDL.

El WSDL oficial ``witsmlStoreAPI_v1.4.1.1.wsdl`` usa RPC/encoded con:

* ``targetNamespace`` del documento WSDL: ``/wsdl/120``.
* namespace de los mensajes (envoltorio de operación y partes): ``/message/120``.
* prefijo de las acciones SOAP: ``/action/120/Store.<operación>``.

Los mensajes se construyen con ``MESSAGE_NS``; ``WSDL_NS`` queda reservado para
el documento WSDL. ``ACTION_NS`` se usa al publicar el contrato y al comparar
``SOAPAction``.
"""

from __future__ import annotations

WITSML_NS = "http://www.witsml.org/schemas/1series"
WITSML = f"{{{WITSML_NS}}}"
SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"
SOAP = f"{{{SOAP_NS}}}"
WSDL_NS = "http://www.witsml.org/wsdl/120"
WSDL = f"{{{WSDL_NS}}}"
MESSAGE_NS = "http://www.witsml.org/message/120"
MESSAGE = f"{{{MESSAGE_NS}}}"
ACTION_NS = "http://www.witsml.org/action/120"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
