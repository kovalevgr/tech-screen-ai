# Prompt Engineering Playbook

How we write, edit, and release agent system prompts in TechScreen. Agent output quality is mostly determined by prompt quality — this is our most-read, most-edited artefact class per line of code.

Related: [ADR-004](../adr/004-agent-architecture-2-plus-1.md), [ADR-008](../adr/008-hybrid-prompt-language.md), [constitution §11](../.specify/memory/constitution.md).

---

## Where prompts live

```
prompts/
├── interviewer/
│   ├── v0001/
│   │   ├── system.md                  Main system prompt (English).
│   │   ├── level-guide.md             Per-level tone and depth guidance.
│   │   └── notes.md                   Author's notes: what changed, why, calibration delta.
│   ├── v0002/
│   └── active.txt                     Contains "v0002" — env-pinned active version.
├── assessor/
│   └── v0001/ ...
├── planner/
│   └── v0001/ ...
└── shared/
    ├── ukrainian-anchors.md           Ukrainian exemplars (see ADR-008).
    ├── json-schemas/                  JSON schemas used by agents.
    └── candidate-facing/              Fixed Ukrainian strings shown to candidates.
        ├── opening.md
        ├── pause.md
        └── closing.md
```

Active version per environment is tracked in `configs/models.yaml` (not in `active.txt` at runtime — `active.txt` is a convenience link for the `agent-prompt-edit` skill).

Prompt versions are append-only. A bad v0003 is not edited in place; v0004 supersedes it.

---

## Anatomy of a system prompt

Every agent system prompt has these sections in order:

### 1. ROLE

One paragraph identifying what the agent is and what it is not. Written in the second person to the model.

> You are the Interviewer in a structured technical interview. You are not an assessor, coach, or tutor. You conduct the dialogue in Ukrainian with a calm, professional, supportive tone.

### 2. OBJECTIVES

A bulleted list of what the agent must accomplish in its single call. Maximum five items.

### 3. INPUTS

A description of the input structure the agent will receive. References the JSON schema or data shape.

> You will receive:
> - `interview_plan_snapshot`: the plan frozen for this session, including seed questions and depth-probe branches.
> - `recent_turns`: the last eight turns (candidate + interviewer) in chronological order.
> - `current_competency`: the competency currently under evaluation.

### 4. OUTPUT CONTRACT

The exact structure of the expected response. For Assessor and Planner, this is a JSON schema reference and a worked example. For Interviewer, this is a short Ukrainian string format.

### 5. LEVEL PROMPTING GUIDE

Per-level tone and depth calibration (entry / specialist / expert / proficient). Specifies vocabulary register, question complexity, how to probe depth, and how to signal off-topic. Mandatory for Interviewer; recommended for Assessor and Planner.

### 6. UKRAINIAN STYLE ANCHORS

Reference to `prompts/shared/ukrainian-anchors.md`. Pulled in for Interviewer (who produces Ukrainian output) and Planner (whose seed questions end up in candidate-facing Ukrainian). Not used by Assessor (whose output is English JSON).

### 7. GUARDRAILS

A numbered list of "if you encounter X, do Y" rules. Examples:

> - If the candidate asks the interviewer for a hint or the answer, gently decline and return to the question.
> - If the candidate writes in Russian, respond in Ukrainian and do not comment on the language choice.
> - If the candidate seems distressed (expresses anxiety or confusion), offer a brief reassuring sentence and move to an easier question in the same competency.

### 8. FORBIDDEN

A numbered list of things the agent must never do. Stated plainly.

> - Do not disclose the rubric, the plan, or the scoring criteria to the candidate.
> - Do not speculate on whether the candidate will be hired.
> - Do not apologise for asking technical questions.

### 9. STYLE FOOTER

One paragraph restating the tone: "supportive, concise, professional Ukrainian" or similar. This is the last thing the model sees before user input.

---

## Writing style for the prompt itself

- **Short declarative sentences.** Models follow concrete instructions better than abstract ones.
- **Lists over paragraphs** where order matters.
- **Positive framing preferred**, but explicit negatives are OK in FORBIDDEN.
- **No meta commentary** about being an AI or a language model.
- **No "please"** in instructions — it reads as optional. Use imperative.
- **One idea per bullet.** A bullet that says "do X and also Y" should be two bullets.
- **No run-on sentences.** If you cannot read a sentence aloud in one breath, split it.

---

## Variables and placeholders

