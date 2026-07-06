# Implementation Plan: Interviewer agent wrapper (T18)

**Branch**: `028-t18-interviewer-agent` | **Date**: 2026-07-06 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/028-t18-interviewer-agent/spec.md`

- **agent:** `backend-engineer`
- **parallel:** true (with T19 — assessor wrapper; disjoint files, shared `app/backend/agents/__init__.py` is byte-identical on both branches and re-exports nothing)
- **depends_on:** [T17]
- **contract:** `prompts/interviewer/v0001/schema.json` (per-agent, no aggregate — T17 ownership note; created on this branch as T17 gap closure before any wrapper code)

## Summary

One new module, `app/backend/agents/interviewer.py`: a thin, typed, pure adapter between the T20 orchestrator and `call_model`. It assembles the pinned-version system prompt at runtime (system.md + level-guide.md + shared Ukrainian anchors), serializes the typed §3 inputs as the user payload, calls the wrapper with the committed `schema.json`, validates `result.parsed` into a frozen `InterviewerOutput`, and applies the T18 per-agent retry policy (one retry on schema-class failures, then typed `InterviewerOutputInvalid`). Deliverables:

1. **Commit 1 (T17 gap closure)** — `prompts/interviewer/v0001/schema.json` codifying the existing system.md §4 output contract; dated addendum in `notes.md`; no prompt text changed.
2. **`app/backend/agents/__init__.py`** — docstring-only package init; deliberately re-exports nothing (T18/T19 parallel-safety).
3. **`app/backend/agents/interviewer.py`** — `PROMPT_VERSION = "v0001"`, frozen input/output models, `InterviewerOutputInvalid`, `run_interviewer_turn(inputs, *, sink, ledger, settings)`.
4. **Tests** — `app/backend/tests/agents/test_interviewer.py`: `call_model` monkeypatched at the interviewer module boundary; real committed prompt files for assembly assertions; the full T18 acceptance matrix.

## Technical Context

**Language/Version**: Python 3.12. No new dependencies.

**Primary Dependencies**: `app.backend.llm` public surface only (`call_model`, `ModelCallRequest`, `ModelCallResult`, `VertexSchemaError`); `TraceSink` / `CostLedger` protocols and `Settings` for pass-through injection; Pydantic for the typed models; stdlib `json` / `pathlib` / `functools.lru_cache` for prompt loading.

**Storage**: none. No DB access, no migrations. Tracing flows through the wrapper's injected sink (durable sink is T21).

**Testing**: `uv run pytest app/backend/tests/agents` (18 tests, no DB, no network); full gates `pytest app/backend/tests` + `ruff check` + `ruff format --check` + `mypy --strict app/backend`.

**Project Type**: backend module + unit tests. Purely additive.

**Constraints**: §2 (wrapper executes the orchestrator's move, never decides), §11 (English module/prompts, Ukrainian utterances stay inside payload/output data), §12 (default caps untouched; retry budget bounded at one), §15 (no logging in this module — `call_model` owns the single non-PII log event), §16 (prompt version pinned in code must match `configs/models.yaml`; asserted by a test), §17 (this spec flow), provider-SDK import ban (pre-commit hook).

**Scale/Scope**: 1 contract file + notes addendum, 2 source files (~230 lines), 1 test module (~380 lines), 3 spec artefacts.

## Constitution Check

| §   | Principle                    | Applies to T18?                                                                                                              | Status |
| --- | ---------------------------- | ----------------------------------------------------------------------------------------------------------------------------- | ------ |
| 2   | Deterministic orchestration  | **Core.** `next_planned_move` arrives decided; the output's `internal_move_executed` is a typed enum for drift detection only. | Pass   |
| 3   | Append-only audit trail      | Indirect — trace writes happen inside `call_model` via the injected sink; this module adds no DB paths.                        | Pass   |
| 5/6 | Secrets / WIF                | No credentials touched; no provider SDK imported.                                                                              | Pass   |
| 11  | Hybrid language              | English code/prompt instructions; Ukrainian only in candidate-facing data (test fixtures included).                            | Pass   |
| 12  | LLM cost/latency caps        | **Core.** Defaults (30 s / 4096) never raised; schema retry bounded at exactly one extra call.                                 | Pass   |
| 14  | Contract-first parallel work | **Core.** `schema.json` committed (commit 1) before wrapper code; T19 parallelises against its own T17 contract.               | Pass   |
| 15  | PII containment              | Module emits no logs; payload goes only into the sanctioned interview pipeline call.                                           | Pass   |
| 16  | Configs as code              | `PROMPT_VERSION` pinned in source, lockstep with `configs/models.yaml` asserted by test; `active.txt` not read at runtime.     | Pass   |
| 17  | Specs precede implementation | This flow.                                                                                                                      | Pass   |
| 18  | Multi-agent explicit         | `agent:`/`parallel:` declared above; fan-out with T19 was requested explicitly by the owner.                                    | Pass   |

**Gate result**: PASS. One doc-drift item surfaced (not a violation): `docs/engineering/vertex-integration.md` § "JSON mode" sketched "Interviewer: no retry"; the implementation plan's T18 acceptance (single retry) supersedes it. Resolved on this branch (Phase 3) per the reviewer gate's PASS-WITH-FINDINGS direction, rather than in a follow-up PR.

## Project Structure

### Documentation (this feature)

```text
specs/028-t18-interviewer-agent/
├── spec.md
├── plan.md                  # This file
└── tasks.md
```

### Source (repository)

```text
prompts/interviewer/v0001/schema.json          # commit 1 — T17 gap closure (contract)
prompts/interviewer/v0001/notes.md             # commit 1 — dated addendum; commit 3 adds the bounds-derivation clause
app/backend/agents/__init__.py                 # new (backend-engineer)
app/backend/agents/interviewer.py              # new (backend-engineer)
app/backend/tests/agents/__init__.py           # new, empty
app/backend/tests/agents/test_interviewer.py   # new (backend-engineer)
docs/engineering/vertex-integration.md         # commit 3 — Interviewer retry line aligned (reviewer finding 1)
docs/engineering/implementation-plan.md        # commit 3 — T17 stale schema sketch → schema.json as source of truth (finding 2)
docs/engineering/coding-conventions.md         # commit 3 — backend layout gains agents/ line (finding 3)
```

## Phases

- **Phase 0**: contract gap closure (commit 1) — the §14 precondition for the T18/T19 parallel group.
- **Phase 1**: wrapper module + typed models + retry policy.
- **Phase 2**: unit suite (mock only at the `call_model` boundary) + full quality gates.
- **Phase 3**: reviewer findings (PASS-WITH-FINDINGS, commit 3) — three doc-drift fixes, notes.md bounds clause, schema deepcopy, mixed-sequence + cache-independence tests.
