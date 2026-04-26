"""Structural test: no class on the credential surface accepts inline secrets (T046b).

Maps to FR-015 / ADR-013 / constitution §5–§6.

The wrapper deliberately exposes **no** parameter through which a caller
could pass a credential, API key, service-account key, PEM, or token —
authentication must come from Application Default Credentials (Workload
Identity Federation in production, ``gcloud auth application-default
login`` in dev). A future PR that adds such a parameter would silently
re-introduce a class of foot-gun the constitution forbids.

This test inspects the public ``__init__`` signatures of:

- :class:`app.backend.llm._real_backend.RealVertexBackend`
- :class:`app.backend.settings.Settings`

and asserts that **no** parameter name appears in the forbidden set.
A failure here means a code reviewer must justify the new surface in
an ADR before merging.
"""

from __future__ import annotations

import inspect
from typing import Final

from app.backend.llm._real_backend import RealVertexBackend
from app.backend.settings import Settings

_FORBIDDEN_PARAM_NAMES: Final[frozenset[str]] = frozenset(
    {
        "credentials",
        "api_key",
        "key",
        "token",
        "service_account",
        "pem",
        "private_key",
        "google_application_credentials",
    }
)


def _params_of(cls: type) -> set[str]:
    """Return the set of explicit ``__init__`` parameter names for ``cls``.

    Uses ``inspect.signature(cls)`` (the constructor signature) rather than
    ``inspect.signature(cls.__init__)`` to keep ``mypy --strict`` quiet —
    accessing ``__init__`` on the class object itself is reported as
    unsound because the attribute could come from an incompatible subclass.
    """
    return set(inspect.signature(cls).parameters.keys())


def test_real_vertex_backend_init_has_no_credential_parameter() -> None:
    """``RealVertexBackend.__init__`` must NOT accept any inline credential.

    Authentication is ADC-only (constitution §5/§6, ADR-013). The class
    intentionally exposes only ``project`` and ``location`` — both
    non-secret routing parameters.
    """
    params = _params_of(RealVertexBackend)
    forbidden = params & _FORBIDDEN_PARAM_NAMES
    assert not forbidden, (
        f"RealVertexBackend.__init__ exposes forbidden credential parameter(s) "
        f"{sorted(forbidden)}. ADC only — see ADR-013 / constitution §5–§6."
    )


def test_settings_has_no_credential_parameter() -> None:
    """``Settings.__init__`` must NOT accept any inline credential.

    Per ADR-022 the only env keys ``Settings`` knows about are non-secret:
    ``LLM_BACKEND``, ``APP_ENV``, ``LLM_BUDGET_PER_SESSION_USD``,
    ``LLM_FIXTURES_DIR``. A credential field would silently let a developer
    drop a JSON key into ``.env`` and have it picked up — exactly the
    pattern ADR-013 forbids.
    """
    params = _params_of(Settings)
    forbidden = params & _FORBIDDEN_PARAM_NAMES
    assert not forbidden, (
        f"Settings.__init__ exposes forbidden credential parameter(s) "
        f"{sorted(forbidden)}. .env is for non-secret keys only — see "
        f"ADR-022 / ADR-013 / constitution §5–§6."
    )
