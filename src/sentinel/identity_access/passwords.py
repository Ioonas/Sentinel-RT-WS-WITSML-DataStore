"""Hash de secretos con Argon2id y tokens de sesión con SHA-256.

El token de sesión es un valor aleatorio de alta entropía; se almacena solo su
SHA-256 (no necesita Argon2). Las contraseñas y credenciales de servicio usan
Argon2id.
"""

from __future__ import annotations

import hashlib

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError


class Argon2PasswordHasher:
    def __init__(
        self,
        *,
        time_cost: int = 3,
        memory_cost: int = 65536,
        parallelism: int = 2,
    ) -> None:
        self._hasher = PasswordHasher(
            time_cost=time_cost,
            memory_cost=memory_cost,
            parallelism=parallelism,
            hash_len=32,
            salt_len=16,
        )

    def hash(self, secret: str) -> str:
        return self._hasher.hash(secret)

    def verify(self, secret: str, hashed: str) -> bool:
        try:
            return self._hasher.verify(hashed, secret)
        except (VerificationError, InvalidHashError):
            return False

    def needs_rehash(self, hashed: str) -> bool:
        try:
            return self._hasher.check_needs_rehash(hashed)
        except InvalidHashError:
            return True


class Sha256TokenHasher:
    def hash_token(self, token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()
