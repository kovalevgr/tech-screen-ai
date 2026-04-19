---
name: calibration-run
description: Run the Assessor (or other agent) against the labelled calibration dataset and produce an agreement report — per-competency exact-match, within-0.5, red-flag precision/recall, systematic bias, regression vs the prior run. Use whenever a prompt version, rubric tree version, or model version changes.
---

# calibration-run

You are measuring whether a change to a prompt, a rubric, or a model moved agent behaviour in a way you can defend. Calibration is how TechScreen knows the Assessor is not drifting.

Calibration is **warning-only** in CI (constitution §13, ADR-020). A regression does not block merge. But every prompt / rubric / model PR must attach a calibration report so a human can make an informed call.

## When to use this skill

- After editing a prompt version under `prompts/<agent>/v<N>/` (via `agent-prompt-edit`).
- After bumping `rubric_tree_version` (via `rubric-yaml`).
- After changing the model string in `configs/models.yaml` (e.g., gemini-2.5-flash → gemini-2.5-pro).
- Scheduled weekly, to catch upstream model drift with a stable prompt.
- Ad-hoc, when a reviewer reports a systematic miscalibration ("we keep over-rating L2 on python.concurrency").

## What calibration measures

The labelled dataset lives at `calibration/dataset/`. Each file is one labelled turn:

```yaml
# calibration/dataset/0042-python-concurrency-mid.yaml
turn_id: 0042
competency_focus: python.concurrency
prior_turns:
  - role: interviewer
    text_uk: "Як ви підходите до IO-bound роботи в Python?"
  - role: candidate
    text: "Обычно использую threading с ThreadPoolExecutor."
turn:
  role: candidate
  text: >
    Для IO я би взяв asyncio — він дозволяє обробляти тисячі конкурентних
    з'єднань одним event-loop потоком без GIL-контенції. Для CPU-bound —
    multiprocessing, бо GIL серіалізує чистий Python-код.
rubric_subset_version: 7
expected:
  assessments:
    - rubric_node_id: python.concurrency
      level: 3
      confidence_floor: 0.7
  red_flags: []
  needs_manual_review: false
labeller: "reviewer@n-ix.com"
labelled_at: "2026-03-12"
notes: >
  Clean Level 3 answer. Names the right tool for each workload, cites the GIL.
  Not L4 (no discussion of structured concurrency, no backpressure / cancellation).
```

The dataset starts small (~50 turns at MVP) and grows as reviewer corrections pile up. Each correction can be exported into a new labelled turn.

A calibration run, given a prompt version and a rubric snapshot, produces:

- **Exact-match rate** — fraction of turns where the Assessor's level exactly matched the label.
- **Within-0.5 rate** — fraction within half a level (counts L3 when expected L3, also counts L3 when expected is ambiguous L2.5 — the expected can be a half-step if the labeller said so).
- **Per-competency breakdowns** of the same.
- **Systematic bias** — average (Assessor level − expected level) per competency. Positive = over-rating, negative = under-rating.
- **Red-flag precision / recall** — relative to the `red_flags` list in the label.
- **Confidence calibration** — for turns where the Assessor reported confidence ≥ 0.8, what fraction were exact-match? If that number drops much below 0.8, the model is over-confident.
- **Delta vs prior run** — same metrics side-by-side with the last calibration run on the prior prompt / rubric version.

## The flow

### 1. Identify what you are calibrating

Set the three inputs explicitly:

```bash
AGENT=assessor
PROMPT_VERSION=v0004            # the NEW version, not the current active one
RUBRIC_VERSION=7                # current active; bump only if this PR changes it
```

Calibrating the new version against the old `models.yaml` is the normal case. Do not promote first and calibrate later.

### 2. Run

```bash
uv run python -m scripts.calibration_run \
    --agent "${AGENT}" \
    --prompt-version "${PROMPT_VERSION}" \
    --rubric-version "${RUBRIC_VERSION}" \
    --dataset calibration/dataset/ \
    --out calibration/reports/
```

The script:

- Loads every labelled turn.
- For each turn, calls the Assessor via the `vertex-call` wrapper using the specified prompt and rubric snapshot.
- Collects assessments, red flags, confidences.
- Writes a report markdown + a JSON of raw per-turn results to `calibration/reports/<agent>-<prompt>-<rubric>-<ts>/`.
- If a previous run exists for the prior prompt version on the same rubric version, includes the delta.

It does **not** mutate any session state. It does **not** count toward session cost caps (calibration cost is its own ledger). It does count toward the monthly LLM budget — a full MVP run is ~50 turns × $0.003 ≈ $0.15, so cheap.

### 3. Inspect the report

The report is one markdown file, something like:

