"""Identity Platform ID-token verification (T07, ADR-024).

The staff-SSO verifier behind the API auth seam (:mod:`app.backend.api.deps`).
Tokens are Identity Platform (GCIP) ID tokens; the verified-claims contract
is ``docs/contracts/id-token-claims.json``. Verification is **offline**:
RS256 signature against Google's published ``securetoken`` X.509 certs
(TTL-cached in process, force-refreshed once when a token presents an
unknown ``kid`` — key rotation), then claim checks:

- ``iss == https://securetoken.google.com/<project>`` and ``aud == <project>``
- ``exp`` / ``iat`` (enforced by :func:`google.auth.jwt.decode`)
- ``email_verified is True``; ``hd`` **and** the email suffix must match the
  allowed hosted domain (`hd` is injected by the auth-claims blocking
  function — GCIP does not copy Google's claim; specs/021 research R4)
- ``role`` ∈ {admin, recruiter, reviewer} — **absence is a distinct error**
  (:class:`MissingRoleClaimError` → HTTP 403: valid identity, no
  authorization) so the API can answer actionably.

Error messages are log-safe by construction: they never echo claim values
or the token (§15 — staff email is PII-adjacent and must not leak into logs
or response bodies).

Lifecycle mirrors :mod:`app.backend.services.feature_flags`: ``main.py``'s
lifespan installs a process-wide verifier via :func:`set_verifier` when
``AUTH_MODE=identity_platform`` (the §9 dark-launch seam — research R6);
with no verifier installed the seam answers 401, the exact pre-T07 posture.
Tests install stubs through the same registry.
"""

from __future__ import annotations

import asyncio
import json
import time
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Final

from google.auth import jwt as google_jwt

_SECURETOKEN_CERTS_URL: Final[str] = (
    "https://www.googleapis.com/robot/v1/metadata/x509/securetoken@system.gserviceaccount.com"
)
_ISSUER_PREFIX: Final[str] = "https://securetoken.google.com/"
_CERTS_FETCH_TIMEOUT_S: Final[float] = 10.0
_DEFAULT_CERTS_TTL_S: Final[float] = 3600.0

#: Staff roles the backend recognises — keep in lockstep with the `role`
#: enum in docs/contracts/id-token-claims.json and configs/auth-roles.yaml.
STAFF_ROLES: Final[frozenset[str]] = frozenset({"admin", "recruiter", "reviewer"})


class TokenVerificationError(Exception):
    """The bearer token failed verification — maps to HTTP 401."""


class MissingRoleClaimError(Exception):
    """Valid domain identity without a staff ``role`` claim — maps to HTTP 403."""


@dataclass(frozen=True, slots=True)
class VerifiedIdentity:
    """The claims subset the API layer consumes (``request.state.user``)."""

    sub: str
    email: str
    role: str


def _fetch_google_certs() -> Mapping[str, str]:
    """Fetch the ``securetoken`` signing certs (kid → PEM). Sync — run in a thread."""
    with urllib.request.urlopen(_SECURETOKEN_CERTS_URL, timeout=_CERTS_FETCH_TIMEOUT_S) as resp:
        certs: Mapping[str, str] = json.loads(resp.read().decode("utf-8"))
    return certs


