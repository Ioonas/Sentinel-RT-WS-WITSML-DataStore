"""Comprobación de contraseñas comunes o comprometidas (NIST SP 800-63B-4).

Dos reglas sin red externa:

1. La contraseña no puede figurar en una lista de contraseñas comunes o
   filtradas. La lista local (``data/common_passwords.txt``) se normaliza a
   minúsculas; la comparación también ignora mayúsculas.
2. La contraseña no puede contener palabras de contexto asociadas a la cuenta
   (parte local del correo, nombre visible y el propio nombre del producto).

La lista es una base mínima. Para cobertura completa de brechas conviene una
lista mayor (por ejemplo, un volcado local de contraseñas filtradas).
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable
from functools import lru_cache
from importlib import resources

_DATA_FILE = "common_passwords.txt"
_PRODUCT_TERMS = ("sentinel", "witsml")
_MIN_CONTEXT_TERM = 4


def _normalize(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().lower()


@lru_cache(maxsize=1)
def _common_passwords() -> frozenset[str]:
    text = (
        resources.files("sentinel.identity_access")
        .joinpath("data", _DATA_FILE)
        .read_text(encoding="utf-8")
    )
    return frozenset(line for line in (_normalize(item) for item in text.splitlines()) if line)


def context_terms(*values: str | None) -> frozenset[str]:
    """Palabras de contexto de una cuenta: fragmentos de correo y nombre más el producto."""
    terms: set[str] = set(_PRODUCT_TERMS)
    for value in values:
        if not value:
            continue
        normalized = _normalize(value)
        terms.add(normalized)
        for piece in normalized.replace("@", " ").replace(".", " ").replace("-", " ").split():
            terms.add(piece)
    return frozenset(term for term in terms if len(term) >= _MIN_CONTEXT_TERM)


def is_common(password: str) -> bool:
    return _normalize(password) in _common_passwords()


def contains_context_term(password: str, terms: Iterable[str]) -> bool:
    lowered = _normalize(password)
    return any(term in lowered for term in terms)
