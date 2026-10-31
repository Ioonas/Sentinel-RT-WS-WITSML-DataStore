"""Validación XSD oficial 1.4.1.1.

Los esquemas distribuidos por Energistics se organizan en dos capas:

* ``witsml_v1.4.1.1_data/xsd_schemas``: esquema normativo de lectura.
* ``witsml_v1.4.1.1_data/generated_{write,update,delete}_schemas``: variantes
  derivadas que expresan las restricciones de cada operación (por ejemplo,
  campos obligatorios en alta y presencia parcial en actualización).

El validador compila el ``obj_<tipo>.xsd`` de la variante que corresponde a la
operación. Si el directorio oficial no está instalado, el bootstrap utiliza
``PermissiveSchemaValidator`` y la validación de esquema queda desactivada.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from lxml import etree

from sentinel.shared.errors import ValidationError
from sentinel.xml_schema.objects import OBJECT_SPECS

DEFAULT_SCHEMA_DIR = Path(__file__).resolve().parents[3] / "schemas" / "witsml" / "1.4.1.1"

_OPERATION_VARIANTS: dict[str, str] = {
    "add": "generated_write_schemas",
    "write": "generated_write_schemas",
    "update": "generated_update_schemas",
    "delete": "generated_delete_schemas",
    "read": "xsd_schemas",
}
_FALLBACK_VARIANTS = ("xsd_schemas", "generated_write_schemas", "generated_update_schemas")


class SchemaValidator(Protocol):
    @property
    def available(self) -> bool: ...

    def validate_document(
        self, object_type: str, document: etree._Element, *, operation: str = "write"
    ) -> None: ...


class LxmlXsdValidator:
    def __init__(self, schema_dir: Path | None = None) -> None:
        self._dir = schema_dir or DEFAULT_SCHEMA_DIR
        self._data_dir = self._resolve_data_dir()
        self._schemas: dict[tuple[str, str], etree.XMLSchema | None] = {}
        self._available = any(
            (self._data_dir / variant).is_dir()
            for variant in ("xsd_schemas", "generated_write_schemas")
        ) or any(self._dir.glob("obj_*.xsd"))

    @property
    def available(self) -> bool:
        return self._available

    def _resolve_data_dir(self) -> Path:
        nested = self._dir / "witsml_v1.4.1.1_data"
        if nested.is_dir():
            return nested
        return self._dir

    def validate_document(
        self, object_type: str, document: etree._Element, *, operation: str = "write"
    ) -> None:
        schema = self._schema(object_type, operation)
        if schema is None:
            return
        if not schema.validate(document):
            errors = "; ".join(
                f"línea {error.line}: {error.message}" for error in schema.error_log
            )
            raise ValidationError(f"El XML no cumple el XSD 1.4.1.1: {errors}")

    def _schema(self, object_type: str, operation: str) -> etree.XMLSchema | None:
        key = (object_type, operation)
        if key not in self._schemas:
            self._schemas[key] = self._compile_for(object_type, operation)
        return self._schemas[key]

    def _compile_for(self, object_type: str, operation: str) -> etree.XMLSchema | None:
        spec = OBJECT_SPECS.get(object_type)
        if spec is None:
            return None
        path = self._schema_path(object_type, operation)
        if path is None:
            return None
        return self._compile(path)

    def _schema_path(self, object_type: str, operation: str) -> Path | None:
        file_name = f"obj_{object_type}.xsd"
        variants = []
        primary = _OPERATION_VARIANTS.get(operation)
        if primary:
            variants.append(primary)
        for variant in _FALLBACK_VARIANTS:
            if variant not in variants:
                variants.append(variant)
        for variant in variants:
            candidate = self._data_dir / variant / file_name
            if candidate.is_file():
                return candidate
        # Estructura plana usada por instalaciones personalizadas/antiguas.
        spec = OBJECT_SPECS[object_type]
        for candidate in (
            self._dir / f"{spec.plural}.xsd",
            self._dir / f"{object_type}.xsd",
        ):
            if candidate.is_file():
                return candidate
        return None

    def _compile(self, path: Path) -> etree.XMLSchema:
        parser = etree.XMLParser(
            resolve_entities=False,
            no_network=True,
            load_dtd=False,
            dtd_validation=False,
            huge_tree=False,
        )
        try:
            document = etree.parse(str(path), parser=parser)
            return etree.XMLSchema(document)
        except (etree.XMLSchemaParseError, etree.XMLSyntaxError, OSError) as exc:
            raise ValidationError(
                f"No se pudo cargar el XSD oficial {path.name}: {exc}"
            ) from exc


class PermissiveSchemaValidator:
    """Validador para pruebas y para entornos sin XSD oficial instalado."""

    @property
    def available(self) -> bool:
        return False

    def validate_document(
        self, object_type: str, document: etree._Element, *, operation: str = "write"
    ) -> None:
        return None