```markdown
# Calibration — assessor v0004 vs rubric v7
Run: 2026-04-19T15:02Z
Dataset: 52 labelled turns

## Overall
| Metric              | v0003 (prior) | v0004 (new) | Δ |
|---------------------|---------------|-------------|---|
| Exact-match         | 0.62          | 0.68        | +0.06 |
| Within-0.5          | 0.83          | 0.88        | +0.05 |
| Red-flag precision  | 0.89          | 0.92        | +0.03 |
| Red-flag recall     | 0.71          | 0.79        | +0.08 |
| Over-confident rate | 0.14          | 0.09        | −0.05 |

## Per-competency
| Competency                     | n  | exact | Δ     | bias  |
|--------------------------------|----|-------|-------|-------|
| python.concurrency             | 8  | 0.75  | +0.12 | −0.10 |
| system-design.consistency      | 7  | 0.57  | +0.00 | +0.30 |
| databases.transactions         | 6  | 0.83  | +0.16 | −0.00 |
| distributed-systems.cap        | 5  | 0.40  | −0.20 | +0.40 |
| ...                            |    |       |       |       |

## Red flags
Precision: 0.92. Recall: 0.79.
- False positives (reported, labeller says no): 2
  - turn 0029 (system-design.caching) — Assessor flagged CONTRADICTION, labeller disagrees.
- False negatives (not reported, labeller says yes): 5
  - turn 0017 (databases.indexing) — FACTUALLY_WRONG missed.

## Regressions to review
- distributed-systems.cap — exact-match dropped 0.20. Five of five bias-positive (model rates higher than labeller). Worth reading before merge.
```

### 4. Decide

- **All green / flat / small improvement.** Proceed. Fill `notes.md` "Calibration delta" line. Attach the report to the PR.
- **Improvement on target metric, small regression elsewhere.** Document the trade-off in `notes.md` explicitly. A merge is fine if the author can articulate why the trade is acceptable.
- **Regression on a metric the change was supposed to improve.** Iterate. Do not merge. Open `notes.md`, record what you tried, bump to `v<NN+1>` or backtrack to the previous version.
- **Red-flag recall drops.** Take this seriously. False-negative red flags are the scariest failure mode — we miss a hallucination or a factual error. Do not merge without understanding why.

### 5. Attach

Link the report in the PR body:

```
Calibration report: calibration/reports/assessor-v0004-rubric-v7-2026-04-19T15:02Z/report.md
Summary: +0.06 exact-match, +0.08 red-flag recall, regression on distributed-systems.cap (see report).
```

The reviewer sub-agent checks for this link and blocks if missing.

## Dataset hygiene

- **One file per turn.** Filename `<ordinal>-<slug>.yaml`. Never reuse an ordinal.
- **Ground truth is human-set.** A labelled turn is signed off by a reviewer (the `labeller:` field).
- **Retire, don't delete.** If a label turns out wrong, add a new turn with the corrected expectation; mark the old one `retired: true` and note the reason.
- **Include the prior turns** (context) but keep the dataset's `prior_turns` short (last 4 is usually enough).
- **Cover the distribution.** At least 5 turns per top-level competency by the time the dataset reaches ~100. At MVP we accept thin coverage.
- **Do not optimise to the dataset.** If the Assessor calibrates perfectly but reviewers still disagree in prod, the dataset is too narrow. Grow it.

## CI behaviour

- CI runs `calibration-run` on every PR that changes `prompts/**`, `configs/rubric/**`, or `configs/models.yaml`.
- CI **does not block** on a regression. It emits a warning with the delta and links the report. Constitution §13.
- CI caches calibration per (agent, prompt_version, rubric_version, model, dataset_hash) tuple — if nothing changed, it reuses the last run.

## Cost and budget

- Typical MVP run: 50 turns × ~1 input-heavy call × gemini-2.5-flash ≈ $0.15.
- Dataset growth: linear in turn count.
- If calibration cost per month exceeds ~5 % of the monthly LLM budget, cache more aggressively or reduce weekly cadence.

## Common mistakes the reviewer will block

- Attaching a report generated from the wrong rubric version (e.g., the new prompt was run against last week's rubric snapshot). The tuple must match the PR.
- Manually editing the report markdown to hide a regression. Raw JSON is in the run folder; reviewer diffs JSON too.
- Running calibration on a smaller "fast" subset of the dataset in CI and claiming it as the PR's report. Full dataset for PR reports. Subset runs are acceptable for local iteration only.
- Promoting `configs/models.yaml` in the same PR as a change that regressed a metric without a written justification.

## References

- Constitution §13 (calibration warning-only), §16 (configs as code).
- ADR-020 (correctness variant A — what "exact-match" means given half-step labels).
- ADR-021 (configs as code).
- `docs/testing-strategy.md` — calibration layer.
- `prompts/<agent>/v<N>/notes.md` — where the Calibration delta line lives per run.
