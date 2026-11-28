"""Supervisor: espera creciente ante fallas repetidas y reinicio al estabilizarse."""

from __future__ import annotations

import time

from sentinel.audit_config.domain import SERVICE_API, SERVICE_MAIL_WORKER
from sentinel.bootstrap import supervisor


def test_comandos_cubren_los_dos_servicios() -> None:
    assert set(supervisor.COMMANDS) == {SERVICE_API, SERVICE_MAIL_WORKER}


def test_espera_crece_ante_fallas_rapidas() -> None:
    child = supervisor.Child(name=SERVICE_API, started_at=time.monotonic())
    supervisor._on_exit(child, 1)
    first = child.restart_at - time.monotonic()
    child.started_at = time.monotonic()
    supervisor._on_exit(child, 1)
    second = child.restart_at - time.monotonic()
    assert second > first


def test_espera_vuelve_al_minimo_si_el_proceso_fue_estable() -> None:
    child = supervisor.Child(name=SERVICE_MAIL_WORKER, backoff=16.0)
    child.started_at = time.monotonic() - supervisor.STABLE_AFTER_SECONDS - 1
    supervisor._on_exit(child, 0)
    assert child.backoff == supervisor.BACKOFF_MIN_SECONDS * 2
