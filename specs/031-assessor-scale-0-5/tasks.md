# Tasks: Assessor level-scale correction — six states 0–5

**Input**: Design documents from `specs/031-assessor-scale-0-5/`
**Prerequisites**: plan.md, spec.md; contract `prompts/assessor/v0003/schema.json` (new in this branch)

**Organization**: single branch, `agent: backend-engineer` throughout (prompt-engineer-owned artifacts declared in plan.md), `parallel: false`. Story labels map to spec.md: US1 = Expert answers score 5, US2 = demonstrated absence scores 0, US3 = v0003 active everywhere.

## Phase 1: Prompt version v0003 (US1+US2)

- [X] T001 [US1+US2] `prompts/assessor/v0003/schema.json`: copy of v0002 with `assessments[].level` enum `[0, 1, 2, 3, 4, 5]` + description naming the six states; `$id` → `assessor-output.v3.json`; everything else structurally unchanged
- [X] T002 [US2] `prompts/assessor/v0003/system.md`: based on v0002 (scoped language rule intact); §2 assigns 0–5; §3 inputs L1–L5 descriptors; §4 six states + 0-qualification (probes present + substantive failed attempts; short answer alone stays "not assessable" = empty array); §5 core rules add 0-vs-empty distinction; §7 guardrail 3 (level-0 conditions) + amended guardrail 2; §8 FORBIDDEN 10 (0 is not a penalty); nine sections preserved
- [X] T003 [US1+US2] `prompts/assessor/v0003/level-guide.md`: six entries — 0 None, 1 Basic, 2 Competent, 3 Advanced, 4 Proficient, 5 Expert — crisp English evidence descriptors consistent with system.md; meta-rules updated (0 vs empty array); `## Confidence calibration` section retained (prompt-assembly test asserts it)
- [X] T004 `prompts/assessor/v0003/notes.md`: what changed vs v0002 + why (the two silent-bias bugs; owner decision Ihor 2026-08-02); "Calibration delta: N/A — labelled dataset does not exist yet (T40 not started)"; author line "Claude Code (orchestrated), scale decision: Ihor — 2026-08-02"
- [X] T005 Guard: `prompts/assessor/v0001/**` and `prompts/assessor/v0002/**` byte-identical to main (`git diff main -- prompts/assessor/v0001 prompts/assessor/v0002` empty)

## Phase 2: Activation (US3)

- [X] T006 [US3] `configs/models.yaml`: assessor `prompt_version: "v0003"` (interviewer/planner pins untouched); `prompts/assessor/active.txt` → `v0003` (convenience pointer in lockstep)
- [X] T007 [US3] `app/backend/agents/assessor.py`: `PROMPT_VERSION = "v0003"`; `AssessmentItem.level` → `Literal[0, 1, 2, 3, 4, 5]` with scale docstring; stale v0001/1–4 docstrings updated (contract-miss message now interpolates `PROMPT_VERSION`); prompt files keep loading from the pinned version dir

## Phase 3: Tests (US1+US2+US3)

- [X] T008 [US1] `app/backend/tests/agents/test_assessor.py`: rejection matrix reworked — `level: 5` removed as a rejection case (now VALID), `level: 6` and `level: -1` are the new out-of-enum boundaries (contract-miss retry-once path)
- [X] T009 [US2] New: `test_run_assessor_turn_level_zero_none_is_valid_output` — level 0 with probe-failure rationale + verbatim evidence span accepted, no retry
- [X] T010 [US1] New: `test_run_assessor_turn_level_five_expert_is_valid_output` — level 5 accepted, no retry
- [X] T011 [US3] Lockstep test pins the literal `"v0003"` on BOTH sides (`PROMPT_VERSION` and the models.yaml assessor pin); `_make_inputs` rubric subset gains an L5 descriptor; stale v0001 references in test docstrings updated
- [X] T012 All existing coverage green unchanged in behaviour: echo-mismatch checks, retry matrix, non-schema wrapper-error propagation, serialization determinism, event-loop non-blocking test; `test_prompt_schema_transport.py` auto-covers `assessor-v0003` via the glob

## Phase 4: Docs + gates

- [X] T013 `docs/engineering/glossary.md`: "Competency proficiency scale (canonical)" entry (0=None…5=Expert; rubric files 1–5 only; 0 assessor-output-only; interviewer target-level axis is a DIFFERENT axis; "Proficient" name-collision warning); stale "Level (1–5)" entry aligned. No .docx touched
- [X] T014 Quality gates: `uv run pytest app/backend/tests` green; `ruff check app/backend` + `ruff format --check app/backend` clean; `mypy --strict app/backend` clean; `scripts/check-no-provider-sdk-imports.sh` exits 0
- [X] T015 Spec Kit artifacts (this directory) committed with the feature branch; spec.md § Handoff to T20 records the owner's dialogue-decision table requirement (deterministic "answered / clarify / none" from level+confidence vs plan target, thresholds in config — NOT implemented here)