- Use `{variable_name}` in snake_case for substitutions.
- Every placeholder in the prompt is declared in the Python builder function. No dynamic `**context` spreads.
- Where a placeholder might be empty, the builder provides a sentinel value, not an empty string. ("No prior turns." rather than "".)

---

## Ukrainian anchors

`prompts/shared/ukrainian-anchors.md` contains:

1. **Register samples.** Five to eight short paragraphs of the desired Ukrainian tone — warm, professional, peer-to-peer.
2. **Opening phrases.** How to ask a question politely, how to acknowledge an answer, how to request elaboration.
3. **Bad examples.** A handful of anti-examples: too cold, too casual, too formal, code-switched. Labelled clearly.
4. **Dictionary.** A short list of technical terms and their preferred Ukrainian form (when a Ukrainian term exists) vs acceptable English usage (when it does not).

The anchors are maintained in collaboration with N-iX recruiters and reviewed quarterly.

---

## Versioning rules

A new prompt version is created when:

- The ROLE, OBJECTIVES, INPUTS, or OUTPUT CONTRACT sections change.
- A GUARDRAIL is added, removed, or materially altered.
- A LEVEL PROMPTING GUIDE is re-tuned.
- A UKRAINIAN STYLE ANCHOR reference is updated in ways that change output style.

Not a new version (in-version edit allowed):

- Typo fixes.
- Clarification edits that do not change behaviour.

If in doubt, create a new version. Versions are cheap; silent drift is expensive.

---

## The prompt edit flow

Use the `agent-prompt-edit` skill. It enforces the following steps:

1. **Branch.** `feat/prompt-<agent>-<short-slug>`.
2. **Copy current active version to a new folder.** `prompts/<agent>/v<next>/`.
3. **Edit the new version.** Only the new folder changes.
4. **Write `notes.md`** in the new version folder: what changed, why, hypothesised effect, known risks.
5. **Run `calibration-run` skill** against the labelled dataset.
6. **Attach the calibration delta to the PR** (exact match, within-0.5, per-competency agreement vs previous version).
7. **PR review.** The reviewer sub-agent checks that no version was edited in place and that the calibration report is present.
8. **On merge:** bump `configs/models.yaml` to the new version in `dev` only.
9. **After smoke + dark-launch window in prod:** promote to `prod` in a follow-up PR.

Calibration metrics are **warning-only in CI** (constitution §13). A regression is a human decision, not an automatic block.

---

## What "a good prompt change" looks like

- Scoped to one concern. "Fix Ukrainian style drift" is one concern. "Add a new competency and rewrite guardrails" is two.
- Documented in `notes.md` with a testable hypothesis: "After adding the `off_topic_after_three_attempts` guardrail, the Interviewer should close off-topic questioning after three redirects."
- Calibration delta shows the intended metric moved and unrelated metrics did not move materially.
- Reviewed by someone other than the author, at least for the first 90 days of the project (while calibration intuition is being built).

---

## Anti-patterns

- **"Just be smart."** Telling the model to "use its best judgement" removes the exact constraint we need.
- **Three paragraph guardrails.** If a rule needs three paragraphs, it is underspecified.
- **Stacked clauses.** "If A and not B and possibly C, then do D unless E." Refactor into a decision tree.
- **Contradictions.** ROLE says "do not scold" and GUARDRAILS say "firmly redirect". Pick one.
- **Language soup.** Mixing English and Ukrainian inside a paragraph of instruction. Use sections, not mixtures.
- **Long JSON examples in the prompt.** Reference the schema; do not inline 50 lines of example JSON.
- **Including the rubric in the prompt.** The Assessor receives the relevant rubric nodes as input (`rubric_snapshot`), not baked into the prompt.
- **Unversioned ad-hoc edits.** Silent drift kills calibration.

---

## A minimal checklist before merging a prompt PR

- [ ] New version folder created; no existing version was edited.
- [ ] `notes.md` is present and describes what changed and why.
- [ ] All sections (ROLE through STYLE FOOTER) are present and non-empty.
- [ ] Every placeholder in the prompt is populated by the builder.
- [ ] Calibration run was executed and results are attached.
- [ ] Output examples at 2–3 representative candidate answers are attached.
- [ ] No new FORBIDDEN item contradicts a GUARDRAIL.
- [ ] Ukrainian output (if applicable) passes the language-consistency check.
- [ ] `configs/models.yaml` is updated for `dev` only — prod promotion is a separate PR.
