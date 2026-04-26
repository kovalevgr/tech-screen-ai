"""Deterministic in-process mock backend for the Vertex wrapper.

Used by every backend test and the dev/CI default — production refuses to
start in mock mode (spec FR-007 / SC-010, enforced by
:meth:`app.backend.settings.Settings.assert_safe_for_environment`).

Lookup recipe (research §13):

    SHA-256(json.dumps(
        {"system_prompt", "user_payload", "json_schema", "agent", "model"},
        sort_keys=True, ensure_ascii=False,
    ).encode("utf-8"))

Fixtures live under ``<fixtures_dir>/<agent>/<sha>.json`` with the envelope
documented in `contracts/wrapper-contract.md` §9. On a miss the backend
writes the *request* envelope under ``<fixtures_dir>/_unrecorded/<sha>.json``
so a developer can inspect what was asked, then raises a deterministic
test-time ``RuntimeError``.

This module is one of the two allowlisted call sites for provider-SDK
imports (the other is ``_real_backend.py``); it currently imports nothing
from any provider SDK but the allowlist exists for forward compatibility
with offline replay tooling that may simulate provider exception types.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Final

from pydantic import ValidationError

from app.backend.llm._backend_protocol import RawBackendResult

_AGENTS: Final[frozenset[str]] = frozenset({"interviewer", "assessor", "planner"})


def canonical_prompt_payload(
    *,
    system_prompt: str,
    user_payload: str,
    json_schema: dict[str, Any] | None,
    agent: str,
    model: str,
) -> str:
    """Build the canonical JSON string the prompt SHA is computed over.

    Stable across Python invocations (``sort_keys=True``); preserves
    non-ASCII characters in ``user_payload`` so Ukrainian transcripts
    hash identically to their on-the-wire bytes (``ensure_ascii=False``).
    """
    return json.dumps(
        {
            "system_prompt": system_prompt,
            "user_payload": user_payload,
            "json_schema": json_schema,
            "agent": agent,
            "model": model,
        },
        sort_keys=True,
        ensure_ascii=False,
    )


def canonical_prompt_sha(
    *,
    system_prompt: str,
    user_payload: str,
    json_schema: dict[str, Any] | None,
    agent: str,
    model: str,
) -> str:
    """Return the 64-char hex SHA-256 of the canonical prompt payload."""
    payload = canonical_prompt_payload(
        system_prompt=system_prompt,
        user_payload=user_payload,
        json_schema=json_schema,
        agent=agent,
        model=model,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class MockVertexBackend:
    """Fixture-keyed deterministic stub. Zero network I/O.

    Constructed with the agent name and the fixtures-root directory.
    Subdirectory ``<fixtures_dir>/<agent>/`` holds one JSON envelope per
    canonical prompt SHA; ``<fixtures_dir>/_unrecorded/`` collects misses
    for the developer to inspect and promote.
    """

    def __init__(self, *, agent: str, fixtures_dir: Path) -> None:
        if agent not in _AGENTS:
            raise ValueError(f"unknown agent {agent!r} — known: {sorted(_AGENTS)}")
        self._agent = agent
        self._fixtures_dir = fixtures_dir

    @property
    def agent(self) -> str:
        return self._agent

    @property
    def fixtures_dir(self) -> Path:
        return self._fixtures_dir

    async def generate(
        self,
        *,
        system_prompt: str,
        user_payload: str,
        json_schema: dict[str, Any] | None,
        model: str,
        temperature: float,
        max_output_tokens: int,
        timeout_s: float,
    ) -> RawBackendResult:
        """Look up the fixture for the canonical prompt SHA and return it.

        ``temperature``, ``max_output_tokens``, and ``timeout_s`` are
        accepted to match the protocol shape but the mock backend does
        not vary its response on them — fixtures are deterministic by
        design.
        """
        del temperature, max_output_tokens, timeout_s
        sha = canonical_prompt_sha(
            system_prompt=system_prompt,
            user_payload=user_payload,
            json_schema=json_schema,
            agent=self._agent,
            model=model,
        )
        fixture_path = self._fixtures_dir / self._agent / f"{sha}.json"
        if not fixture_path.is_file():
            self._record_unrecorded(
                sha=sha,
                system_prompt=system_prompt,
                user_payload=user_payload,
                json_schema=json_schema,
                model=model,
            )
            raise RuntimeError(f"fixture missing for prompt SHA {sha}; see _unrecorded/{sha}.json")
        try:
            envelope: Any = json.loads(fixture_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"fixture {fixture_path} is not valid JSON: {exc}") from exc
        if not isinstance(envelope, dict):
            raise RuntimeError(
                f"fixture {fixture_path}: expected a JSON object, got {type(envelope).__name__}"
            )
        try:
            return RawBackendResult.model_validate(envelope)
        except ValidationError as exc:
            raise RuntimeError(
                f"fixture {fixture_path} does not match the envelope: {exc}"
            ) from exc

    def _record_unrecorded(
        self,
        *,
        sha: str,
        system_prompt: str,
        user_payload: str,
        json_schema: dict[str, Any] | None,
        model: str,
    ) -> None:
        unrecorded_dir = self._fixtures_dir / "_unrecorded"
        unrecorded_dir.mkdir(parents=True, exist_ok=True)
        envelope = {
            "agent": self._agent,
            "model": model,
            "system_prompt": system_prompt,
            "user_payload": user_payload,
            "json_schema": json_schema,
        }
        (unrecorded_dir / f"{sha}.json").write_text(
            json.dumps(envelope, sort_keys=True, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
