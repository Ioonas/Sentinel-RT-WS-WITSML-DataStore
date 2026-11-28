"""Supervisor de los procesos de Sentinel: levanta la API y el worker de correo.

Relanza cada proceso cuando termina, ya sea por un reinicio solicitado desde el panel
o por una falla. Si un proceso falla con frecuencia, espera más antes de relanzarlo
(hasta 60 s). Al apagarse el supervisor, detiene a los hijos en orden.

Uso: ``python -m sentinel.bootstrap.supervisor [api] [mail-worker]``.
Sin argumentos levanta ambos. En Windows se ejecuta como servicio con NSSM o similar;
en Linux, con systemd (ver ``deploy/supervisor``).
"""

from __future__ import annotations

import logging
import subprocess
import sys
import time
from dataclasses import dataclass, field

from sentinel.audit_config.domain import SERVICE_API, SERVICE_MAIL_WORKER, SERVICE_NAMES

logger = logging.getLogger("sentinel.supervisor")

BACKOFF_MIN_SECONDS = 2.0
BACKOFF_MAX_SECONDS = 60.0
# Un proceso que vivió más que esto se considera estable y reinicia su espera.
STABLE_AFTER_SECONDS = 60.0
STOP_GRACE_SECONDS = 30.0
POLL_SECONDS = 1.0

COMMANDS: dict[str, list[str]] = {
    SERVICE_API: [sys.executable, "-c", "from sentinel.bootstrap.cli import serve; serve()"],
    SERVICE_MAIL_WORKER: [
        sys.executable,
        "-c",
        "from sentinel.bootstrap.cli import mail_worker; mail_worker()",
    ],
}


@dataclass
class Child:
    name: str
    process: subprocess.Popen | None = None
    started_at: float = 0.0
    backoff: float = BACKOFF_MIN_SECONDS
    restart_at: float = 0.0
    restarts: int = field(default=0)


def _start(child: Child) -> None:
    child.process = subprocess.Popen(COMMANDS[child.name])
    child.started_at = time.monotonic()
    child.restarts += 1
    logger.info("Servicio %s iniciado (pid %s)", child.name, child.process.pid)


def _on_exit(child: Child, code: int) -> None:
    uptime = time.monotonic() - child.started_at
    if uptime >= STABLE_AFTER_SECONDS:
        child.backoff = BACKOFF_MIN_SECONDS
    wait = child.backoff
    child.backoff = min(BACKOFF_MAX_SECONDS, child.backoff * 2)
    child.restart_at = time.monotonic() + wait
    child.process = None
    logger.warning(
        "Servicio %s terminó (código %s tras %.0f s); se relanza en %.0f s",
        child.name,
        code,
        uptime,
        wait,
    )


def _stop_all(children: list[Child]) -> None:
    running = [c for c in children if c.process is not None]
    for child in running:
        child.process.terminate()
    deadline = time.monotonic() + STOP_GRACE_SECONDS
    for child in running:
        remaining = max(0.0, deadline - time.monotonic())
        try:
            child.process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            logger.error("Servicio %s no respondió a tiempo; se fuerza su cierre", child.name)
            child.process.kill()
            child.process.wait()
        logger.info("Servicio %s detenido", child.name)


def run(services: list[str] | None = None) -> None:
    names = services or list(SERVICE_NAMES)
    unknown = [name for name in names if name not in COMMANDS]
    if unknown:
        raise SystemExit("Servicio desconocido: " + ", ".join(unknown))
    children = [Child(name=name) for name in names]
    logger.info("Supervisor iniciado para: %s", ", ".join(names))
    for child in children:
        _start(child)
    try:
        while True:
            time.sleep(POLL_SECONDS)
            now = time.monotonic()
            for child in children:
                if child.process is not None:
                    code = child.process.poll()
                    if code is not None:
                        _on_exit(child, code)
                elif now >= child.restart_at:
                    _start(child)
    except KeyboardInterrupt:
        logger.info("Apagando el supervisor")
    finally:
        _stop_all(children)


USAGE = """Uso: python -m sentinel.bootstrap.supervisor [api] [mail-worker]

Sin argumentos levanta la API WITSML/administrativa (api) y el worker de correo
(mail-worker). Con nombres, levanta solo esos servicios.
"""


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    if any(arg in ("-h", "--help", "/?") for arg in args):
        print(USAGE)
        return
    unknown = [arg for arg in args if arg not in COMMANDS]
    if unknown:
        raise SystemExit(f"Servicio desconocido: {', '.join(unknown)}\n\n{USAGE}")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    run(args or None)


if __name__ == "__main__":
    main()
