# Feature Specification: Feature-flag infrastructure (T05a)

**Feature Branch**: `009-t05a-feature-flag-infrastructure`
**Created**: 2026-04-28
**Status**: Draft
**Input**: User description: T05a — Feature-flag infrastructure (§9 dark-launch enabler), per `docs/engineering/implementation-plan.md` Tier 1 / W1–W2

## User Scenarios & Testing *(mandatory)*

The "users" of this feature are humans and AI sub-agents that build every later risky feature (Tier 3 agents, Tier 5 WebSocket streaming, Tier 5 auto-save, Tier 6 reviewer UI write paths, etc.); the project owner / on-call operator who must be able to disable a misbehaving feature in under a minute without a deploy; the `reviewer` sub-agent that enforces §9 on every PR; and the GitHub Actions workflow that keeps the source-of-truth YAML and the production database in lockstep. T05a delivers the **mechanism** every later risky feature plugs into — it ships **no** end-user behaviour by itself.

### User Story 1 — A risky feature ships dark by default (Priority: P1)

A backend engineer (or backend-engineer sub-agent) is about to introduce a feature whose failure could degrade candidate experience, corrupt data, or inflate Vertex cost (constitution §9). They must be able to gate that feature on a single boolean, declared once, that **starts `false`** in production and stays `false` until someone explicitly flips it.

**Why this priority**: P1 because it is the entire point of T05a. Constitution §9 is a hard invariant; without this mechanism, every later Tier 3+ task that introduces an agent, a WebSocket channel, or an auto-save would silently violate §9. The reviewer agent has no way to enforce "is the risky feature behind a flag?" until flags exist.

**Independent Test**: A contributor declares a new flag in `configs/feature-flags.yaml` with `enabled: false`, adds a single `is_enabled("their_flag")` call in `app/backend/`, opens a PR that merges to `main`. After the post-merge sync workflow runs, a row exists in the `feature_flag` table with `enabled=false`, `updated_by='configs-as-code'`. A request that exercises the gated code path observes the feature OFF — without any other configuration step.

**Acceptance Scenarios**:

1. **Given** an empty `configs/feature-flags.yaml`, **When** a contributor adds a new entry `{name: "h1_rag", owner: "@andrii", default: false, description: "...", state: "active"}` and merges to `main`, **Then** the post-merge workflow inserts a row in `feature_flag` with `name="h1_rag"`, `enabled=false`, `updated_by="configs-as-code"`.
2. **Given** the row exists, **When** the backend evaluates `await is_enabled("h1_rag")`, **Then** the result is `false`.
3. **Given** the contributor merges code that calls `is_enabled("h1_rag_typo")` (typo) but only `h1_rag` is declared in YAML, **Then** the call raises a typed unknown-flag error rather than silently returning `false`.

---

### User Story 2 — An operator flips a flag without a deploy (Priority: P1)

An operator or the project owner needs to enable (or disable) a feature **between deploys** — either to roll out a green feature once smoke + calibration pass, or to disable a misbehaving feature during an incident. The change must take effect within seconds across all running backend instances, without rebuilding or redeploying the container.

**Why this priority**: Co-equal P1. Constitution §9 + §19 (rollback as a first-class operation, < 5 min) require that disabling a feature does not require a deploy. Without fast cross-instance propagation, a runaway feature keeps burning Vertex cost (§12) until a redeploy completes.

**Independent Test**: An operator opens a one-line PR changing `enabled: false → true` for an existing flag in `configs/feature-flags.yaml` and merges to `main`. The post-merge sync workflow updates the DB row. The next `is_enabled` call on each running backend instance observes the new value within 1 second of the DB write — **without any code change or restart**. Symmetrically: an emergency `UPDATE feature_flag SET enabled = false WHERE name = 'broken'` via direct SQL is observed by the backend in under 1 second.

**Acceptance Scenarios**:

1. **Given** a backend instance has cached `is_enabled("h1_rag") = false` (default), **When** an operator merges a PR setting `enabled: true` in YAML, **Then** the next `is_enabled("h1_rag")` on that instance returns `true` within 1 second of the sync workflow updating the DB row.
2. **Given** an incident requires immediate disable, **When** the operator runs a direct `UPDATE feature_flag` SQL, **Then** every running backend instance observes the new value within 1 second of the UPDATE committing.
3. **Given** multiple backend instances are running, **When** the DB row changes, **Then** each instance invalidates its own cache independently — no shared cache / no broadcast bus is required outside the database.

---

