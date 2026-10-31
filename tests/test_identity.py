"""Pruebas unitarias de identidad, roles y contraseñas."""

from __future__ import annotations

from sentinel.identity_access.domain import (
    Grant,
    HumanRole,
    Principal,
    PrincipalKind,
    ServiceRole,
    WitsmlAction,
    permissions_for_role,
)
from sentinel.identity_access.passwords import Argon2PasswordHasher, Sha256TokenHasher


def test_password_hashing_and_rehash_detection() -> None:
    hasher = Argon2PasswordHasher()
    hashed = hasher.hash("Sentinel-Dev-2026")
    assert hashed.startswith("$argon2id$")
    assert hasher.verify("Sentinel-Dev-2026", hashed)
    assert not hasher.verify("wrong", hashed)
    assert not hasher.needs_rehash(hashed)


def test_token_hash_is_deterministic_and_not_reversible() -> None:
    hasher = Sha256TokenHasher()
    first = hasher.hash_token("secret-token")
    assert first == hasher.hash_token("secret-token")
    assert "secret-token" not in first
    assert len(first) == 64


def test_superadmin_has_all_permissions() -> None:
    principal = Principal(
        id="u1",
        name="admin@example.com",
        kind=PrincipalKind.HUMAN,
        role=HumanRole.SUPERADMIN.value,
    )
    assert principal.has("admin.config.write")
    assert principal.allows_witsml(WitsmlAction.DELETE, "well", "w-1")


def test_reader_grants_are_read_only_and_scoped() -> None:
    reader = Principal(
        id="s1",
        name="acme.reader",
        kind=PrincipalKind.SERVICE,
        role=ServiceRole.READER.value,
        grants=(Grant(object_type="well", action=WitsmlAction.READ),),
    )
    assert reader.allows_witsml(WitsmlAction.READ, "well", "w-1")
    assert not reader.allows_witsml(WitsmlAction.WRITE, "well", "w-1")
    assert not reader.allows_witsml(WitsmlAction.READ, "log", "w-1")
    assert reader.readable_wells is None


def test_well_scope_limits_access() -> None:
    principal = Principal(
        id="s2",
        name="acme.scoped",
        kind=PrincipalKind.SERVICE,
        role=ServiceRole.READER.value,
        grants=(Grant(object_type="*", action=WitsmlAction.READ),),
        well_scope=frozenset({"w-1"}),
    )
    assert principal.allows_witsml(WitsmlAction.READ, "well", "w-1")
    assert not principal.allows_witsml(WitsmlAction.READ, "well", "w-2")
    assert principal.readable_wells == frozenset({"w-1"})


def test_role_permissions_are_deny_by_default_for_admin() -> None:
    assert permissions_for_role(HumanRole.ADMIN.value) == frozenset()
    assert "admin.audit.read" in permissions_for_role(HumanRole.AUDITOR.value)
    assert "admin.identities.write" in permissions_for_role(
        HumanRole.SECURITY_ADMIN.value
    )
