#!/usr/bin/env python3
"""Configura la herramienta oficial wPCTT para apuntar a un Store Sentinel.

El script no forma parte del producto: prepara una instalación local de la
herramienta de certificación (``wcat.exe``) sin modificar sus scripts ni sus
esquemas. Guarda una copia de seguridad de los archivos que toca y nunca
imprime la contraseña.

Uso típico::

    python certification/prepare_wcat.py \
        --tool-home "D:/Descargas-J/Docs/wPCTT1.1-t1.0-s1.0" \
        --server-url "http://localhost:8000/witsml" \
        --username "wcat.certification" \
        --password "<secreto>"

Después: ejecutar ``load_data_set.exe -as`` y abrir ``wcat.exe`` desde
``--tool-home``. Ver ``certification/README.md``.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

SERVER_FILE = Path("server") / "default_server.py"
PROFILES_FILE = Path("server") / "server_access_profiles.ini"
SCHEMA_VERSION = "1.4.1.1"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tool-home", required=True, type=Path)
    parser.add_argument("--server-url", required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--profile", default="sentinel-certification")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Solo mostrar la configuración actual (contraseña redactada).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    server_file = args.tool_home / SERVER_FILE
    profiles_file = args.tool_home / PROFILES_FILE
    if not server_file.is_file() or not profiles_file.is_file():
        print(
            f"No se encontró una instalación de wPCTT en {args.tool_home}.",
            file=sys.stderr,
        )
        return 2
    if args.check:
        _print_current(server_file, profiles_file)
        return 0
    if not re.match(r"^https?://", args.server_url):
        print("--server-url debe incluir esquema http:// o https://.", file=sys.stderr)
        return 2

    backup_dir = _backup(args.tool_home, server_file, profiles_file)
    _update_server_file(server_file, args)
    _update_profiles_file(profiles_file, args)
    print(f"Copia de seguridad: {backup_dir}")
    print(f"Perfil configurado: {args.profile}")
    print(f"URL: {args.server_url}")
    print(f"Usuario: {args.username}")
    print("Contraseña: <redactada>")
    return 0


def _backup(tool_home: Path, *files: Path) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = tool_home / "server" / f"backup-{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=False)
    for path in files:
        shutil.copy2(path, backup_dir / path.name)
    return backup_dir


def _update_server_file(path: Path, args: argparse.Namespace) -> None:
    values = {
        "server_name": repr(args.profile),
        "server_URL": repr(args.server_url),
        "server_username": repr(args.username),
        "server_password": repr(args.password),
        "server_schema_version": repr(SCHEMA_VERSION),
    }
    text = path.read_text(encoding="utf-8")
    for key, value in values.items():
        pattern = re.compile(rf"^{re.escape(key)}\s*=\s*.*$", re.MULTILINE)
        if not pattern.search(text):
            raise SystemExit(f"{path} no contiene la variable {key}.")
        text = pattern.sub(f"{key} = {value}", text, count=1)
    path.write_text(text, encoding="utf-8", newline="\n")


def _update_profiles_file(path: Path, args: argparse.Namespace) -> None:
    values = {
        "server_url": args.server_url,
        "server_username": args.username,
        "server_password": args.password,
        "server_proxy_url": "",
    }
    lines: list[str] = []
    section: str | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            section = stripped
            lines.append(line)
            continue
        if section in ("[DEFAULT]", "[[server]") and "=" in line:
            key = line.split("=", 1)[0].strip()
            if key in values:
                lines.append(f"{key} = {values[key]}")
                continue
        lines.append(line)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def _print_current(server_file: Path, profiles_file: Path) -> None:
    names = (
        "server_name",
        "server_URL",
        "server_username",
        "server_password",
        "server_schema_version",
    )
    text = server_file.read_text(encoding="utf-8")
    for name in names:
        match = re.search(rf"^{name}\s*=\s*(.*)$", text, re.MULTILINE)
        value = match.group(1).strip() if match else "<ausente>"
        if name == "server_password" and value not in ('""', "''", ""):
            value = "<definida>"
        print(f"{name} = {value}")
    print(f"profiles = {profiles_file}")


if __name__ == "__main__":
    raise SystemExit(main())