### User Story 3 — Unregistered flag usage is rejected before merge (Priority: P1)

The mechanism is only useful if it's **enforced**: a developer who calls `is_enabled("anything")` MUST be unable to merge unless `"anything"` is declared in `configs/feature-flags.yaml`. Symmetrically, removing the last call to a flag MUST not silently delete its history — the flag must be flipped to `state: sunset` and documented, never quietly dropped.

**Why this priority**: P1 because without bidirectional enforcement the registry drifts. Drift means: typo-flags silently default to "off" (the previous failure mode this exact mechanism exists to prevent), and sunset flags vanish from history (defeating audit). The same enforcement layer that catches a typo also keeps the audit trail honest.

**Independent Test**: Two fixture PRs. (a) A PR that adds `is_enabled("undeclared_flag")` in `app/backend/` without adding `undeclared_flag` to YAML is rejected by pre-commit locally **and** by the same check running in CI. (b) A PR that deletes the last `is_enabled("legacy")` call across the tree without flipping the `legacy:` YAML entry to `state: sunset` **and** adding a sunset row to the human-readable index is rejected by the same hook.

**Acceptance Scenarios**:

1. **Given** `configs/feature-flags.yaml` declares only `h1_rag`, **When** a contributor commits code containing `is_enabled("h1_rag_typo")`, **Then** the local pre-commit hook fails with a clear message naming `h1_rag_typo` and the YAML file to update, and the same check fails in CI.
2. **Given** the tree contains exactly one `is_enabled("legacy")` call and the YAML still has `legacy: state: active`, **When** a contributor removes that call, **Then** the pre-commit hook refuses the change unless the YAML entry is updated to `state: sunset` (with `sunset_pr` + `sunset_date`) AND a sunset row is added to the human-readable index.
3. **Given** a YAML entry is marked `state: sunset`, **When** a contributor opens any later PR, **Then** the YAML entry remains in the file (never deleted) so the audit trail survives.

---

### User Story 4 — Sunset history is preserved across the project's lifetime (Priority: P2)

Constitution §1 (auditability) and §16 (configs as code) require that the project can always answer "when did flag X turn on, who owned it, why was it sunsetted?" — months or years later. T05a must encode this from day one so the answer doesn't have to be reconstructed from git archaeology.

**Why this priority**: P2 because it serves long-tail audits, not the daily dark-launch loop. But the cost of NOT encoding it now is invisible debt (every removed flag silently erases its provenance), which is exactly the kind of thing §1 forbids.

**Independent Test**: After multiple flags have been added, flipped, and sunsetted, an operator can list every flag the project ever had (active + sunset) from a single committed file plus a single human-readable index, and trace each sunset entry back to the PR that retired it.

**Acceptance Scenarios**:

1. **Given** `legacy_thing` was sunsetted in PR #N on 2026-05-15, **When** an operator opens `docs/engineering/feature-flags.md` six months later, **Then** they see `legacy_thing` listed under sunset entries with `sunset_pr: #N` and `sunset_date: 2026-05-15`.
2. **Given** a sunsetted flag's DB row still exists, **When** the post-merge sync workflow runs, **Then** the row is left untouched (no auto-delete) and an "orphan row" warning is emitted as a workflow annotation for the operator to act on if they choose.

---

### Edge Cases

