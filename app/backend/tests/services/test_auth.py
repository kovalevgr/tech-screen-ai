"""Unit tests for the Identity Platform ID-token verifier (T07).

Zero network, zero committed key material: tokens are minted per test run
with a throwaway RSA key (``cryptography`` keygen + ``google.auth.crypt``
signer) and the verifier's ``certs_fetcher`` seam is fed the matching public
key. Covers the constitution acceptance ("middleware unit-tested against
three role fixtures") plus every reject path from
``docs/contracts/id-token-claims.json``.
"""

from __future__ import annotations

import time
from collections.abc import Mapping

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from google.auth import crypt
from google.auth import jwt as google_jwt

from app.backend.services.auth import (
    STAFF_ROLES,
    IdTokenVerifier,
    MissingRoleClaimError,
    TokenVerificationError,
    VerifiedIdentity,
    get_verifier,
    set_verifier,
)

_PROJECT = "tech-screen-test"
_DOMAIN = "n-ix.com"
_KID = "test-key-1"

_OMIT = object()  # sentinel: remove the claim entirely


def _pem_pair() -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = (
        key.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("utf-8")
    )
    return private_pem, public_pem


# One keypair per test session — keygen is the slow part.
_PRIVATE_PEM, _PUBLIC_PEM = _pem_pair()
_CERTS: dict[str, str] = {_KID: _PUBLIC_PEM}
# google-auth ships py.typed but crypt/jwt helpers are unannotated — narrow
# ignores per coding-conventions (same note as services/auth.py).
_SIGNER = crypt.RSASigner.from_string(_PRIVATE_PEM, _KID)  # type: ignore[no-untyped-call]


def _mint(**overrides: object) -> str:
    """Mint a signed ID token with contract-valid defaults."""
    now = int(time.time())
    claims: dict[str, object] = {
        "iss": f"https://securetoken.google.com/{_PROJECT}",
        "aud": _PROJECT,
        "sub": "gcip-uid-123",
        "email": f"recruiter@{_DOMAIN}",
        "email_verified": True,
        "hd": _DOMAIN,
        "role": "recruiter",
        "iat": now - 60,
        "exp": now + 3600,
    }
    claims.update(overrides)
    payload = {k: v for k, v in claims.items() if v is not _OMIT}
    token: bytes = google_jwt.encode(_SIGNER, payload)  # type: ignore[no-untyped-call]
    return token.decode("utf-8")


def _verifier(
    certs: Mapping[str, str] | None = None,
    *,
    fetch_counter: list[int] | None = None,
) -> IdTokenVerifier:
    def _fetch() -> Mapping[str, str]:
        if fetch_counter is not None:
            fetch_counter.append(1)
        return certs if certs is not None else _CERTS

    return IdTokenVerifier(
        project_id=_PROJECT,
        allowed_domain=_DOMAIN,
        certs_fetcher=_fetch,
    )


# ---------------------------------------------------------------------------
# The three role fixtures (constitution acceptance)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("role", sorted(STAFF_ROLES))
async def test_verify_accepts_each_staff_role(role: str) -> None:
    email = f"{role}@{_DOMAIN}"
    token = _mint(role=role, email=email, sub=f"uid-{role}")

    identity = await _verifier().verify(token)

    assert identity == VerifiedIdentity(sub=f"uid-{role}", email=email, role=role)


# ---------------------------------------------------------------------------
# 401 paths — TokenVerificationError
# ---------------------------------------------------------------------------


async def test_verify_rejects_tampered_payload() -> None:
    header, payload, signature = _mint().split(".")
    # Flip payload bytes without touching the (now stale) signature.
    tampered_payload = payload[:-2] + ("AA" if payload[-2:] != "AA" else "BB")
    with pytest.raises(TokenVerificationError):
        await _verifier().verify(f"{header}.{tampered_payload}.{signature}")


async def test_verify_rejects_token_signed_by_unknown_key() -> None:
    other_private, _ = _pem_pair()
    imposter = crypt.RSASigner.from_string(  # type: ignore[no-untyped-call]
        other_private, "imposter-kid"
    )
    now = int(time.time())
    token = google_jwt.encode(  # type: ignore[no-untyped-call]
        imposter,
        {
            "iss": f"https://securetoken.google.com/{_PROJECT}",
            "aud": _PROJECT,
            "sub": "uid",
            "email": f"admin@{_DOMAIN}",
            "email_verified": True,
            "hd": _DOMAIN,
            "role": "admin",
            "iat": now - 60,
            "exp": now + 3600,
        },
    ).decode("utf-8")

    with pytest.raises(TokenVerificationError):
        await _verifier().verify(token)


async def test_verify_rejects_expired_token() -> None:
    now = int(time.time())
    token = _mint(iat=now - 7200, exp=now - 3600)
    with pytest.raises(TokenVerificationError):
        await _verifier().verify(token)


