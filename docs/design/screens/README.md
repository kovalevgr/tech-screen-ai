# Screens

Per-screen design specifications. One folder per MVP screen, numbered in a rough funnel order.

Each screen folder contains:

- `spec.md` — prose specification (purpose, states, interactions, components used).
- `references/` — any reference screenshots, wireframes, or annotated captures (optional at spec time; populated during grooming).

The prose spec is authoritative. Screenshots support the prose but never replace it — Claude Code uses the prose as the fallback when images are unavailable or ambiguous.

---

## MVP screen inventory

### Candidate flow

| ID                       | Name                                                          | Status |
| ------------------------ | ------------------------------------------------------------- | ------ |
| `01-candidate-join`      | Magic-link landing; consent, name confirmation, session start | stub   |
| `02-candidate-session`   | Live session: dialogue pane, input, pause/help affordances    | stub   |
| `03-candidate-completed` | End of session; short thank-you + explanation of next steps   | stub   |

### Recruiter flow

| ID                             | Name                                                                            | Status |
| ------------------------------ | ------------------------------------------------------------------------------- | ------ |
| `10-recruiter-login`           | Google Workspace SSO sign-in                                                    | stub   |
| `11-recruiter-dashboard`       | List of sessions: filters, state chips, quick actions                           | stub   |
| `12-recruiter-plan-review`     | Pre-interview plan review: approve / request adjustments before candidate joins | stub   |
| `13-recruiter-session-monitor` | Live monitor: read-only view of an in-progress session                          | stub   |
| `14-recruiter-session-review`  | Post-session review: dialogue, assessments, corrections, audit                  | stub   |
| `15-recruiter-rubric-browser`  | Read-only browser of rubric versions / snapshots                                | stub   |

### Admin (internal, behind feature flag)

| ID                     | Name                              | Status |
| ---------------------- | --------------------------------- | ------ |
| `90-admin-flags`       | Feature flag toggles              | stub   |
| `91-admin-calibration` | Latest calibration report summary | stub   |

---

## Screen numbering

- `0x` — candidate-facing.
- `1x` — recruiter-facing.
- `9x` — admin-only / internal tooling.

Numbers are reserved, not sequential; we leave gaps (03, 11, 12) to allow future insertion without renumbering.

---

## Contract with Spec Kit

A `plan.md` that touches the frontend must reference the relevant `screens/<NN-xxx>/spec.md`. If the spec does not yet exist, the plan writes it first.

This makes screen specs the interface between "what should the feature look like" and "how does it render". They are also what the `reviewer` sub-agent checks against when deciding whether a frontend change is grounded.

---

## Document versioning

- v1.0 — 2026-04-18.
- Update this file when a screen is added, removed, or renumbered.
