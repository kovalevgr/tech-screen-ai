# ADR-021: Configs as code — rubrics, prompts, flags in Git

- **Status:** Accepted
- **Date:** 2026-04-18

## Context

TechScreen has many "config-shaped" artefacts:

- Competency rubrics and scoring anchors.
- Position templates (C# Middle, React Senior, …).
- Agent system prompts.
- Feature flag defaults.
- Model selection and parameter configuration.

Two common approaches:

1. **Store in DB, edit via Admin UI.** Fast iteration, tempting for non-engineers, but:
   - Changes are not reviewable.
   - History is limited to whatever audit the Admin UI writes.
   - Re-creating a historical configuration for calibration replay is painful.
   - Diffs across environments are invisible.
2. **Store in Git as code.** Every change is a commit, reviewable, revertible, diffable.

## Decision

The **source of truth** for rubrics, position templates, prompts, and feature flag defaults is the Git repository, under `configs/` (rubrics, templates, flags) and `prompts/` (agent system prompts).

- Non-engineers can still edit via an Admin UI. UI edits write to corresponding DB tables and trigger a GitHub PR that exports the DB state to the `configs/` files. A human reviewer merges the PR — at which point the change is canonical.
- Runtime reads go to the DB table (fast), seeded from the Git-backed files on startup.
- A nightly drift checker compares DB state to Git state and warns on divergence.
- Calibration replays load configs from a specific Git commit — not from the current DB.

## Consequences

**Positive.**

- Every config change has a reviewable diff and an author.
- Historical configurations can be checked out and replayed exactly.
- Disaster recovery: if the DB is wiped, we re-seed from Git.

**Negative.**

- Two writes per UI edit (DB + Git PR) — more moving parts.
- Non-engineers must trust a Git-backed workflow they cannot directly inspect.

**Mitigation.**

- The "export DB to PR" step is one button in the Admin UI and is explained in the Admin guide.
- Config changes go through the same calibration loop as prompt changes — a config change that materially affects Assessor behaviour gets a calibration report in its PR.
