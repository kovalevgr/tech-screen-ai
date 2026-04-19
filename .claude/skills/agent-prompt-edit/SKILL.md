---
name: agent-prompt-edit
description: Versioned edit flow for TechScreen runtime agent prompts (Interviewer, Assessor, Planner). Produces a new prompt version folder, preserves the previous version unchanged, updates notes.md, and runs calibration before handoff. Use whenever anything under prompts/<agent>/ changes behaviourally, even for a one-word edit.
---

# agent-prompt-edit

You are changing a runtime agent prompt. Prompts are **versioned, not edited in place**. This skill enforces the flow so that calibration history stays interpretable and old sessions remain replayable against the prompt they were run with.

The only exceptions are pure typo fixes (punctuation, obvious misspelling) that do not change meaning — those can be edited in place with a commit message starting `typo:`.

## When to use this skill

- Adding or removing a section from a system prompt.
- Tightening a guardrail or forbidden item.
- Adjusting the level-prompting guide.
- Swapping an example.
- Bumping a JSON schema field (schema change = prompt version bump).
- Any change that could move calibration agreement by more than noise.

## When NOT to use

- Creating a prompt for a brand-new agent. That is covered by the `vertex-call` skill (new agent setup) and a fresh `v0001` without a predecessor.
- Editing `prompts/shared/ukrainian-anchors.md` or `prompts/shared/candidate-facing/*`. Those are shared assets; edits are independent of any agent version. They still require calibration if the change is substantive.

## The flow

Do these in order. Do not skip.

### 1. Identify the active version

Look in `configs/models.yaml`:

```yaml
interviewer:
  prompt_version: v0003   # active in prod
```

The active version is the one pinned here, not the highest folder number. If they disagree, ask — a hanging draft folder is a sign of a half-finished PR.

### 2. Create the next version folder

Copy the active folder to the next ordinal. Example:

```
prompts/interviewer/v0003/  →  prompts/interviewer/v0004/
```

Every file comes over unchanged: `system.md`, `level-guide.md`, `schema.json` (if the agent has one), `notes.md`, plus any `examples/`.

Do this with file tools, not `git mv`. The goal is a second copy, not a rename.

### 3. Edit the copy

Open the new folder and make the change. Some rules the reviewer will enforce:

- **Nine sections.** ROLE, OBJECTIVES, INPUTS, OUTPUT CONTRACT, LEVEL PROMPTING GUIDE, UKRAINIAN STYLE ANCHORS (if candidate-facing), GUARDRAILS, FORBIDDEN, STYLE FOOTER. Missing sections fail review.
- **No meta-commentary** ("as an AI", "as a language model"). The model should never refer to itself as one.
- **Imperatives, not requests.** "Respond in Ukrainian." not "Please respond in Ukrainian."
- **One idea per bullet.** Compound bullets hide behaviour.
- **Placeholders in `{snake_case}`.** Every placeholder must be populated by the Python builder in `app/backend/llm/agents/<agent>.py`. If you add a new placeholder, update the builder in the same PR.
- **Hybrid language.** System text English. Candidate-facing examples and anchors Ukrainian. No Ukrainian in a GUARDRAIL; no English in a candidate-facing example.
- **Schema bump.** If the change adds, removes, or renames a field in the model's output, `schema.json` must change too, and the call-site parser in `app/backend/llm/agents/<agent>.py` must match.

### 4. Fill `notes.md`

`notes.md` is not decoration. The reviewer reads it, and the next person editing this prompt reads it a year from now. Write:

```markdown
# <agent> <version> — notes

## What changed vs <previous version>
- Bullet 1.
- Bullet 2.

## Why
- Motivation, in 1–3 sentences. Cite the calibration finding, the incident, the ADR, or the user feedback.

## Hypothesised behaviour change
- What you expect calibration to show. Agreement up/down, red-flag recall up/down, specific failure mode reduced.

## Known risks
- What could go wrong. What to watch for in the first 20 candidate sessions after promotion.

## Calibration delta
- Filled after the calibration run. Reference the report path or PR comment.
```

"What changed" and "why" are filled before calibration. "Calibration delta" is filled after.

### 5. Run calibration

Invoke the `calibration-run` skill. It runs the new version against `calibration/dataset/` and produces a report at `calibration/reports/<agent>-<new-version>-<timestamp>.md`.

Attach the report to the PR. Key metrics the reviewer looks at:

- Per-competency exact-match agreement vs prior version.
- Within-0.5 agreement.
- Red-flag precision / recall.
- Systematic bias (does the new version over- or under-rate a specific level?).

Calibration is **warning-only** in CI (constitution §13, ADR-020). A regression is a human decision — but do not ignore it. Either explain in `notes.md` why the new behaviour is intentional (e.g., "we accepted a small dip in L2 agreement to close a false-positive red-flag on junior profiles") or iterate before merging.

### 6. Decide on promotion

Two scenarios:

- **Dev-only.** The PR creates the new version folder and leaves `configs/models.yaml` pointing at the old version. Dev overrides via `LLM_AGENT_PROMPT_OVERRIDE=<agent>=v0004` for local validation. This is the default for larger changes.
- **Promote in the same PR.** Only for low-risk edits where calibration shows no regression. Update `configs/models.yaml` to the new version. Mention in the PR body.

When in doubt, split: one PR adds the version folder, a follow-up PR flips `models.yaml`. That way rollback is a single revert.

### 7. Commit

- Branch: `feat/prompt-<agent>-<slug>`.
- Subject: `add <agent> v<NNNN>: <slug>` — imperative, lowercase, ≤ 72 chars.
- Body: what changed, calibration delta (one-line summary), whether `models.yaml` moves in this PR or next, link to the calibration report.
- **No** `Co-authored-by: Claude` trailers. Project convention.

## Checklist before you hand off

- New version folder present; previous version untouched (diff vs `main` shows only additions under the new folder, plus optionally a `models.yaml` line).
- All nine sections present and non-empty (where applicable).
- `schema.json` bumped if output shape changed; builder parser updated to match.
- Every placeholder referenced by the prompt is declared in the builder.
- `notes.md` has real "What changed", "Why", "Hypothesised behaviour change", and "Known risks".
- Calibration report attached; `notes.md` has the "Calibration delta" line filled.
- Ukrainian output passes the language-consistency check (no русизми; register matches `prompts/shared/ukrainian-anchors.md`).
- No new FORBIDDEN item contradicts an existing GUARDRAIL.
- `configs/models.yaml` either stays put or advances — not accidentally half-updated.

## Common mistakes the reviewer will block

- Edited `prompts/<agent>/v0003/system.md` in place. This is the most common mistake; the reviewer greps the diff for changes inside non-latest version folders and hard-blocks.
- Empty `notes.md` or copy-pasted from the previous version.
- `schema.json` changed but the parser in `app/backend/llm/agents/<agent>.py` still expects the old shape.
- Calibration report not attached, or attached but showing a regression without justification.
- Prompt references a placeholder like `{rubric_levels}` that the builder does not provide. Runtime will pass the literal string `"{rubric_levels}"` to the model.
- English text leaked into a candidate-facing example. Assessor is immune (its output is English); Interviewer and Planner are not.

## References

- `docs/prompt-engineering-playbook.md` — the long-form guide. This skill is the short checklist.
- `docs/anti-patterns.md` — LLM section.
- `prompts/shared/ukrainian-anchors.md` — register for any UA candidate-facing change.
- Constitution §11 (hybrid language), §13 (calibration warning-only), §16 (configs as code).
- ADR-004 (agent architecture), ADR-008 (hybrid language), ADR-020 (correctness variant), ADR-021 (configs as code).
