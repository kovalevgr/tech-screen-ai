"""Identity Platform blocking function — domain gate + role claims (T07, ADR-024).

Two HTTPS endpoints deployed from this package (gen2 Cloud Functions,
operator runbook: ``specs/021-t07-identity-sso/quickstart.md`` §4):

- ``before_created`` (``beforeUserCreated``): blocks account creation for
  non-``n-ix.com`` / unverified emails; injects persistent ``hd`` (+ ``role``
  when mapped) custom claims.
- ``before_signed_in`` (``beforeUserSignedIn``): re-derives the same claims
  on EVERY sign-in as session claims, so a role change in
  ``configs/auth-roles.yaml`` (redeployed with the function) takes effect at
  the next sign-in — no persistent stale claims (research R2).

The ``firebase_functions`` SDK implements the blocking-function wire
protocol, including verification of the GCIP-signed request JWT — the
endpoints are deployed ``--allow-unauthenticated`` because Identity Platform
is the caller and the payload signature is the authentication (research R7).

The role mapping is a vendored copy of ``configs/auth-roles.yaml`` placed
next to this file by the deploy step. A missing/invalid mapping raises at
cold start: sign-ins fail loudly (fail-closed) rather than admitting anyone.

This module is intentionally a thin adapter: all decision logic lives in
:mod:`roles` (pure, repo-unit-tested). It imports ``firebase_functions``,
which exists only in the function runtime (``requirements.txt`` here) — the
repo test suite never imports this module.
"""

from __future__ import annotations

from pathlib import Path

from firebase_functions import https_fn, identity_fn
from roles import Decision, decide, load_mapping

_MAPPING = load_mapping(Path(__file__).parent / "auth-roles.yaml")


def _decision_for(event: identity_fn.AuthBlockingEvent) -> Decision:
    decision = decide(event.data.email, event.data.email_verified, _MAPPING)
    if not decision.allowed:
        # Reason strings are log-safe by construction (no email/PII — §15).
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.PERMISSION_DENIED,
            message=decision.reason or "sign-in rejected",
        )
    return decision


@identity_fn.before_user_created(region="europe-west1")
def before_created(
    event: identity_fn.AuthBlockingEvent,
) -> identity_fn.BeforeCreateResponse | None:
    """Gate account creation. Deliberately sets NO persistent claims.

    Persistent ``custom_claims`` written here would survive removal from
    ``configs/auth-roles.yaml``: session claims merge over persistent ones and
    an *absent* session ``role`` cannot erase a persisted ``role``, so a
    removed staff member would keep their old role forever (reviewer PR#22
    finding 1). Both blocking triggers fire on the first sign-in, so
    :func:`before_signed_in`'s session claims already deliver the role for
    every session — creation only needs the allow/deny gate.
    """
    _decision_for(event)
    return None


@identity_fn.before_user_signed_in(region="europe-west1")
def before_signed_in(
    event: identity_fn.AuthBlockingEvent,
) -> identity_fn.BeforeSignInResponse | None:
    """Gate every sign-in and refresh the claims for this session's tokens."""
    decision = _decision_for(event)
    return identity_fn.BeforeSignInResponse(session_claims=dict(decision.claims))
