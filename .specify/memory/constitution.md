# TechScreen Constitution

**Status:** Ratified 2026-04-18 · **Project:** TechScreen (internal AI technical screening) · **Owner:** Ihor

This document defines the **non-negotiable invariants** of the TechScreen project. Every plan, PR, ADR, and deploy must respect these principles. Changes to this document require an explicit ADR that supersedes the affected principle and a review from the project owner.

Invariants are ranked. When two principles conflict, the lower-numbered one wins.

---

## 1. Candidates and reviewers come first

The product exists to conduct fair, auditable technical interviews. Every other decision — model choice, cost optimisation, architectural elegance — is downstream of that purpose.

**Why.** We are replacing human interviewers for hiring decisions. A decision made by this system affects a real person's career.

**Enforcement.** Any change that trades auditability, fairness, or candidate experience for convenience must be rejected or escalated.

---

## 2. Deterministic orchestration

The interview flow is controlled by a deterministic Python state machine. **LLMs never decide "what happens next"** — they produce content and assessments inside states the orchestrator selects.

**Why.** LLM-driven orchestration makes sessions unreproducible, hard to debug, and impossible to replay for calibration.

**Enforcement.** No control-flow branches based on LLM free-text output. Routing may only use typed JSON fields (enums, booleans) produced by agents, validated against a schema, and logged to `turn_trace`.

---

## 3. Append-only audit trail

The following tables are append-only: `turn_trace`, `assessment`, `assessment_correction`, `turn_annotation`, `audit_log`, `session_decision`. Rows are never updated or deleted. Corrections are new rows that reference the corrected row.

**Why.** Hiring decisions can be challenged months later. We must be able to reconstruct exactly what the system said, what a reviewer overrode, and when.

**Enforcement.** No `UPDATE` or `DELETE` statements against these tables in application code. Database-level `REVOKE UPDATE, DELETE` on the application role. Reviewer corrections always produce a new `assessment_correction` row.

---

## 4. Immutable rubric snapshots

When an interview starts, the active `rubric_tree_version` is frozen into `rubric_snapshot` on the session. The runtime Assessor evaluates against the snapshot, never against the live rubric tree. Rubric edits never retroactively change old sessions.

**Why.** We change rubrics as we learn. Old assessments must keep their original semantics, otherwise historical calibration becomes meaningless.

**Enforcement.** `interview_session.rubric_snapshot` is `NOT NULL`. Assessor input loads rubric from `rubric_snapshot`, not from `rubric_tree_version`. Tests verify that editing a rubric node does not change scores on an existing session.

---

## 5. No plaintext secrets

Secrets never appear in source, logs, Docker images, LLM context, or any committed file. Locally, secrets live in `.env` files excluded by `.gitignore`. In production, secrets live in Google Secret Manager and are injected into Cloud Run at runtime.

**Why.** A leaked Vertex API key, DB password, or session signing key is a P0 incident. The cheapest way to prevent leaks is to never have the secret in a place it could leak.

**Enforcement.** `pre-commit` runs `gitleaks` and `detect-secrets`. CI blocks any PR that matches the secret regex allow-list. `.env.example` contains keys; secret keys carry empty values, and non-secret defaults (enums, public URLs, placeholder domains) are permitted — the `forbid-env-values` hook flags credential-shaped strings (PEM headers, JWTs, URLs with inline credentials, opaque strings ≥32 chars). See ADR-022. JSON service-account keys are not used anywhere — see §6.

---

## 6. Workload Identity Federation only

GitHub Actions authenticates to GCP via Workload Identity Federation (OIDC). Service-account JSON keys are not created, not stored, not rotated — they do not exist in this project.

**Why.** JSON keys are a permanent credential with no expiry and poor auditability. WIF is short-lived, per-run, and tied to a specific repo + branch.

**Enforcement.** `gcloud iam service-accounts keys create` is forbidden. The `terraform` service account's key policy disables key creation. Infra review on any PR that imports, references, or writes JSON keys.

---

## 7. Docker parity dev → CI → prod

Local development, CI, and production all run the same containers. A test that passes on a developer's machine but fails in CI is a sign that dev parity is broken, and dev is wrong.

**Why.** Drift between dev and prod produces bugs that appear only in production. We do not have a staging environment (see §8), so dev parity is our main pre-prod defence.

**Enforcement.** `docker-compose.yml` is the dev environment. `docker-compose.test.yml` is the CI environment. Dockerfiles are multi-stage and the `prod` target is the image deployed to Cloud Run. CI uses the same Compose files as dev.

---

## 8. Production is the only long-lived environment

There is no staging, no QA, no UAT. A single GCP project, `<PROJECT_ID>`, hosts production. Pre-prod testing happens locally via Docker; pre-release verification happens via Cloud Run revisions receiving 0% traffic.

**Why.** Staging drifts from prod, is expensive, and gives false confidence. Our compensating controls — Docker parity, dark launches, traffic splitting, calibration — are stronger than a stale staging environment would be.

**Enforcement.** No second GCP project for long-lived environments. Ephemeral preview revisions at 0% traffic are allowed and encouraged.

---

## 9. Dark launch by default

Any feature whose failure could degrade candidate experience, corrupt data, or inflate Vertex cost ships behind a feature flag that starts `false`. The flag is flipped on after smoke + calibration checks pass.

**Why.** Without staging, our risk management is per-feature, not per-deploy. Flags let us merge code in small steps without exposing users to half-built features.

**Enforcement.** Feature flags live in a `feature_flag` table (self-hosted, not LaunchDarkly). Reviewer agent blocks merge of risky features missing a flag. Flag names, owners, and default values are listed in `docs/feature-flags.md`.

---

## 10. Migration approval

