# Assessor — v0003 — notes

## What changed vs v0002

- `schema.json`: `assessments[].level` enum widened from `[1, 2, 3, 4]` to `[0, 1, 2, 3, 4, 5]`, with a description naming the six states (0=None, 1=Basic, 2=Competent, 3=Advanced, 4=Proficient, 5=Expert). `$id` bumped to `assessor-output.v3.json`. Everything else structurally unchanged from v0002.
- `system.md`: every scale mention updated — §2 objective now assigns 0–5; §3 inputs describe rubric nodes with L1–L5 descriptors (was L1–L4); §4 defines the six states and when 0 qualifies; §5 core rules add the 0-vs-not-assessable distinction; §7 gains guardrail 3 (conditions for level 0) and amends guardrail 2 (short answer alone is never 0); §8 gains FORBIDDEN 10 (0 is not a penalty). The v0002 scoping of the language rule (§1 / §4 / §6 / §8.1 / §8.5 — authored prose English, evidence spans verbatim) is intact, byte-for-byte where the scale did not touch it.
- `level-guide.md`: rebuilt around the canonical six-state N-iX competency-matrix scale. The v0002 level names (Entry / Specialist / Expert / Proficient — imported by mistake from the interviewer's POSITION target-level axis) are replaced by the proficiency names Basic / Competent / Advanced / Proficient / Expert, a Level 0 (None) entry is added, and meta-rules 3 / 6 plus a new meta-rule 7 spell out "0 vs empty array". Confidence bands unchanged and explicitly applied to level 0.

## Why

Two silent-bias bugs in the v0001/v0002 contract, both structural (the schema itself forced them — no amount of prompt prose could compensate):

1. **Cap at 4 silently deflated the top of the scale.** The canonical N-iX competency-matrix scale has six states 0–5, and rubric files carry level descriptors for ranks 1..5 (`docs/contracts/rubric.schema.json` minimum 1 / maximum 5). With `enum [1,2,3,4]` travelling as structured output, the model was FORCED to emit ≤ 4: every Expert-level (5) answer was recorded as at most Proficient, with no trace that clamping happened.
2. **No 0 forced an unearned Basic.** When a candidate demonstrably lacked a competency ("не володіє"), the closest legal output was level 1 (or dropping the assessment entirely) — either inflating the candidate or silently losing a real finding of absence.

Owner decision (Ihor, 2026-08-02): the canonical scale is six states 0–5 — 0=None, 1=Basic, 2=Competent, 3=Advanced, 4=Proficient, 5=Expert. Rubric FILES keep level ranks 1..5 (None needs no descriptor); only the Assessor may emit 0.

## Hypothesised behaviour change

- Level distribution grows a true right tail (5s appear for genuinely expert answers) and a truthful floor (0s replace unearned 1s or silently dropped assessments).
- No expected movement on mid-scale (2–3) agreement: descriptors for those ranks are unchanged.
- Risk-watch metric: rate of level-0 emissions on turns that should be "not assessable" (empty array). The prompt draws this line three times (§4, §5, §7.2–3, guide meta-rule 7); calibration should verify the model respects it.

## Known risks

- The model may over-emit 0 for short-but-honest answers despite the guardrails. Watch the first ~20 sessions after promotion for 0s without probe evidence in the turn context.
- The model may under-emit 5 (anchoring bias toward the old ceiling from generic training priors). If calibration shows a missing right tail on known-expert answers, strengthen the L5 example set.
- "Proficient" name collision: the interviewer's POSITION target-level guide (Entry/Specialist/Expert/Proficient, `prompts/interviewer/v0001/level-guide.md`) is a different axis. The two agents never see each other's guides, so no runtime confusion is possible — but humans reading calibration output should mind the collision (see `docs/engineering/glossary.md`, "Competency proficiency scale").
- Downstream: T20's dialogue-decision table must treat 0 as a valid, meaningful level (absence), not as missing data. Recorded in `specs/031-assessor-scale-0-5/spec.md` § Handoff to T20.

## Calibration delta

- N/A — labelled dataset does not exist yet (T40 not started). `calibration/dataset/` and the calibration runner land with T40 (Tier 7); v0001 and v0002 have no baseline either. Owed: run assessor v0003 against the labelled set as soon as T40 lands.

## Promotion

- Promoted in the same PR (owner-directed): `configs/models.yaml` `assessor.prompt_version` → `"v0003"`, `app/backend/agents/assessor.py` `PROMPT_VERSION` → `"v0003"` and `AssessmentItem.level` → `Literal[0..5]`, lockstep test pins v0003 on both sides. v0002 was never activated (models.yaml stayed at v0001); v0003 supersedes it directly and carries all v0002 prose fixes.

## Author

Claude Code (orchestrated), scale decision: Ihor — 2026-08-02.
