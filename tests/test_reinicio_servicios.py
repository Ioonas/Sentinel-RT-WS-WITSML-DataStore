"""Decisión de reinicio: espera a operaciones en curso, cancela tras el plazo."""

from __future__ import annotations

from sentinel.bootstrap.restart import (
    DECISION_CANCEL,
    DECISION_DRAIN,
    DECISION_NONE,
    DECISION_RESTART,
    restart_decision,
)


def test_sin_solicitud_pendiente_no_hace_nada() -> None:
    assert (
        restart_decision(requested=3, handled=3, in_flight=5, waited=0, timeout=300)
        == DECISION_NONE
    )


def test_reinicia_cuando_no_hay_operaciones_en_curso() -> None:
    assert (
        restart_decision(requested=4, handled=3, in_flight=0, waited=0, timeout=300)
        == DECISION_RESTART
    )


def test_espera_mientras_hay_operaciones_en_curso() -> None:
    assert (
        restart_decision(requested=4, handled=3, in_flight=2, waited=120, timeout=300)
        == DECISION_DRAIN
    )


def test_cancela_si_las_operaciones_no_terminan_a_tiempo() -> None:
    assert (
        restart_decision(requested=4, handled=3, in_flight=1, waited=300, timeout=300)
        == DECISION_CANCEL
    )