Every Alembic migration runs `--sql` dry-run in CI. A human must approve the generated SQL before production apply. Migrations are forward-only and zero-downtime.

**Why.** A bad migration can corrupt the append-only audit trail (§3) or lock production tables. The cost of a human eye is cheap compared to that risk.

**Enforcement.** CI posts the dry-run SQL as a PR comment. `/deploy` refuses to proceed if the migration has not been approved (check-box or labelled review). Destructive DDL (`DROP COLUMN`, `DROP TABLE`, type-narrowing `ALTER`) triggers an extra ADR requirement.

---

## 11. Hybrid language

Agent system prompts, ADRs, constitution, glossary, docstrings, commit messages, and code comments are in **English**. Candidate-facing output from the Interviewer (questions, follow-ups, summaries visible to the candidate) is in **Ukrainian**.

**Why.** English system prompts perform measurably better on Gemini. Candidates interviewing for roles targeting Ukrainian speakers expect a Ukrainian interview experience.

**Enforcement.** Prompts include a `UKRAINIAN STYLE ANCHORS` section that constrains output language. Assessor operates on Ukrainian candidate text but produces English JSON fields. Language-switch tests run on every agent prompt change.

---

## 12. LLM cost and latency caps

Every LLM call has a hard 30-second timeout and a max-output-tokens cap (default 4096). Per-session aggregate cost is tracked in `turn_trace` and surfaced in the session view. A monthly Vertex budget alert fires at 50%, 90%, 100% of $50.

**Why.** A runaway agent loop can burn $100/hour. We detect it in minutes, not days.

**Enforcement.** `vertex-call` skill enforces timeouts and caps. Sessions whose cost exceeds a per-session ceiling (default $5) raise an alert and are flagged for review.

---

## 13. Calibration never blocks merge

Calibration runs (agreement between Assessor and reviewer labels) produce warnings in CI, never hard failures. The human reviewer decides whether to act.

**Why.** Prompt changes can move agreement metrics up or down for good reasons. A CI that blocks on calibration would make prompt iteration impossible.

**Enforcement.** Calibration CI step has `continue-on-error: true`. Calibration results are posted as a PR comment with trend vs. previous run.

---

## 14. Contract-first for parallel work

When a feature spans layers (backend + frontend, or two parallel backend modules) and sub-agents work in parallel, an OpenAPI spec or JSON schema must exist **and be committed** before the layer work starts.

**Why.** Parallel work without a contract produces merge conflicts and silent mismatches. We pay a small upfront cost to save a larger merge-time cost.

**Enforcement.** `docs/engineering/multi-agent-workflow.md` gates parallel fan-out on contract presence. Orchestrator refuses to dispatch parallel sub-agents without a referenced contract artefact.

---

## 15. PII containment

Candidate PII (name, email, CV, transcript text) lives only in designated tables (`candidate`, `interview_session`, `message`, `turn`). It is never copied into logs, metrics, trace exports, or LLM context outside the interview pipeline. Exports to analytics use pseudonymised IDs.

**Why.** GDPR + hiring regulations + internal policy. A PII leak is a regulatory incident.

**Enforcement.** Log formatters strip known PII fields. `audit_log` captures actor identity but not subject PII beyond a hashed reference. Exports and backups are encrypted at rest.

---

## 16. Configs as code

Rubrics, position templates, prompt versions, agent configurations, and feature flag defaults live in Git as YAML or Markdown. Runtime Admin UI edits are promoted to Git (export + PR) before being canonical.

**Why.** Auditable change history, reviewable diffs, and ability to re-create any historical configuration from a commit.

**Enforcement.** `configs/` directory is the source of truth. Admin UI writes to DB tables but the "official" version for calibration and replay comes from `configs/`. Drift checker compares DB vs. Git and warns.

---

## 17. Specifications precede implementation

No non-trivial feature is implemented without passing through `/specify` → `/plan` → `/tasks` → `/implement` (GitHub Spec Kit). Trivial changes (typo fixes, dependency bumps, formatting) may skip this.

**Why.** Specifications are the cheapest place to catch design problems. A 30-minute spec review saves 3-day refactors.

**Enforcement.** PR template requires a spec link for any feature PR. Reviewer agent blocks PRs that modify > 50 lines of production code without a spec reference.

---

## 18. Multi-agent orchestration is explicit

Sub-agent fan-out (parallel backend + frontend + infra) is decided by the human or the orchestrator Claude, declared in the plan, and approved before `/implement`. Automatic parallelisation without approval is forbidden on the MVP.

**Why.** We do not yet have enough data to trust an orchestrator's parallelisation heuristics. Wrong fan-out wastes tokens and creates merge conflicts.

**Enforcement.** `/plan` output labels every task with an `agent:` field. `/implement` refuses to fan out tasks not marked `parallel: true` in the plan.

---

## 19. Rollback is a first-class operation

Every deploy must be reversible in under five minutes without data loss. This constrains migration design, traffic policies, and feature flag lifecycles.

**Why.** When something breaks at 02:00, we roll back, then debug. We do not debug on a degraded production.

**Enforcement.** `/rollback` slash command shifts Cloud Run traffic to the previous revision in one call. Migrations are additive (§10). Feature flags can be disabled without a deploy.

---

## 20. This document is the floor, not the ceiling

These principles describe what must hold. They do not describe what must be built. Good engineering adds ideas this document does not mention; it does not remove the ones it does.

---

## Changing the constitution

1. Draft an ADR (`adr/NNN-change-principle-X.md`) explaining what is changing, why, and what replaces it.
2. Circulate to the project owner. If accepted, supersede the affected section here with a link to the new ADR.
3. Do not silently edit. Every change leaves a trail.

## Version

- **v1.0** — 2026-04-18 — Initial ratification.
