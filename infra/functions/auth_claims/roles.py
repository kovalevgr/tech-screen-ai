"""Pure decision logic for the auth-claims blocking function (T07, ADR-024).

Deliberately SDK-free: this module is imported both by ``main.py`` (inside
the deployed Cloud Function, where ``firebase_functions`` exists) and by the
repo test suite (where it does not). Everything here is synchronous, pure,
and unit-tested against the committed ``configs/auth-roles.yaml``.

The mapping file is the constitution §16 source of truth
(``configs/auth-roles.yaml``); the deploy runbook vendors a copy next to the
function (``specs/021-t07-identity-sso/quickstart.md`` §4). Validation is
strict structural Python (no jsonschema dependency in the function runtime):
an invalid mapping raises :class:`RoleMappingError` at import/cold-start,
which fails sign-ins loudly (fail-closed) instead of admitting anyone.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Final

import yaml

#: The only roles the TechScreen backend recognises — keep in lockstep with
#: docs/contracts/id-token-claims.json (`role` enum) and
#: app/backend/services/auth.py (STAFF_ROLES).
STAFF_ROLES: Final[frozenset[str]] = frozenset({"admin", "recruiter", "reviewer"})


class RoleMappingError(ValueError):
    """Raised when the role-mapping YAML is structurally invalid."""


@dataclass(frozen=True)
class RoleMapping:
    """Parsed, validated content of ``configs/auth-roles.yaml``."""

    domain: str
    roles: Mapping[str, str]  # lower-cased email -> staff role


@dataclass(frozen=True)
class Decision:
    """Outcome of the sign-in gate for one account.

    ``allowed=False`` means the blocking function must reject the event
    (permission denied). ``claims`` holds the custom claims to inject when
    allowed: always ``hd``; ``role`` only for mapped emails.
    """

    allowed: bool
    reason: str | None = None
    claims: Mapping[str, str] = field(default_factory=dict)


def load_mapping(path: Path) -> RoleMapping:
    """Load and strictly validate the role mapping.

    Args:
        path: Location of the (vendored) ``auth-roles.yaml``.

    Returns:
        The validated, immutable :class:`RoleMapping`.

    Raises:
        RoleMappingError: On any structural problem — missing/empty domain,
            non-mapping ``roles``, email keys without ``@``, or role values
            outside :data:`STAFF_ROLES`.
    """
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RoleMappingError(f"role mapping file not found: {path}") from exc

    if not isinstance(loaded, dict):
        raise RoleMappingError(f"{path}: expected a YAML mapping at top level")

    domain = loaded.get("domain")
    if not isinstance(domain, str) or not domain.strip() or "@" in domain:
        raise RoleMappingError(f"{path}: 'domain' must be a bare hostname string")

    raw_roles = loaded.get("roles")
    if not isinstance(raw_roles, dict):
        raise RoleMappingError(f"{path}: 'roles' must be a mapping of email -> role")

    roles: dict[str, str] = {}
    for email, role in raw_roles.items():
        if not isinstance(email, str) or "@" not in email:
            raise RoleMappingError(f"{path}: role key {email!r} is not an email address")
        if not isinstance(role, str) or role not in STAFF_ROLES:
            raise RoleMappingError(
                f"{path}: role for {email!r} must be one of {sorted(STAFF_ROLES)}, got {role!r}"
            )
        roles[email.strip().lower()] = role

    return RoleMapping(domain=domain.strip().lower(), roles=MappingProxyType(roles))


def decide(email: object, email_verified: object, mapping: RoleMapping) -> Decision:
    """Gate one sign-in/creation event and compute the claims to inject.

    Args:
        email: The account email as reported by Identity Platform (untyped —
            the event payload is external input).
        email_verified: The provider's verification flag for that email.
        mapping: The validated role mapping.

    Returns:
        A :class:`Decision` — blocked (with a log-safe reason that contains
        no PII) or allowed with the ``hd`` (+ optional ``role``) claims.
    """
    if not isinstance(email, str) or "@" not in email:
        return Decision(allowed=False, reason="account has no usable email")
    if email_verified is not True:
        return Decision(allowed=False, reason="account email is not verified")

    normalized = email.strip().lower()
    _, _, domain = normalized.rpartition("@")
    if domain != mapping.domain:
        return Decision(allowed=False, reason="account is outside the allowed hosted domain")

    claims: dict[str, str] = {"hd": mapping.domain}
    role = mapping.roles.get(normalized)
    if role is not None:
        claims["role"] = role
    return Decision(allowed=True, claims=MappingProxyType(claims))
