"""API-level tests for the T07 auth seam (``deps.get_current_user``).

Exercises the HTTP mapping end-to-end through a probe app that mounts the
real ``require_roles`` dependency chain (no database — auth failures raise
before any session dependency resolves), plus the real app's dark-mode
posture and OpenAPI surface. Token verification itself is unit-tested in
``tests/services/test_auth.py``; here a stub verifier drives the seam.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient

from app.backend.api import deps
from app.backend.services.auth import (
    IdTokenVerifier,
    MissingRoleClaimError,
    TokenVerificationError,
    VerifiedIdentity,
    set_verifier,
)

_DOMAIN = "n-ix.com"

#: token string → outcome for the stub verifier.
_TOKENS: dict[str, VerifiedIdentity] = {
    "admin-token": VerifiedIdentity(sub="uid-admin", email=f"admin@{_DOMAIN}", role="admin"),
    "recruiter-token": VerifiedIdentity(
        sub="uid-recruiter", email=f"recruiter@{_DOMAIN}", role="recruiter"
    ),
    "reviewer-token": VerifiedIdentity(
        sub="uid-reviewer", email=f"reviewer@{_DOMAIN}", role="reviewer"
    ),
}


class _StubVerifier(IdTokenVerifier):
    """Deterministic verifier: maps known token strings, rejects the rest."""

    def __init__(self) -> None:
        super().__init__(
            project_id="tech-screen-test",
            allowed_domain=_DOMAIN,
            certs_fetcher=dict,  # never called; verify() is overridden
        )

    async def verify(self, token: str) -> VerifiedIdentity:
        if token == "norole-token":
            raise MissingRoleClaimError("token carries no role claim")
        try:
            return _TOKENS[token]
        except KeyError as exc:
            raise TokenVerificationError("token failed verification") from exc


def _probe_app() -> FastAPI:
    """Minimal app mounting the real auth chain — no DB dependencies."""
    app = FastAPI()

    @app.get("/probe")
    async def probe(  # pyright: ignore[reportUnusedFunction]
        request: Request,
        principal: Annotated[deps.Principal, Depends(deps.require_roles("recruiter", "admin"))],
    ) -> dict[str, object]:
        return {"principal_role": principal.role, "state_user": request.state.user}

    return app


@pytest.fixture
def probe_client() -> Iterator[TestClient]:
    """Probe client with the stub verifier installed (auth 'enabled')."""
    set_verifier(_StubVerifier())
    try:
        yield TestClient(_probe_app())
    finally:
        set_verifier(None)


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Dark mode (§9): no verifier installed — the exact pre-T07 posture
# ---------------------------------------------------------------------------


def test_disabled_mode_answers_401_with_seam_hint() -> None:
    client = TestClient(_probe_app())  # no verifier installed
    response = client.get("/probe", headers=_bearer("admin-token"))
    assert response.status_code == 401
    assert "AUTH_MODE" in response.json()["detail"]


def test_real_app_is_dark_by_default() -> None:
    """The shipped app, no auth env: authenticated surface stays 401-dark."""
    from app.backend.main import app

    app.dependency_overrides[deps.require_crud_enabled] = lambda: None
    try:
        response = TestClient(app).get("/position-templates")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Enabled mode: 401 / 403 / 200 matrix through the untouched require_roles seam
# ---------------------------------------------------------------------------


def test_missing_bearer_token_is_401_with_challenge(probe_client: TestClient) -> None:
    response = probe_client.get("/probe")
    assert response.status_code == 401
    assert response.json()["detail"] == "missing bearer token"
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_invalid_token_is_401_with_challenge(probe_client: TestClient) -> None:
    response = probe_client.get("/probe", headers=_bearer("garbage"))
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize("token", ["admin-token", "recruiter-token"])
def test_manager_roles_pass_the_gate(probe_client: TestClient, token: str) -> None:
    response = probe_client.get("/probe", headers=_bearer(token))
    assert response.status_code == 200
    assert response.json()["principal_role"] == _TOKENS[token].role


def test_reviewer_is_403_at_the_role_gate(probe_client: TestClient) -> None:
    """Valid staff token, wrong role — the pre-T07 require_roles 403 fires."""
    response = probe_client.get("/probe", headers=_bearer("reviewer-token"))
    assert response.status_code == 403
    assert "reviewer" in response.json()["detail"]


def test_missing_role_claim_is_403_with_actionable_body(probe_client: TestClient) -> None:
    response = probe_client.get("/probe", headers=_bearer("norole-token"))
    assert response.status_code == 403
    assert "configs/auth-roles.yaml" in response.json()["detail"]


def test_request_state_user_is_populated(probe_client: TestClient) -> None:
    response = probe_client.get("/probe", headers=_bearer("recruiter-token"))
    assert response.status_code == 200
    assert response.json()["state_user"] == {
        "sub": "uid-recruiter",
        "email": f"recruiter@{_DOMAIN}",
        "role": "recruiter",
    }


# ---------------------------------------------------------------------------
# OpenAPI surface: the bearer scheme is part of the committed contract
# ---------------------------------------------------------------------------


def test_openapi_declares_the_bearer_security_scheme() -> None:
    from app.backend.main import app

    schemes = app.openapi()["components"]["securitySchemes"]
    assert schemes["IdentityPlatformBearer"]["type"] == "http"
    assert schemes["IdentityPlatformBearer"]["scheme"] == "bearer"
    assert schemes["IdentityPlatformBearer"]["bearerFormat"] == "JWT"