- **NOTIFY listener drops**: If the long-lived database listener loses its connection, the cache silently falls back to the 60-second TTL (correctness preserved, freshness degraded). The listener reconnects with exponential backoff; reconnects are logged but do not raise.
- **Workflow can't reach the DB**: The post-merge sync workflow fails loudly with a clear message and a non-zero exit; the merge stays merged in `main` but the DB drifts from YAML until the workflow succeeds on retry or a follow-up commit. The operator is notified (workflow failure surfaces in the standard CI channel).
- **YAML and DB drift "orphan"**: A flag present in the DB but absent from YAML is **never auto-deleted**; the workflow emits a warning annotation naming the orphan, and a human decides whether to re-add the entry (with `state: sunset`) or run a manual cleanup.
- **Concurrent flag flip during a request**: A request that has already read `is_enabled` before a flip uses the old value for the rest of that request; new requests after the cache invalidates use the new value. No cross-request consistency is promised.
- **Schema violation in YAML**: A commit that introduces a YAML entry violating the committed schema contract (e.g., missing `owner`, invalid `state` enum) is rejected by pre-commit and CI; the workflow never runs against a non-conforming YAML.
- **Direct DB write without YAML change** (emergency disable): Accepted; the next normal sync workflow will then mark the DB row as drifting from YAML and emit the orphan warning, which is the operator's cue to either reconcile or accept the divergence intentionally.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST persist every declared flag as a row in a `feature_flag` table with at minimum: a flag `name` (primary key), an `enabled` boolean (default `false`), an `owner` string, an optional `default_value` payload, an `updated_at` timestamp, and an `updated_by` string identifying the actor that last changed the row.
- **FR-002**: System MUST expose a single backend-side query function that takes a flag name (and optionally a session identifier reserved for future use) and returns the current boolean enabled state.
- **FR-003**: The query function MUST return a value reflecting the current database state within **1 second** of a DB write, **without** requiring a process restart, container redeploy, or external cache flush.
- **FR-004**: The query function MUST raise a typed "unknown flag" error when called with a name not present in `configs/feature-flags.yaml`. It MUST NOT silently default to `false`.
- **FR-005**: System MUST treat `configs/feature-flags.yaml` as the source of truth. The DB is a runtime mirror produced by the post-merge sync workflow; admin/UI mutations are deferred to a later phase and are explicitly out of scope.
- **FR-006**: System MUST validate `configs/feature-flags.yaml` against a committed JSON Schema contract on every commit. PRs that introduce a non-conforming YAML entry MUST be rejected locally (pre-commit) and in CI.
- **FR-007**: A post-merge workflow MUST, on every push to `main` that changes `configs/feature-flags.yaml`, diff the YAML against the DB and upsert rows so that **every YAML entry has a corresponding row** with `updated_by` set to a stable marker identifying the configs-as-code path (so direct-SQL emergency edits are distinguishable in audit).
- **FR-008**: The post-merge workflow MUST authenticate to the database without any committed credential, JSON service-account key, or other long-lived secret in the repository or workflow file (constitution §5 and §6).
- **FR-009**: System MUST NOT auto-delete a `feature_flag` row when its YAML entry is removed; orphan rows MUST be detected and surfaced as a non-fatal workflow warning, but the row stays until a human decides.
- **FR-010**: A bidirectional pre-commit hook MUST block: (a) any commit that introduces a query call referencing a flag name not declared in YAML; (b) any commit that removes the last query call referencing a flag whose YAML entry is not flipped to `state: sunset` (with a `sunset_pr` back-reference and `sunset_date`) AND whose sunset entry is not added to the human-readable flag index. The hook MUST run in CI as well so it cannot be bypassed by skipping local hooks.
- **FR-011**: Sunset flag entries MUST remain in `configs/feature-flags.yaml` and in the human-readable flag index indefinitely. Deletion of a sunset entry is treated as a constitution-§1 violation (audit history lost) and MUST be rejected by the same hook.
- **FR-012**: A human-readable flag index document MUST list every flag (active + sunset) with owner, default, current state, a one-line description, and — for sunset entries — the back-reference to the PR that retired the flag and the date.
- **FR-013**: The `feature_flag` table is explicitly **mutable** and is NOT subject to the constitution §3 append-only protections that apply to the six audit tables. The migration that creates it MUST NOT attach the `reject_audit_mutation()` trigger or `REVOKE UPDATE, DELETE` from the application role. This carve-out MUST be called out in code comments and migration docstring so a future contributor does not extend §3 protections to it by reflex.
- **FR-014**: System MUST expose, in the trace surface of any LLM call gated on a flag (T21 wires this in a later tier), the `name → enabled` resolution that was observed, so a session's gating decisions are auditable post-hoc. (T05a creates the surface for this; T21 wires the trace.)
- **FR-015**: The migration introducing `feature_flag` MUST be additive and forward-only (constitution §10). A reversible `downgrade()` exists for local/CI resets only.

### Key Entities

