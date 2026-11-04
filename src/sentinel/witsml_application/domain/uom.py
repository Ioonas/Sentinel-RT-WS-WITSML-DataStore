"""Validación semántica del diccionario de unidades WITSML 1.4.1.1.

La API 1.4.1 (§6.4.4.2 para ``AddToStore`` y §6.7.4.3 para ``UpdateInStore``)
exige que todo dato de medida declare ``uom`` y que su valor coincida con un
atributo ``annotation`` del archivo ``witsmlUnitDict.xml``. El XSD oficial ya
declara ``uom`` como obligatorio, pero su enumeración es por clase de cantidad y
el error se reportaría como XML no conforme. Este validador aplica las reglas
semánticas antes del XSD para devolver ``-443`` (unidad no reconocida) o
``-453`` (unidad omitida).

El índice de tipos se construye a partir de los XSD oficiales: recorre el
árbol XML siguiendo el tipo declarado de cada elemento, de modo que un mismo
nombre (por ejemplo ``value``) solo se considera medida cuando el esquema le
asigna un tipo de medida. Los elementos cuya declaración no puede resolverse
—``customData`` usa ``xsd:any``— conservan la validación de ``uom`` si el
atributo está presente, pero no se marcan como medidas.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

from sentinel.witsml_application.domain.codes import WmlsCode, base_message
from sentinel.witsml_application.domain.errors import WitsmlError
from sentinel.xml_schema.xsd import DEFAULT_SCHEMA_DIR

_XS = "{http://www.w3.org/2001/XMLSchema}"
_UNIT_DICTIONARY = Path("ancillary") / "witsmlUnitDict.xml"
_TYPE_DIRECTORIES = ("generated_write_schemas", "xsd_schemas")


@dataclass
class _TypeIndex:
    """Declaraciones XSD necesarias para resolver el tipo de cada elemento."""

    complex_types: dict[str, etree._Element]
    groups: dict[str, etree._Element]
    elements: dict[str, etree._Element]
    measure_types: frozenset[str]
    _children: dict[str, dict[str, frozenset[str]]] = field(default_factory=dict)

    def global_type(self, name: str) -> str | None:
        declaration = self.elements.get(name)
        if declaration is None:
            return None
        return _local_type(declaration.get("type"))

    def child_types(self, type_name: str | None) -> dict[str, frozenset[str]]:
        if not type_name:
            return {}
        cached = self._children.get(type_name)
        if cached is None:
            cached = {
                name: frozenset(types)
                for name, types in self._collect(type_name, frozenset()).items()
            }
            self._children[type_name] = cached
        return cached

    def _collect(
        self, type_name: str, seen: frozenset[str]
    ) -> dict[str, set[str]]:
        if type_name in seen:
            return {}
        seen = seen | {type_name}
        node = self.complex_types.get(type_name)
        if node is None:
            return {}
        result: dict[str, set[str]] = {}
        complex_content = node.find(f"{_XS}complexContent")
        if complex_content is not None:
            extension = complex_content.find(f"{_XS}extension")
            if extension is not None:
                base = _local_type(extension.get("base"))
                if base:
                    for name, types in self._collect(base, seen).items():
                        result.setdefault(name, set()).update(types)
                for name, declared in self._declarations(extension):
                    if declared:
                        result.setdefault(name, set()).add(declared)
            return result
        for name, declared in self._declarations(node):
            if declared:
                result.setdefault(name, set()).add(declared)
        return result

    def _declarations(
        self, container: etree._Element
    ) -> Iterator[tuple[str, str | None]]:
        for child in container:
            if not isinstance(child.tag, str):
                continue
            tag = etree.QName(child).localname
            if tag in ("sequence", "choice", "all"):
                yield from self._declarations(child)
            elif tag == "group":
                group = self.groups.get(_local_type(child.get("ref")) or "")
                if group is None:
                    continue
                for content_tag in ("sequence", "choice", "all"):
                    content = group.find(f"{_XS}{content_tag}")
                    if content is not None:
                        yield from self._declarations(content)
            elif tag == "element":
                name = child.get("name")
                declared = _local_type(child.get("type"))
                reference = _local_type(child.get("ref"))
                if reference:
                    target = self.elements.get(reference)
                    if target is not None:
                        name = name or target.get("name")
                        declared = declared or _local_type(target.get("type"))
                if name:
                    yield name, declared


class UomValidator:
    """Valida ``uom`` contra ``witsmlUnitDict.xml`` y detecta medidas sin unidad."""

    def __init__(self, schema_dir: Path | None = None) -> None:
        self._schema_dir = schema_dir or DEFAULT_SCHEMA_DIR
        self._annotations: frozenset[str] | None = None
        self._index: _TypeIndex | None = None

    @property
    def available(self) -> bool:
        return self._unit_dictionary_path().is_file()

    def validate(self, document: etree._Element) -> None:
        """Valida todos los ``uom`` de ``document``.

        Devuelve ``-443`` si un valor no está en el diccionario y ``-453`` si
        una medida no declara ``uom``. La primera violación encontrada en el
        recorrido determina el código, igual que hace el XSD con el primer
        error de esquema.
        """
        if not self.available:
            return
        annotations = self._load_annotations()
        index = self._load_index()
        root_name = etree.QName(document).localname
        self._visit(
            document,
            index.global_type(root_name),
            index,
            annotations,
            (root_name,),
        )

    def _visit(
        self,
        element: etree._Element,
        type_name: str | None,
        index: _TypeIndex,
        annotations: frozenset[str],
        path: tuple[str, ...],
    ) -> None:
        children = index.child_types(type_name)
        for child in element:
            if not isinstance(child.tag, str):
                continue
            name = etree.QName(child).localname
            child_path = path + (name,)
            uom = child.get("uom")
            if uom is not None:
                if not uom.strip():
                    raise WitsmlError(
                        WmlsCode.MISSING_UNIT_FOR_MEASURE,
                        f"{base_message(int(WmlsCode.MISSING_UNIT_FOR_MEASURE))} "
                        f"Element '/{'/'.join(child_path)}' has an empty uom.",
                    )
                if uom not in annotations:
                    raise WitsmlError(
                        WmlsCode.INVALID_UOM,
                        f"{base_message(int(WmlsCode.INVALID_UOM))} "
                        f"Value '{uom}' on '/{'/'.join(child_path)}' is not in the "
                        "Units Dictionary.",
                    )
            child_type = _choose_type(children.get(name), index.measure_types)
            if (
                child_type is not None
                and child_type in index.measure_types
                and uom is None
            ):
                raise WitsmlError(
                    WmlsCode.MISSING_UNIT_FOR_MEASURE,
                    f"{base_message(int(WmlsCode.MISSING_UNIT_FOR_MEASURE))} "
                    f"Element '/{'/'.join(child_path)}' has no uom.",
                )
            self._visit(child, child_type, index, annotations, child_path)

    def _unit_dictionary_path(self) -> Path:
        data_dir = self._resolve_data_dir()
        return data_dir / _UNIT_DICTIONARY

    def _resolve_data_dir(self) -> Path:
        nested = self._schema_dir / "witsml_v1.4.1.1_data"
        if nested.is_dir():
            return nested
        return self._schema_dir

    def _load_annotations(self) -> frozenset[str]:
        if self._annotations is None:
            root = etree.parse(
                str(self._unit_dictionary_path()), parser=_parser()
            ).getroot()
            annotations: set[str] = set()
            for element in root.iter():
                if not isinstance(element.tag, str):
                    continue
                if etree.QName(element).localname != "UnitOfMeasure":
                    continue
                annotation = element.get("annotation")
                if annotation:
                    annotations.add(annotation)
            self._annotations = frozenset(annotations)
        return self._annotations

    def _load_index(self) -> _TypeIndex:
        if self._index is not None:
            return self._index
        data_dir = self._resolve_data_dir()
        directory = next(
            (
                data_dir / name
                for name in _TYPE_DIRECTORIES
                if (data_dir / name).is_dir()
            ),
            None,
        )
        complex_types: dict[str, etree._Element] = {}
        groups: dict[str, etree._Element] = {}
        elements: dict[str, etree._Element] = {}
        if directory is not None:
            parser = _parser()
            for path in sorted(directory.glob("*.xsd")):
                root = etree.parse(str(path), parser=parser).getroot()
                for node in root:
                    if not isinstance(node.tag, str):
                        continue
                    tag = etree.QName(node).localname
                    name = node.get("name")
                    if not name:
                        continue
                    if tag == "complexType":
                        complex_types.setdefault(name, node)
                    elif tag == "group":
                        groups.setdefault(name, node)
                    elif tag == "element":
                        elements.setdefault(name, node)
        self._index = _TypeIndex(
            complex_types=complex_types,
            groups=groups,
            elements=elements,
            measure_types=_measure_types(complex_types),
        )
        return self._index


def _parser() -> etree.XMLParser:
    return etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        dtd_validation=False,
        huge_tree=False,
    )


def _local_type(value: str | None) -> str | None:
    if not value:
        return None
    return value.split(":")[-1] or None


def _measure_types(
    complex_types: dict[str, etree._Element],
) -> frozenset[str]:
    measures: set[str] = set()
    changed = True
    while changed:
        changed = False
        for name, node in complex_types.items():
            if name in measures:
                continue
            simple_content = node.find(f"{_XS}simpleContent")
            if simple_content is not None:
                extension = simple_content.find(f"{_XS}extension")
                if (
                    extension is not None
                    and _local_type(extension.get("base")) == "abstractMeasure"
                ):
                    measures.add(name)
                    changed = True
                continue
            complex_content = node.find(f"{_XS}complexContent")
            if complex_content is not None:
                extension = complex_content.find(f"{_XS}extension")
                if (
                    extension is not None
                    and _local_type(extension.get("base")) in measures
                ):
                    measures.add(name)
                    changed = True
    return frozenset(measures)


def _choose_type(
    candidates: frozenset[str] | None, measure_types: frozenset[str]
) -> str | None:
    if not candidates:
        return None
    for candidate in candidates:
        if candidate in measure_types:
            return candidate
    return sorted(candidates)[0]
