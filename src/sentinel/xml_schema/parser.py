"""Parseo XML endurecido.

Requisitos del spec (§6): sin DTD, sin entidades externas y sin acceso a red ni
a archivos. lxml se configura explícitamente y además se rechaza cualquier
``DOCTYPE``/``ENTITY`` antes de parsear.
"""

from __future__ import annotations

import re

from lxml import etree

from sentinel.shared.errors import ValidationError

_DOCTYPE = re.compile(rb"<!\s*(DOCTYPE|ENTITY)", re.IGNORECASE)
_MAX_DOCUMENT_BYTES = 32 * 1024 * 1024


def _as_bytes(data: str | bytes) -> bytes:
    raw = data.encode("utf-8") if isinstance(data, str) else data
    if len(raw) > _MAX_DOCUMENT_BYTES:
        raise ValidationError("El documento XML excede el tamaño máximo permitido.")
    if _DOCTYPE.search(raw):
        raise ValidationError("El XML no puede contener DTD ni entidades.")
    return raw


def parse_xml(data: str | bytes) -> etree._Element:
    """Parsea un documento XML de forma segura."""
    raw = _as_bytes(data)
    parser = etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        dtd_validation=False,
        huge_tree=False,
        remove_blank_text=False,
        recover=False,
    )
    try:
        root = etree.fromstring(raw, parser=parser)
    except etree.XMLSyntaxError as exc:
        raise ValidationError(f"XML inválido: {exc}") from exc
    if root is None:
        raise ValidationError("XML vacío o inválido.")
    return root


def parse_fragment(data: str | bytes) -> etree._Element:
    """Parsea un fragmento (p. ej. ``XMLin`` ya validado) con las mismas reglas."""
    return parse_xml(data)


def serialize(element: etree._Element, *, declaration: bool = False) -> str:
    return etree.tostring(
        element,
        encoding="UTF-8",
        xml_declaration=declaration,
        pretty_print=False,
    ).decode("utf-8")
