# Feature Specification: Assessor level-scale correction — six states 0–5

**Feature Branch**: `031-assessor-scale-0-5`
**Created**: 2026-08-02
**Status**: Draft
**Input**: Owner decision (Ihor, 2026-08-02): the canonical N-iX competency-matrix scale is SIX states numbered 0–5 — 0=None ("не володіє" — absence of proficiency), 1=Basic, 2=Competent, 3=Advanced, 4=Proficient, 5=Expert. The shipped assessor contract (`enum [1, 2, 3, 4]` in `prompts/assessor/v0001..v0002/schema.json`, mirrored by `AssessmentItem.level: Literal[1, 2, 3, 4]`) is wrong on two counts and must be corrected before T20 consumes assessor output.

## The two silent-bias bugs this fixes

Both are structural — the schema travels as structured output (`response_json_schema`, verbatim per 030), so the model is FORCED to comply and no prompt prose can compensate:

1. **Ceiling clamp (silent deflation).** The enum caps at 4 while rubric files carry level descriptors for ranks 1..5 (`docs/contracts/rubric.schema.json`, minimum 1 / maximum 5). Every genuinely Expert (5) answer — and any Advanced+ judgement the model wanted to place above 4 — was recorded as at most 4, with no trace that clamping occurred. Assessments land in an append-only table; the deflation would have been permanent and invisible.
2. **Missing floor (unearned Basic).** The scale had no way to express 0/None. When a candidate demonstrably lacked a competency, the model's only legal moves were an unearned level 1 or silently dropping the assessment — either inflating the candidate or losing a real finding of absence.

## Clarifications

### Session 2026-08-02

- Q: Does the rubric contract change too? → A: **No — deliberately untouched.** Rubric FILES keep level ranks 1..5 (Basic..Expert descriptors); None needs no descriptor. `docs/contracts/rubric.schema.json` (minimum 1 / maximum 5), `docs/contracts/rubric-snapshot.schema.json`, `docs/contracts/matrix-format.md`, and all `configs/rubric/**` stay byte-identical. Only the Assessor may emit 0.
- Q: When does 0 qualify? → A: Demonstrated absence: the interviewer probed the competency (probe visible in the turn context) and the candidate's substantive attempts contained no relevant proficiency. A merely short answer ("Не знаю.") stays "not assessable" — empty `assessments` array, never 0. Encoded in v0003 `system.md` §4/§5/§7.2–3/§8.10 and `level-guide.md` (Level 0 entry + meta-rules 6–7).
- Q: New prompt version or in-place edit? → A: New version `prompts/assessor/v0003/` per the `agent-prompt-edit` discipline; v0001 and v0002 preserved byte-identical. v0003 bases on **v0002 content** (which carries the scoped-language fixes but was never activated — `configs/models.yaml` stayed at v0001).
- Q: Activate in the same PR? → A: **Yes (owner-directed).** `configs/models.yaml` assessor `prompt_version: "v0003"`; `PROMPT_VERSION = "v0003"` in `app/backend/agents/assessor.py`; lockstep test pins v0003 on both sides. Interviewer/planner pins untouched.
- Q: Calibration? → A: N/A — labelled dataset does not exist yet (T40 not started). Warning-only per constitution §13; delta owed when T40 lands (recorded in v0003 `notes.md`).
- Q: The v0002 level-guide names (Entry/Specialist/Expert/Proficient)? → A: Those were imported by mistake from the interviewer's POSITION target-level axis (`prompts/interviewer/v0001/level-guide.md`) — a different axis (position target seniority, not candidate proficiency). v0003 replaces them with the proficiency names; the interviewer guide is confirmed correct for its own axis and stays untouched. Name-collision warning ("Proficient" in both scales) recorded in `docs/engineering/glossary.md`.

## User Scenarios & Testing

The "users" are the T20 orchestrator (consumer of `AssessorOutput`), reviewers auditing assessments, and the candidates whose scores must not be silently biased.

### User Story 1 — Expert answers score 5 (Priority: P1)

**Acceptance**: a well-formed assessor payload with `level: 5` validates and returns to the caller with no retry; `level: 6` and `level: -1` are contract misses (retry-once then `AssessorOutputInvalid`).

### User Story 2 — Demonstrated absence scores 0 (Priority: P1)

**Acceptance**: a well-formed payload with `level: 0` validates and returns with no retry. The prompt distinguishes 0 (positive finding of absence, evidence spans quote the failed attempts) from "not assessable" (empty `assessments` array — unchanged behaviour).

### User Story 3 — The active contract is v0003 everywhere (Priority: P1)

**Acceptance**: `configs/models.yaml` assessor pin, `PROMPT_VERSION`, the loaded prompt files, and the transported `schema.json` all resolve to v0003; the lockstep test pins the literal `"v0003"` on both sides. The offline schema-transport regression (glob `prompts/*/v*/schema.json`) covers the v0003 schema automatically and passes.

## Requirements

- **FR-031-1**: `prompts/assessor/v0003/` created from v0002 content; `schema.json` level enum `[0, 1, 2, 3, 4, 5]` with state names in the description; `$id` bumped to `assessor-output.v3.json`; v0001/v0002 byte-identical to main.
- **FR-031-2**: `system.md` / `level-guide.md` describe the six-state scale (guide: six entries 0 None … 5 Expert), define when 0 qualifies, keep the v0002 language-rule scoping and the hybrid-language posture (§11).
- **FR-031-3**: `notes.md` records what changed vs v0002, the two bugs, the owner decision + date, calibration N/A (T40), author line.
- **FR-031-4**: Activation — models.yaml pin + `PROMPT_VERSION` + `AssessmentItem.level: Literal[0, 1, 2, 3, 4, 5]`; docstrings updated; module keeps loading prompt files from the pinned version dir.
- **FR-031-5**: Tests — level 0 and level 5 happy paths; 6 and −1 as the new rejection boundaries; lockstep pins v0003; all existing coverage (echo checks, retry matrix, serialization, concurrency) stays green.
- **FR-031-6**: Docs — canonical-scale note in `docs/engineering/glossary.md` (0=None…5=Expert; rubric files 1–5 only; 0 assessor-output-only; interviewer target-level axis is different; "Proficient" name collision). No .docx touched.
- **FR-031-7**: Untouched: `docs/contracts/rubric.schema.json`, `app/backend/llm/**`, interviewer prompts/wrapper, alembic, CI workflows.

## Handoff to T20 — dialogue-decision table (requirement recorded, NOT implemented here)

Owner requirement for the orchestrator (T20): each turn's dialogue decision — **"answered" / "clarify" / "none"** — must be derived **deterministically** from the assessor's `(level, confidence)` versus the plan's target level for the competency, with the thresholds living in config (not in prompts, not in model output). Constitution §2: this is flow control, so it belongs to the Python state machine; the Assessor only supplies the typed `(level, confidence)` inputs. This branch delivers the six-state input domain the table needs — including level 0, which the table must treat as a valid "none"-signal (demonstrated absence), not missing data — and deliberately does NOT implement the table, its config surface, or its thresholds. T20 owns that, and its spec must reference this section.

## Success Criteria

- **SC-1**: `uv run pytest app/backend/tests`, `ruff check app/backend`, `ruff format --check app/backend`, `mypy --strict app/backend`, `scripts/check-no-provider-sdk-imports.sh` all green.
- **SC-2**: `git diff main -- prompts/assessor/v0001 prompts/assessor/v0002 docs/contracts/rubric.schema.json app/backend/llm` is empty.
- **SC-3**: The schema-transport regression passes for `assessor-v0003` (integer enums transport verbatim via `response_json_schema`).
