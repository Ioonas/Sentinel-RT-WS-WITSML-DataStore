"""Límites de uid según abstractUidString de WITSML 1.4.1.1: máximo 64, sin espacios."""

import pytest

from sentinel.shared.errors import ValidationError
from sentinel.xml_schema.documents import normalize_uid


def test_uid_de_64_caracteres_es_valido():
    assert normalize_uid("a" * 64) == "a" * 64


def test_uid_de_65_caracteres_se_rechaza():
    with pytest.raises(ValidationError):
        normalize_uid("a" * 65)


def test_uid_con_espacios_se_rechaza():
    with pytest.raises(ValidationError):
        normalize_uid("pozo uno")
    with pytest.raises(ValidationError):
        normalize_uid(" pozo")


def test_uid_vacio_devuelve_none():
    assert normalize_uid(None) is None
    assert normalize_uid("") is None
