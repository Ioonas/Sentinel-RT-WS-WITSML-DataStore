"""Puerto generador de identificadores."""

from __future__ import annotations

import uuid
from typing import Protocol


class IdGenerator(Protocol):
    def new_uid(self) -> str: ...

    def new_token(self, nbytes: int = 32) -> str: ...


class UuidGenerator:
    def new_uid(self) -> str:
        return str(uuid.uuid4())

    def new_token(self, nbytes: int = 32) -> str:
        import secrets

        return secrets.token_urlsafe(nbytes)
