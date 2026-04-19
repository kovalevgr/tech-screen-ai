# ADR-018: Immutable rubric snapshots per session

- **Status:** Accepted
- **Date:** 2026-04-18

## Context

The rubric — the tree of competencies, sub-competencies, and scoring anchors — evolves. We refine descriptions, add new competencies, rename levels, merge nodes. Each change is made with care, but the change is real.

An interview conducted under rubric version **v5** must keep meaning the same whether we view it today or after rubric version **v9** ships. Otherwise:

- Historical calibration metrics become meaningless (agreement is computed against rubric that did not exist at the time).
- Reviewer overrides from past sessions become impossible to interpret.
- Legal / compliance requests ("what was the rubric when we rejected candidate X?") cannot be answered.

## Decision

- `rubric_tree_version` is an append-only, immutable entity in the database. A change to the rubric creates a new version, never mutates an existing one.
- `interview_session.rubric_snapshot` is a `JSONB` column containing the full, resolved rubric tree (every node, every anchor) as it existed at session start. This column is **NOT NULL**.
- The runtime Assessor agent loads rubric content from `rubric_snapshot`, not from the current `rubric_tree_version`.
- Reviewer UI displays per-session scores against the snapshot, never re-aligning old scores to a new rubric.

## Consequences

**Positive.**
- Enforces constitution §4 (immutable snapshots).
- Historical consistency: a 6-month-old session looks the same today as the day it happened.
- Calibration math across versions is apples-to-apples because each session carries its own rubric.

**Negative.**
- Storage cost: every session carries a ~5–20 KB JSONB copy of the rubric. For 10k sessions this is ~50–200 MB — trivial.
- Cross-session rubric analytics ("how did we score `concurrency` across Q1 vs Q2?") require aware joins that respect rubric differences.

**Mitigation.**
- Snapshot JSONB is GZIP-compressed by Postgres' TOAST layer — actual disk cost is smaller than the uncompressed size.
- Cross-version analytics are covered by `rubric_node.stable_id` — a stable identifier that persists across rubric renames, used for longitudinal queries.
