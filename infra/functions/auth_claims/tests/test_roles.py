"""Unit tests for the auth-claims blocking-function decision logic (T07).

Runs inside the repo's default pytest suite (pyproject ``testpaths`` includes
``infra/functions``) so an invalid committed ``configs/auth-roles.yaml`` or a
regression in the sign-in gate cannot merge. Imports only the SDK-free
``roles`` module — ``firebase_functions`` is never needed at test time.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from infra.functions.auth_claims.roles import (
    STAFF_ROLES,
    Decision,
    RoleMappingError,
    decide,
    load_mapping,
)

_REPO_ROOT = Path(__file__).resolve().parents[4]
_COMMITTED_MAPPING = _REPO_ROOT / "configs" / "auth-roles.yaml"


def _write_mapping(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "auth-roles.yaml"
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture
def mapping(tmp_path: Path):
    return load_mapping(
        _write_mapping(
            tmp_path,
            """
domain: n-ix.com
roles:
  Admin@N-iX.com: admin
  recruiter@n-ix.com: recruiter
  reviewer@n-ix.com: reviewer
""",
        )
    )


# ---------------------------------------------------------------------------
# load_mapping — validation of the §16 source of truth
# ---------------------------------------------------------------------------


def test_load_mapping_accepts_the_committed_configs_file() -> None:
    """The real configs/auth-roles.yaml must always validate (US4)."""
    loaded = load_mapping(_COMMITTED_MAPPING)
    assert loaded.domain == "n-ix.com"
    assert loaded.roles, "the committed mapping must map at least the operator"
    assert set(loaded.roles.values()) <= STAFF_ROLES


def test_load_mapping_normalises_email_case(mapping) -> None:
    assert "admin@n-ix.com" in mapping.roles


@pytest.mark.parametrize(
    "content",
    [
        "[]",  # not a mapping
        "roles: {}",  # missing domain
        "domain: ''\nroles: {}",  # empty domain
        "domain: someone@n-ix.com\nroles: {}",  # domain is an email
        "domain: n-ix.com\nroles: []",  # roles not a mapping
        "domain: n-ix.com\nroles:\n  not-an-email: admin",  # key without @
        "domain: n-ix.com\nroles:\n  a@n-ix.com: superuser",  # unknown role
        "domain: n-ix.com\nroles:\n  a@n-ix.com: [admin]",  # non-string role
    ],
)
def test_load_mapping_rejects_invalid_shapes(tmp_path: Path, content: str) -> None:
    with pytest.raises(RoleMappingError):
        load_mapping(_write_mapping(tmp_path, content))


def test_load_mapping_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(RoleMappingError):
        load_mapping(tmp_path / "nope.yaml")


# ---------------------------------------------------------------------------
# decide — the sign-in gate (data-model.md decision table)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("email", "role"),
    [
        ("admin@n-ix.com", "admin"),
        ("recruiter@n-ix.com", "recruiter"),
        ("reviewer@n-ix.com", "reviewer"),
    ],
)
def test_decide_maps_each_staff_role(mapping, email: str, role: str) -> None:
    decision = decide(email, True, mapping)
    assert decision.allowed
    assert dict(decision.claims) == {"hd": "n-ix.com", "role": role}


def test_decide_allows_unmapped_domain_email_without_role_claim(mapping) -> None:
    """Unmapped staff sign in role-less; the backend answers 403 (US4)."""
    decision = decide("newcomer@n-ix.com", True, mapping)
    assert decision.allowed
    assert dict(decision.claims) == {"hd": "n-ix.com"}


def test_decide_is_case_insensitive_on_lookup(mapping) -> None:
    decision = decide("Recruiter@N-IX.com", True, mapping)
    assert decision.allowed
    assert decision.claims["role"] == "recruiter"


@pytest.mark.parametrize(
    ("email", "verified"),
    [
        ("outsider@gmail.com", True),  # wrong domain
        ("spoof@n-ix.com.evil.com", True),  # suffix trick
        ("recruiter@n-ix.com", False),  # unverified
        ("recruiter@n-ix.com", None),  # verification unknown
        (None, True),  # no email at all
        ("not-an-email", True),
    ],
)
def test_decide_blocks_everyone_else(mapping, email: object, verified: object) -> None:
    decision = decide(email, verified, mapping)
    assert not decision.allowed
    assert decision.reason
    # Reject reasons must be log-safe: no PII / email echo (§15).
    assert not (isinstance(email, str) and email in decision.reason)


def test_decision_claims_default_empty() -> None:
    assert dict(Decision(allowed=False, reason="x").claims) == {}
