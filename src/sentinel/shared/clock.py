"""Puerto de reloj. El núcleo no llama ``datetime.now`` directamente para que
la semántica de crecimiento y auditoría sea verificable en pruebas."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class FixedClock:
    """Reloj controlable para pruebas unitarias."""

    def __init__(self, current: datetime) -> None:
        self._current = current

    def now(self) -> datetime:
        return self._current

    def advance(self, seconds: float) -> None:
        from datetime import timedelta

        self._current += timedelta(seconds=seconds)
