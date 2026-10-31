"""Registro de los objetos WITSML soportados."""

from __future__ import annotations

from dataclasses import dataclass

from sentinel.identity_access.domain import SUPPORTED_WITSML_OBJECTS


@dataclass(frozen=True)
class ObjectSpec:
    name: str
    plural: str
    writable: bool
    supports_growing: bool
    parent: str | None = None


OBJECT_SPECS: dict[str, ObjectSpec] = {
    "well": ObjectSpec("well", "wells", writable=True, supports_growing=False),
    "wellbore": ObjectSpec(
        "wellbore", "wellbores", writable=True, supports_growing=False, parent="well"
    ),
    "log": ObjectSpec(
        "log", "logs", writable=True, supports_growing=True, parent="wellbore"
    ),
    "trajectory": ObjectSpec(
        "trajectory", "trajectorys", writable=True, supports_growing=True,
        parent="wellbore",
    ),
    "changeLog": ObjectSpec(
        "changeLog", "changeLogs", writable=False, supports_growing=False
    ),
}

SUPPORTED_TYPES = tuple(OBJECT_SPECS)
WRITABLE_TYPES = tuple(name for name, spec in OBJECT_SPECS.items() if spec.writable)
assert set(SUPPORTED_WITSML_OBJECTS) <= set(SUPPORTED_TYPES)


def spec_for(object_type: str) -> ObjectSpec:
    try:
        return OBJECT_SPECS[object_type]
    except KeyError as exc:
        from sentinel.shared.errors import ValidationError

        raise ValidationError(f"Tipo de objeto WITSML no soportado: {object_type}") from exc


def object_type_for_plural(plural: str) -> str | None:
    for name, spec in OBJECT_SPECS.items():
        if spec.plural == plural:
            return name
    return None
