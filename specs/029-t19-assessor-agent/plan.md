# Implementation Plan: Assessor agent wrapper (T19)

**Branch**: `029-t19-assessor-agent` | **Date**: 2026-07-06 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/029-t19-assessor-agent/spec.md`

- **agent:** `backend-engineer`
- **parallel:** true (with T18 — Interviewer wrapper, sibling branch)
- **depends_on:** [T17]
- **contract:** `prompts/assessor/v0001/schema.json`

## Summary

T19 ships the second of the two Tier-3 agent wrappers: a thin, typed, async adapter between the future orchestrator (T20) and the T04 `call_model` doorway, bound to the T17 Assessor contract. One new package (`app/backend/agents/`), one module (`assessor.py`), one test module. Purely additive — zero existing files touched.

Deliverables:

1. **`app/backend/agents/__init__.py`** — deliberately re-exports nothing; byte-agreed with the T18 branch so the parallel tasks never conflict on this file (§14: the committed per-agent `schema.json` files are the contract that lets T18/T19 fan out).
2. **`app/backend/agents/assessor.py`** — `PROMPT_VERSION = "v0001"`; module-cached prompt assembly (`system.md` + `level-guide.md`; `schema.json` as `json_schema`); frozen `AssessorTurnInput` mirroring system.md §3 INPUTS (permissive `dict[str, Any]` for structures T20/Tier-4 will type; typed ids win over caller `turn_metadata` in the wire payload); `AssessorOutput`/`AssessmentItem`/`RedFlagItem` mirroring `schema.json` exactly; `run_assessor_turn(...)` with the per-agent retry policy (one fresh retry on schema/validation miss or echoed-id mismatch → `AssessorOutputInvalid` chaining the cause; other wrapper errors untouched).
3. **`app/backend/tests/agents/test_assessor.py`** — real prompt files, `call_model` monkeypatched at the module boundary; retry matrix (incl. echoed-id mismatch); error-propagation matrix; the T19 acceptance test proving the event loop stays free while scoring (ADR-007).

## Technical Context

**Language/Version**: Python 3.12. **Primary Dependencies**: existing only — `app.backend.llm` public surface (`call_model`, `ModelCallRequest`, typed errors), Pydantic v2, pytest + pytest-asyncio (auto mode). Zero new dependencies.

**Storage**: none — the wrapper is pure; tracing/cost flow through the injected `TraceSink` / `CostLedger` protocols exactly as T04 defined them.

**Testing**: `uv run pytest app/backend/tests` (19 new tests, no DB, no network); `ruff check` + `ruff format --check` + `mypy --strict` on `app/backend`.

**Constraints honoured**: §2 (scores, never routes), §11 (English-only Assessor output enforced by the contract itself), §12 (wrapper default caps never raised), §15 (typed failure message carries no candidate text), ADR-007 (plain awaitable coroutine, no blocking I/O after first-call prompt cache fill), FR-014/ADR-002 (no provider SDK imports — `scripts/check-no-provider-sdk-imports.sh` clean).

**Known stale doc**: implementation-plan.md T17's Assessor output one-liner (`concepts_covered/...`) predates the committed contract; per the T17 ownership note the per-agent `schema.json` wins (spec.md Clarifications).

## Constitution Check

| §   | Principle                    | Applies to T19?                                                                                                      | Status |
| --- | ---------------------------- | --------------------------------------------------------------------------------------------------------------------- | ------ |
| 1   | Candidates/reviewers first   | Indirect — strict contract validation keeps assessments reviewer-auditable.                                            | Pass   |
| 2   | Deterministic orchestration  | **Core.** The wrapper scores; no control-flow on model output beyond validation. Routing stays with T20's state machine. | Pass   |
| 3   | Append-only audit trail      | N/A here — trace rows flow through T04's sink unchanged; this module never touches audit tables.                        | N/A    |
| 4   | Immutable rubric snapshots   | Indirect — inputs carry a `rubric_snapshot_subset`; the wrapper never loads the live rubric tree.                       | Pass   |
| 5–6 | Secrets / WIF                | Yes — no secrets, no keys, no new config.                                                                              | Pass   |
| 11  | Hybrid language              | Yes — English prompt + English-JSON output contract; Ukrainian appears only as candidate text inside test payloads.     | Pass   |
| 12  | LLM cost/latency caps        | **Core.** Wrapper defaults (30 s / 4096) untouched; retry adds at most one extra capped call.                           | Pass   |
| 14  | Contract-first parallel work | **Core.** T18/T19 fan out against the committed per-agent schema files (T17); this plan's `contract:` field binds it.   | Pass   |
| 15  | PII containment              | Yes — `AssessorOutputInvalid` message is PII-free; payload detail only on the chained cause.                            | Pass   |
| 17  | Specs precede implementation | Yes — this flow.                                                                                                        | Pass   |
| 18  | Multi-agent explicit         | Yes — `agent:`/`parallel:` declared above; fan-out was orchestrator-approved.                                           | Pass   |

Sections not listed (7–10, 13, 16, 19, 20): N/A for a pure in-process module — no Docker/env/migration/flag/deploy surface. **Gate result**: PASS.

## Project Structure

```text
specs/029-t19-assessor-agent/
├── spec.md
├── plan.md          # This file
└── tasks.md

app/backend/agents/__init__.py             # new — empty public surface (shared line-for-line with T18 branch)
app/backend/agents/assessor.py             # new — the wrapper
app/backend/tests/agents/__init__.py       # new — empty (tests/services convention)
app/backend/tests/agents/test_assessor.py  # new — 19 tests
```

## Phases

- **Phase 0**: contract + floor reading (T17 prompt artefacts, T04 wrapper surface, vertex-integration retry table) — no open unknowns; one staleness recorded in Clarifications.
- **Phase 1**: implementation + tests (tasks.md).
- **Phase 2**: quality gates + commit; merge order vs the T18 branch is arbitrary (only byte-identical or disjoint files overlap).