class IdTokenVerifier:
    """Offline GCIP ID-token verifier with a TTL-cached certs store.

    Args:
        project_id: GCP project ID — the expected ``aud`` and the issuer
            suffix (``GCP_PROJECT``; both environments share one identity
            plane, research R8).
        allowed_domain: Workspace hosted domain admitted by the middleware
            (``AUTH_ALLOWED_DOMAIN``, ``n-ix.com`` at MVP).
        certs_fetcher: Injection seam for tests — a sync callable returning
            the kid → PEM mapping. Defaults to fetching Google's published
            certs via stdlib ``urllib`` inside ``asyncio.to_thread``.
        certs_ttl_seconds: Cache lifetime for fetched certs.
        forced_refresh_cooldown_seconds: Minimum spacing between unknown-kid
            forced refetches. Without it, a spray of garbage JWTs with
            fabricated ``kid`` values would queue the whole authenticated
            surface behind serialized outbound cert fetches (reviewer PR#22
            finding 2). Within the cooldown an unknown ``kid`` fails fast
            against the cached certs (→ 401).
        clock: Monotonic clock injection seam for tests.
    """

    def __init__(
        self,
        *,
        project_id: str,
        allowed_domain: str,
        certs_fetcher: Callable[[], Mapping[str, str]] | None = None,
        certs_ttl_seconds: float = _DEFAULT_CERTS_TTL_S,
        forced_refresh_cooldown_seconds: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not project_id:
            raise ValueError("project_id must be set (GCP_PROJECT) to verify ID tokens")
        if not allowed_domain:
            raise ValueError("allowed_domain must be set (AUTH_ALLOWED_DOMAIN)")
        self._project_id = project_id
        self._issuer = _ISSUER_PREFIX + project_id
        self._allowed_domain = allowed_domain.lower()
        self._certs_fetcher = certs_fetcher if certs_fetcher is not None else _fetch_google_certs
        self._certs_ttl = certs_ttl_seconds
        self._clock = clock
        self._certs: Mapping[str, str] | None = None
        self._certs_deadline: float = 0.0
        self._forced_cooldown = forced_refresh_cooldown_seconds
        self._forced_ok_after: float = 0.0
        self._certs_lock = asyncio.Lock()

    async def verify(self, token: str) -> VerifiedIdentity:
        """Verify ``token`` and return the consumed claims subset.

        Args:
            token: The raw bearer JWT.

        Returns:
            The :class:`VerifiedIdentity` for the signed-in staff member.

        Raises:
            TokenVerificationError: Signature, issuer, audience, lifetime,
                verification-flag, or hosted-domain failure (→ 401).
            MissingRoleClaimError: Valid identity without a staff role (→ 403).
        """
        certs = await self._get_certs()
        kid = self._peek_kid(token)
        if kid is not None and kid not in certs:
            # Google rotates signing keys; refresh once before failing.
            certs = await self._get_certs(force_refresh=True)
        try:
            # google-auth ships py.typed but jwt.decode is unannotated —
            # narrow ignore per coding-conventions (no blanket override).
            claims = google_jwt.decode(  # type: ignore[no-untyped-call]
                token,
                certs=dict(certs),
                audience=self._project_id,
                # Google's own verifiers tolerate small skew; 0 rejects a
                # token minted with iat == now on a 1 s-lagging clock
                # (reviewer PR#22 finding 3).
                clock_skew_in_seconds=10,
            )
        except ValueError as exc:
            raise TokenVerificationError("token failed signature/audience/lifetime checks") from exc
        return self._check_claims(dict(claims))

    async def _get_certs(self, *, force_refresh: bool = False) -> Mapping[str, str]:
        async with self._certs_lock:
            certs = self._certs
            now = self._clock()
            if force_refresh and now < self._forced_ok_after:
                # Unknown-kid refresh inside the cooldown window: fail fast
                # against the cache instead of refetching (finding 2).
                force_refresh = False
            if force_refresh or certs is None or now >= self._certs_deadline:
                certs = await asyncio.to_thread(self._certs_fetcher)
                self._certs = certs
                self._certs_deadline = self._clock() + self._certs_ttl
                if force_refresh:
                    self._forced_ok_after = self._clock() + self._forced_cooldown
            return certs

    @staticmethod
    def _peek_kid(token: str) -> str | None:
        try:
            # Unannotated in google-auth despite py.typed — see verify() note.
            header = google_jwt.decode_header(token)  # type: ignore[no-untyped-call]
        except ValueError as exc:
            raise TokenVerificationError("malformed token") from exc
        kid = dict(header).get("kid")
        return kid if isinstance(kid, str) else None

    def _check_claims(self, claims: dict[str, object]) -> VerifiedIdentity:
        if claims.get("iss") != self._issuer:
            raise TokenVerificationError("unexpected token issuer")
        sub = claims.get("sub")
        if not isinstance(sub, str) or not sub:
            raise TokenVerificationError("token has no subject")
        email = claims.get("email")
        if not isinstance(email, str) or "@" not in email:
            raise TokenVerificationError("token has no usable email claim")
        if claims.get("email_verified") is not True:
            raise TokenVerificationError("token email is not verified")
        # hd is injected by the auth-claims blocking function (research R4);
        # the email-suffix check is deliberate defense in depth.
        if claims.get("hd") != self._allowed_domain:
            raise TokenVerificationError("token is not from the allowed hosted domain")
        if not email.lower().endswith("@" + self._allowed_domain):
            raise TokenVerificationError("token email is outside the allowed hosted domain")
        role = claims.get("role")
        if role is None:
            raise MissingRoleClaimError("token carries no role claim")
        if not isinstance(role, str) or role not in STAFF_ROLES:
            raise MissingRoleClaimError("token role claim is not a recognised staff role")
        return VerifiedIdentity(sub=sub, email=email, role=role)


# ---------------------------------------------------------------------------
# Process-wide verifier registry (mirrors feature_flags.set_service):
# installed by main.py's lifespan when AUTH_MODE=identity_platform, reset on
# shutdown; tests install stubs through the same seam. None = dark (§9).
# ---------------------------------------------------------------------------

_verifier: IdTokenVerifier | None = None


def set_verifier(verifier: IdTokenVerifier | None) -> None:
    """Install (or clear, with ``None``) the process-wide verifier."""
    global _verifier
    _verifier = verifier


def get_verifier() -> IdTokenVerifier | None:
    """Return the installed verifier, or ``None`` when auth is dark."""
    return _verifier