- **Feature flag** (runtime row): A binary on/off switch named in code, persisted as one row per flag in the database. Carries metadata (owner, last change time, last actor) used for audit and for the orphan-detection workflow. Mutable by design.
- **Feature-flag YAML entry**: The Git-tracked declaration that any runtime flag must have. Contains the flag's identity (`name`), accountability (`owner`), default behaviour, a short description, lifecycle `state` (`active` or `sunset`), and — when `sunset` — back-references to the PR/date that retired it. The schema of this entry is itself committed (FR-006).
- **Feature-flag index document**: The human-readable companion to the YAML. One section per flag, including a sunset table. Updated by every PR that adds or sunsets a flag.
- **Post-merge sync workflow**: The automation that observes YAML changes on `main` and reflects them into the database. Has no other responsibility; future tasks (T16 rubric sync) extend the same workflow file with parallel jobs.
- **Bidirectional registration hook**: The pre-commit/CI guard that keeps the YAML and the in-code call sites consistent in both directions (no orphan calls, no silently-deleted history).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A contributor can introduce a new dark-launched feature end-to-end (declare flag in YAML + add one call site + ship via PR) **in under 10 minutes** following the human-readable flag index document, without consulting any source code other than the document and the YAML schema.
- **SC-002**: After a YAML change merges to `main`, the database reflects the new state in under **5 minutes** (one workflow run, including queue time).
- **SC-003**: After the database reflects a change, every running backend instance returns the new value from its query function within **1 second** of the database write — measured by an integration test that updates a row and polls the query function.
- **SC-004**: **100% of in-code flag query calls in `app/backend/`** resolve to a name declared in `configs/feature-flags.yaml` — verifiable by running the registration hook against a clean tree and observing exit 0.
- **SC-005**: **100% of YAML entries with `state: sunset`** have a matching entry in the human-readable index with a non-empty `sunset_pr` back-reference and `sunset_date` — verifiable by the registration hook.
- **SC-006**: Five distinct fixture PRs exercising the failure modes (undeclared name; removed last call without sunset; sunset entry deleted; schema-violating YAML; workflow DB-unreachable) **all** fail at the documented gate, none reaches `main`.
- **SC-007**: An on-call operator can disable a misbehaving feature in **under 60 seconds** end-to-end from incident detection — measured by: (a) emergency SQL `UPDATE` takes < 5 seconds to execute, (b) cache invalidation on every backend instance completes within 1 second of the UPDATE, (c) the operator's runbook entry in the human-readable index is under 200 words.
- **SC-008**: The post-T05a tree carries **zero** new credentials in source control — verifiable by `gitleaks` and `detect-secrets` on the PR diff.
- **SC-009**: The `feature_flag` table has **no** trigger and **no** REVOKE on it that resembles the audit-table guard — verifiable by a positive test in the DB integration suite that asserts an `UPDATE feature_flag` from the application role succeeds.

## Assumptions

- The database is reachable from the GitHub Actions workflow via a network path that does not require a long-lived secret in the repo or workflow YAML (Workload Identity Federation binding from T01a is assumed present).
- The application role and the migrator role both exist with the privilege shapes T05 established. T05a does not extend or alter §3 protections; it explicitly carves out `feature_flag` from them.
- A single source-of-truth YAML file (`configs/feature-flags.yaml`) for all flags is acceptable at MVP scale (single-digit to low-tens of flags). Per-environment overrides are out of scope (constitution §8 — production is the only long-lived environment).
- A 60-second TTL is an acceptable correctness backstop when the NOTIFY listener is disconnected; the 1-second SLO for cache freshness (FR-003 / SC-003) applies only when the listener is healthy, which is the steady state.
- The post-merge sync workflow may take up to 5 minutes including CI queue time on a busy day; flag flips that demand faster propagation use the direct-SQL emergency path (covered by SC-007) rather than the workflow path.
- The choice of YAML/JSON-Schema validation library is an implementation detail to be settled in the planning phase research; the spec is library-agnostic.
- This feature ships the **mechanism**. The first real-world flag (e.g., an H2 RAG toggle in Tier 3) is wired by the consuming PR, not by T05a.
- The MVP query interface accepts an optional session-identifier argument but does NOT use it; per-session / per-user / percentage rollout is reserved for a future phase and explicitly out of scope.
- The post-merge sync workflow's `updated_by` marker is a single stable string (e.g., `"configs-as-code"`). Differentiating between human-PR-driven flips and other workflow-driven flips is out of scope; emergency direct-SQL writes set their own `updated_by` and so are distinguishable.

## Out of scope

- Admin UI for toggling flags (Phase 2). All MVP toggles happen via PR to the YAML or direct SQL for emergencies.
- Per-user, per-session, or percentage-based rollouts. The query surface reserves an argument for this future capability but the implementation is binary on/off.
- Multi-environment configurations (no staging — constitution §8). Production is the only environment that has a real flag-state row.
- Rubric configs-as-code synchronisation (T16). T05a ships the post-merge sync workflow file with a single feature-flag job; T16 adds a parallel rubric job to the same file.
- Wiring any specific feature flag to any specific call site. T05a delivers the mechanism; consumers (Tier 3+ tasks) wire their own flags in their own PRs.
- Any change to the six §3 append-only tables. The append-only invariant remains exactly as T05 established it.
