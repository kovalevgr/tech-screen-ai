# Assessor — v0002 — notes

## What changed vs v0001

- §8 FORBIDDEN 1 scoped: the no-Ukrainian/no-Russian rule now applies only to fields the Assessor authors (`rationale_en`, `description_en`, `manual_review_reason_en`); `evidence_spans` / `evidence_span` are explicitly exempt as verbatim candidate quotes.
- §8 FORBIDDEN 5 hardened: "do not paraphrase" extended to "do not paraphrase, translate, or transliterate".
- §4 OUTPUT CONTRACT: the `evidence_spans` bullet now states spans stay in the candidate's original language, with a one-line Ukrainian micro-example («для IO-bound я взяв би asyncio»).
- §1 ROLE: "You never produce Ukrainian output" replaced with the scoped formulation (authored prose is English; evidence fields quote verbatim).
- §6 UKRAINIAN STYLE ANCHORS: reworded to match ("quote verbatim; never translate").
- `schema.json` byte-identical to v0001 — the constraint lives in prose, not schema. No placeholder changes; no builder or parser change required.

## Why

v0001 §8.1 ("Do not emit any Ukrainian or Russian text in any field") is unsatisfiable together with §4's requirement that `evidence_spans` be EXACT substrings of the candidate's answer whenever the candidate answers in Ukrainian or Russian — which is the normal case under constitution §11 / ADR-008. Found at the T19 reviewer gate; recorded in `specs/029-t19-assessor-agent/` and the PR #28 body ("Prompt tension for prompt-engineer v0002").

## Hypothesised behaviour change

- Fewer contract misses on Ukrainian/Russian-language turns. Under v0001 the model had to break one of the two rules; the failure modes were translated or paraphrased spans (silent — exactly the drift the planned substring post-validator would reject) or empty/hallucinated spans (loud — schema retry in the T19 wrapper). Expect the wrapper's retry rate on non-English turns to drop.
- Exact-match agreement on Ukrainian-language calibration turns improves or holds; English-turn behaviour unchanged (the two rules coincide there).
- No expected movement in red-flag precision/recall beyond span fidelity.

## Known risks

- The model may over-generalise the exemption and let Ukrainian leak into `rationale_en` / `description_en`. §8.1 still forbids this explicitly; watch the first ~20 sessions after promotion and the first calibration run for non-English text in authored fields.
- The §4 micro-example is the first Ukrainian text in the Assessor system prompt. If calibration shows it pulls rationale register toward Ukrainian, replace it with a language-free formulation.
- Supersedes a v0001 note: v0001 "Known risks" cited "the prompt forbids Ukrainian/Russian in any field" as the guarantee for Russian-language answers; the guarantee is now scoped to authored fields only.

## Calibration delta

- Not run — calibration infrastructure does not exist yet: `calibration/dataset/` and `scripts/calibration_run` land with T40 (Tier 7), and `evals/` is still the empty T01 placeholder. v0001 has no baseline either ("N/A — initial version"). Owed: run assessor v0002 vs v0001 as soon as T40 lands, before or together with the promotion PR.

## Promotion

- This version ships dev-only: `configs/models.yaml` stays at `v0001`, `prompts/assessor/active.txt` stays `v0001`.
- Promotion is a follow-up PR after PR #28 (T19) merges, flipped in lockstep: `configs/models.yaml` `assessor.prompt_version` → `"v0002"`, `app/backend/agents/assessor.py` `PROMPT_VERSION` → `"v0002"` (plus its v0001-referencing docstrings), and `test_prompt_version_pinned_to_v0001` in `app/backend/tests/agents/test_assessor.py` updated to the new pin.

## Author

Drafted via `agent-prompt-edit` (Claude Code session), for review by Ihor — 2026-07-07.
