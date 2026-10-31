"""Pruebas de la regla de dependencias de la arquitectura hexagonal."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src" / "sentinel"
CORE = (
    "shared",
    "identity_access",
    "audit_config",
    "xml_schema",
    "witsml_application",
)
FORBIDDEN_MODULES = (
    "sentinel.persistence",
    "sentinel.wmls_transport",
    "sentinel.admin_api",
    "sentinel.mail_worker",
    "sentinel.bootstrap",
)
FORBIDDEN_THIRD_PARTY = (
    "fastapi",
    "starlette",
    "sqlalchemy",
    "asyncpg",
    "uvicorn",
    "smtplib",
)


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_core_does_not_import_adapters() -> None:
    violations: list[str] = []
    for module in CORE:
        for path in (ROOT / module).rglob("*.py"):
            for imported in imported_modules(path):
                if any(
                    imported == forbidden or imported.startswith(f"{forbidden}.")
                    for forbidden in FORBIDDEN_MODULES
                ):
                    violations.append(f"{path.name} importa {imported}")
                if any(
                    imported == forbidden or imported.startswith(f"{forbidden}.")
                    for forbidden in FORBIDDEN_THIRD_PARTY
                ):
                    violations.append(f"{path.name} importa {imported}")
    assert not violations, violations


def test_entry_adapters_do_not_import_persistence() -> None:
    violations: list[str] = []
    for module in ("wmls_transport", "admin_api"):
        for path in (ROOT / module).rglob("*.py"):
            for imported in imported_modules(path):
                if imported.startswith("sentinel.persistence"):
                    violations.append(f"{path.name} importa {imported}")
    assert not violations, violations
