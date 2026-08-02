# Implementation Plan: Assessor level-scale correction — six states 0–5

**Branch**: `031-assessor-scale-0-5` | **Date**: 2026-08-02 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/031-assessor-scale-0-5/spec.md`

- **agent:** `backend-engineer` (executing; the `prompts/assessor/v0003/**` artifacts are **prompt-engineer-owned** territory, produced here under the `agent-prompt-edit` discipline by explicit owner direction — single-branch execution, no fan-out)
- **parallel:** false
- **depends_on:** [T17, T19]
- **contract:** `prompts/assessor/v0003/schema.json`

## Summary

Correct the assessor's level scale from `enum [1, 2, 3, 4]` to the canonical six-state N-iX competency-matrix scale `[0, 1, 2, 3, 4, 5]` (owner decision: Ihor, 2026-08-02 — 0=None, 1=Basic, 2=Competent, 3=Advanced, 4=Proficient, 5=Expert). Ship as a new prompt version `prompts/assessor/v0003/` (based on v0002 content, which was authored but never activated), activate it in the same PR (models.yaml + `PROMPT_VERSION` + `Literal[0..5]` in lockstep), update tests to the new boundaries, and record the canonical scale in the glossary. The rubric contract (ranks 1..5) is deliberately untouched — 0 is assessor-output-only.

Fixes two silent-bias bugs (see spec.md): the enum ceiling at 4 silently deflated Advanced+/Proficient/Expert candidates (structured output forces ≤ 4), and the missing 0 forced an unearned Basic when a candidate demonstrably lacked the competency.

## Technical Context

**Language/Version**: Python 3.12. **Dependencies**: none added. **Storage**: none — no DB surface (assessments table consumption is T20+). **Testing**: fully offline; `call_model` mocked at the sanctioned LLM boundary; prompt files and schema are the real committed v0003 artifacts; the offline schema-transport regression (`test_prompt_schema_transport.py`, glob-driven) picks up the v0003 schema automatically.

**Out of scope**: `docs/contracts/rubric.schema.json` and all rubric configs (ranks 1..5 stay); `app/backend/llm/**`; interviewer prompts/wrapper (its Entry/Specialist/Expert/Proficient guide is the POSITION target-level axis — confirmed, not modified); alembic; CI workflows; the T20 dialogue-decision table (requirement recorded in spec.md § Handoff to T20).

## Constitution Check

| §   | Principle                     | Applies?                                                                                                                     | Status |
| --- | ----------------------------- | ---------------------------------------------------------------------------------------------------------------------------- | ------ |
| 2   | Deterministic orchestration   | **Core.** The scale change feeds T20's deterministic decision table; nothing here routes on model output. The handoff section keeps thresholds in config, out of prompts. | Pass   |
| 3   | Append-only audit             | Indirect — motivates the fix (deflated levels would have been permanent in `assessment`); no DB code touched.                  | Pass   |
| 4   | Rubric snapshot frozen        | Indirect — rubric files and contract untouched; only the assessor output domain changes.                                       | Pass   |
| 11  | Hybrid language               | **Core.** v0003 keeps English instructions; candidate-language handling (verbatim evidence spans) carried from v0002 intact.   | Pass   |
| 12  | LLM caps                      | Unchanged — wrapper defaults untouched.                                                                                        | Pass   |
| 13  | Calibration warning-only      | **Core.** No labelled dataset yet (T40); delta declared N/A in v0003 notes.md, owed at T40.                                    | Pass   |
| 16  | Configs as code               | **Core.** New prompt version + models.yaml pin move via PR; prior versions immutable.                                          | Pass   |
| 17  | Specs precede implementation  | Yes — this flow.                                                                                                               | Pass   |
| 18  | Multi-agent explicit          | Single branch, owner-dispatched; prompt-engineer-owned files declared above.                                                   | Pass   |

Sections not listed: N/A — no deploy surface, no secrets, no PII path changes. **Gate result**: PASS.

## Project Structure

```text
specs/031-assessor-scale-0-5/
├── spec.md
├── plan.md          # This file
└── tasks.md

prompts/assessor/v0003/schema.json        # new — level enum [0..5], $id assessor-output.v3.json
prompts/assessor/v0003/system.md          # new — six-state scale, 0-qualification rules
prompts/assessor/v0003/level-guide.md     # new — six entries: None/Basic/Competent/Advanced/Proficient/Expert
prompts/assessor/v0003/notes.md           # new — changes vs v0002, owner decision, calibration N/A
prompts/assessor/active.txt               # v0001 → v0003 (convenience pointer, kept in lockstep)
configs/models.yaml                       # assessor prompt_version → "v0003"
app/backend/agents/assessor.py            # PROMPT_VERSION, Literal[0..5], docstrings
app/backend/tests/agents/test_assessor.py # new boundaries, 0/5 happy paths, v0003 lockstep pin
docs/engineering/glossary.md              # canonical proficiency scale entry + Level entry alignment
```

## Phases

- **Phase 1**: `prompts/assessor/v0003/` authored from v0002 content per `agent-prompt-edit` (v0001/v0002 byte-identical).
- **Phase 2**: activation — models.yaml + active.txt + `assessor.py` in lockstep.
- **Phase 3**: tests — boundary rework (5 valid, 0 valid, 6/−1 reject), lockstep pin, existing coverage green.
- **Phase 4**: docs (glossary), spec artifacts, quality gates.
