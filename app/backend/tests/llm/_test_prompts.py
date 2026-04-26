"""Canonical test prompts and matching SHAs for the wrapper test suite.

Lives **inside** ``app/backend/tests/llm/`` (not under ``fixtures/``) because
pytest auto-collects fixture-dir contents as test modules in some setups
and the helper here is genuinely test code, not a fixture envelope. The
fixture files committed under
``app/backend/tests/fixtures/llm_responses/<agent>/<sha>.json`` are named
with the SHAs computed by :func:`prompt_sha` over the constants here, so
the test suite and the committed fixtures stay in lockstep.

Use these exact prompts in any wrapper-level test that needs a fixture
hit; making up a fresh prompt will compute a different SHA and trigger
the ``_unrecorded`` capture path (which is itself a valid test target,
just be intentional about it).
"""

from __future__ import annotations

from typing import Any, Final

from app.backend.llm._mock_backend import canonical_prompt_sha

# Per-agent JSON schemas mirror the agent-output contracts from
# `docs/specs/agents.docx` at a minimal-viable shape — enough to exercise
# Stage-2 validation without drifting from the spec contract.
INTERVIEWER_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "message_uk": {"type": "string"},
        "intent": {"type": "string"},
        "next_topic_hint": {"type": "string"},
        "end_of_phase": {"type": "boolean"},
    },
    "required": ["message_uk", "intent", "end_of_phase"],
    "additionalProperties": False,
}

ASSESSOR_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "concepts_covered": {"type": "array", "items": {"type": "string"}},
        "concepts_missing": {"type": "array", "items": {"type": "string"}},
        "red_flags": {"type": "array", "items": {"type": "string"}},
        "level_estimate": {"type": "string"},
        "confidence": {"type": "number"},
    },
    "required": [
        "concepts_covered",
        "concepts_missing",
        "level_estimate",
        "confidence",
    ],
    "additionalProperties": False,
}

PLANNER_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "next_phase": {"type": "string"},
        "rationale": {"type": "string"},
    },
    "required": ["next_phase", "rationale"],
    "additionalProperties": False,
}

# Canonical prompts. English instructions with synthetic non-PII content
# (constitution §15). The user payloads are intentionally short so the
# fixtures stay small and the SHAs in version control are stable.
INTERVIEWER_SYSTEM_PROMPT: Final[str] = (
    "You are the Interviewer agent. Ask the candidate one question at a time."
)
INTERVIEWER_USER_PAYLOAD: Final[str] = (
    "Phase: warmup. Candidate has joined the call. Greet them in Ukrainian "
    "and ask the first scoping question."
)
INTERVIEWER_MODEL: Final[str] = "gemini-2.5-flash"

ASSESSOR_SYSTEM_PROMPT: Final[str] = (
    "You are the Assessor agent. Score the candidate's last answer."
)
ASSESSOR_USER_PAYLOAD: Final[str] = (
    "Question: What is recursion? Candidate answer: When a function calls itself."
)
ASSESSOR_MODEL: Final[str] = "gemini-2.5-flash"

# Schema-INVALID variant: a different user payload that the broken
# fixture is keyed against. The fixture's `text` field is JSON that
# omits a required field of ASSESSOR_SCHEMA so the wrapper's Stage-2
# validation rejects it.
ASSESSOR_BROKEN_USER_PAYLOAD: Final[str] = (
    "Question: Explain TCP. Candidate answer: It is a protocol that sends data."
)

PLANNER_SYSTEM_PROMPT: Final[str] = "You are the Planner agent. Decide the next interview phase."
PLANNER_USER_PAYLOAD: Final[str] = (
    "Current phase: scoping. Assessor confidence: 0.7. Time remaining: 25 min."
)
PLANNER_MODEL: Final[str] = "gemini-2.5-pro"


def prompt_sha(
    *,
    agent: str,
    system_prompt: str,
    user_payload: str,
    json_schema: dict[str, Any] | None,
    model: str,
) -> str:
    """Thin shim around :func:`canonical_prompt_sha` for test ergonomics."""
    return canonical_prompt_sha(
        system_prompt=system_prompt,
        user_payload=user_payload,
        json_schema=json_schema,
        agent=agent,
        model=model,
    )


# Pre-computed SHAs for the four committed fixtures. Recompute these via
# `python -c "from app.backend.tests.llm._test_prompts import *; print(...)"`
# whenever a constant above changes.
INTERVIEWER_SHA: Final[str] = prompt_sha(
    agent="interviewer",
    system_prompt=INTERVIEWER_SYSTEM_PROMPT,
    user_payload=INTERVIEWER_USER_PAYLOAD,
    json_schema=INTERVIEWER_SCHEMA,
    model=INTERVIEWER_MODEL,
)
ASSESSOR_SHA: Final[str] = prompt_sha(
    agent="assessor",
    system_prompt=ASSESSOR_SYSTEM_PROMPT,
    user_payload=ASSESSOR_USER_PAYLOAD,
    json_schema=ASSESSOR_SCHEMA,
    model=ASSESSOR_MODEL,
)
ASSESSOR_BROKEN_SHA: Final[str] = prompt_sha(
    agent="assessor",
    system_prompt=ASSESSOR_SYSTEM_PROMPT,
    user_payload=ASSESSOR_BROKEN_USER_PAYLOAD,
    json_schema=ASSESSOR_SCHEMA,
    model=ASSESSOR_MODEL,
)
PLANNER_SHA: Final[str] = prompt_sha(
    agent="planner",
    system_prompt=PLANNER_SYSTEM_PROMPT,
    user_payload=PLANNER_USER_PAYLOAD,
    json_schema=PLANNER_SCHEMA,
    model=PLANNER_MODEL,
)