@pytest.mark.parametrize(
    "overrides",
    [
        {"hd": "gmail.com"},  # wrong hosted domain
        {"hd": _OMIT},  # hd never injected (blocking fn bypassed)
        {"email": "someone@gmail.com"},  # email outside domain (hd forged)
        {"email": _OMIT},  # no email at all
        {"email_verified": False},
        {"email_verified": _OMIT},
        {"aud": "some-other-project"},
        {"iss": "https://securetoken.google.com/some-other-project"},
        {"iss": "https://evil.example.com/tech-screen-test"},
        {"sub": ""},
        {"sub": _OMIT},
    ],
    ids=[
        "wrong-hd",
        "missing-hd",
        "email-outside-domain",
        "missing-email",
        "unverified-email",
        "missing-email-verified",
        "wrong-audience",
        "wrong-issuer-project",
        "wrong-issuer-host",
        "empty-sub",
        "missing-sub",
    ],
)
async def test_verify_rejects_bad_claims_with_401_error(overrides: dict[str, object]) -> None:
    with pytest.raises(TokenVerificationError):
        await _verifier().verify(_mint(**overrides))


async def test_verify_rejects_garbage_token() -> None:
    with pytest.raises(TokenVerificationError):
        await _verifier().verify("not-a-jwt-at-all")


# ---------------------------------------------------------------------------
# 403 path — MissingRoleClaimError (valid identity, no authorization)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [{"role": _OMIT}, {"role": "candidate"}, {"role": "superuser"}, {"role": 7}],
    ids=["absent", "candidate", "unknown", "non-string"],
)
async def test_verify_maps_missing_or_non_staff_role_to_403_error(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(MissingRoleClaimError):
        await _verifier().verify(_mint(**overrides))


# ---------------------------------------------------------------------------
# Certs cache behaviour (key rotation)
# ---------------------------------------------------------------------------


async def test_verify_refreshes_certs_once_on_unknown_kid() -> None:
    """Simulates Google key rotation: first fetch is stale, refresh saves it."""
    calls: list[int] = []
    stale_then_fresh: list[Mapping[str, str]] = [{"stale-kid": _PUBLIC_PEM}, _CERTS]

    def _fetch() -> Mapping[str, str]:
        calls.append(1)
        return stale_then_fresh[min(len(calls) - 1, 1)]

    verifier = IdTokenVerifier(project_id=_PROJECT, allowed_domain=_DOMAIN, certs_fetcher=_fetch)
    identity = await verifier.verify(_mint())

    assert identity.role == "recruiter"
    assert len(calls) == 2  # initial fetch + one rotation refresh


async def test_unknown_kid_forced_refresh_respects_cooldown() -> None:
    """Reviewer PR#22 finding 2: garbage-kid spray must not amplify cert fetches.

    Within the cooldown an unknown ``kid`` fails fast against the cache; only
    after the window may the next unknown ``kid`` force one more refetch.
    """
    calls: list[int] = []
    now = [1000.0]

    def _fetch() -> Mapping[str, str]:
        calls.append(1)
        return _CERTS  # never contains the rogue kid

    verifier = IdTokenVerifier(
        project_id=_PROJECT,
        allowed_domain=_DOMAIN,
        certs_fetcher=_fetch,
        forced_refresh_cooldown_seconds=30.0,
        clock=lambda: now[0],
    )
    rogue_priv, _ = _pem_pair()
    rogue_signer = crypt.RSASigner.from_string(rogue_priv, "rogue-kid")  # type: ignore[no-untyped-call]
    wall = int(time.time())
    rogue_token: str = google_jwt.encode(  # type: ignore[no-untyped-call]
        rogue_signer,
        {
            "iss": f"https://securetoken.google.com/{_PROJECT}",
            "aud": _PROJECT,
            "sub": "rogue",
            "email": f"rogue@{_DOMAIN}",
            "email_verified": True,
            "hd": _DOMAIN,
            "role": "recruiter",
            "iat": wall - 60,
            "exp": wall + 3600,
        },
    ).decode("utf-8")

    with pytest.raises(TokenVerificationError):
        await verifier.verify(rogue_token)
    assert len(calls) == 2  # initial fill + one forced refresh

    with pytest.raises(TokenVerificationError):
        await verifier.verify(rogue_token)
    assert len(calls) == 2  # inside the cooldown: no extra fetch

    now[0] += 31.0
    with pytest.raises(TokenVerificationError):
        await verifier.verify(rogue_token)
    assert len(calls) == 3  # cooldown elapsed: one more forced refresh allowed


async def test_small_clock_skew_is_tolerated() -> None:
    """Reviewer PR#22 finding 3: iat marginally ahead of a lagging clock is OK."""
    wall = int(time.time())
    identity = await _verifier().verify(_mint(iat=wall + 5))

    assert identity.role == "recruiter"


async def test_verify_reuses_cached_certs_within_ttl() -> None:
    calls: list[int] = []
    verifier = _verifier(fetch_counter=calls)

    await verifier.verify(_mint())
    await verifier.verify(_mint(role="admin", email=f"admin@{_DOMAIN}"))

    assert len(calls) == 1


# ---------------------------------------------------------------------------
# Constructor guards + process-wide registry
# ---------------------------------------------------------------------------


def test_constructor_requires_project_and_domain() -> None:
    with pytest.raises(ValueError):
        IdTokenVerifier(project_id="", allowed_domain=_DOMAIN)
    with pytest.raises(ValueError):
        IdTokenVerifier(project_id=_PROJECT, allowed_domain="")


def test_verifier_registry_round_trip() -> None:
    assert get_verifier() is None
    verifier = _verifier()
    try:
        set_verifier(verifier)
        assert get_verifier() is verifier
    finally:
        set_verifier(None)
    assert get_verifier() is None
