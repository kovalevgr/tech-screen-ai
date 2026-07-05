# Feature Specification: Configs-as-Code sync — rubric job (T16)

**Feature Branch**: `022-t16-rubric-sync`
**Created**: 2026-07-05
**Status**: Draft
**Input**: User description: T16 — Configs-as-Code sync (YAML → DB on merge) per `docs/engineering/implementation-plan.md` Tier 2. Extend the T05a/T06 flag-sync workflow with a second job `sync-rubric` that diffs `configs/rubric/` against the DB and applies validated changes via the T08 importer. Destructive changes (removed topic, retyped level) require an `ADR-xxx` citation in the triggering commit/PR body; otherwise the job fails. The two jobs run independently. After T16 the workflow owns ALL configs-as-code surfaces (§16).

## Clarifications

### Session 2026-07-05

- Q: May the workflow file be renamed now that it carries more than flags? → A: **Yes — `sync-configs.yml`**, provided every live reference is updated. Renaming is safe here: the workflow runs on `push` to `main` (never a required PR status check — those key off job names, not filenames), no other workflow references it via `workflow_run`/`workflow_call`, and `git log --follow` keeps file history. Cost accepted: the Actions UI groups old runs under the old workflow name (cosmetic). Historical spec records (`specs/009`, `specs/018`) keep the old name — they describe what was true then.
- Q: What exactly is "destructive" (the plan says "removed topic, retyped level")? → A: Anything that changes assessment semantics *going forward*: a node (topic/competency/block) flipped to `retired: true` (that IS "removal" in this codebase — specs/010 FR-009 forbids actual deletion), a node un-retired (ids are never reused after retire), a level rank removed from an active competency, or a level's `descriptor_en` changed ("retyped" — the descriptor is what the Assessor consumes; §11/ADR-008). Presentation-only edits (`label_uk`, `label_en`, `evidence_examples_en`, `version` integer) are benign. Deleting a stable id outright is FORBIDDEN, not merely destructive — no ADR can authorise it.
- Q: Where does the gate find the ADR citation in a push-triggered run (there is no `github.event.pull_request`)? → A: In the head commit message (via `git log`, works for merge and squash commits) **or** in the body/title of any PR associated with the head SHA, fetched via the `commits/{sha}/pulls` REST endpoint (`pull-requests: read` permission). Documented fallback: if the API call fails, the commit message alone decides. All of it flows through files/env — never interpolated into `run:` script text (untrusted input).
- Q: What baseline does the destructive diff use? → A: The push's `before` commit (`github.event.before`), extracted with git — not the DB, which stores neither `retired` flags nor labels, so a DB-derived baseline would be lossy. Fallback chain: unresolvable/zero `before` → `HEAD~1` with a warning → empty baseline (initial commit). The importer's DB-side rename rejection stays as the structural backstop.
- Q: The sync identity must write `audit_log` (specs/010 FR-010: one receipt row per version) — but §3 tables were "never granted" so far. → A: Grant **INSERT only** on `audit_log`. INSERT is the one verb §3 permits (append-only), the FR-010 receipt is a §1 auditability anchor we must not drop, and migration 0001's `reject_audit_mutation()` trigger keeps UPDATE/DELETE impossible for every role regardless of grants. The other five §3 tables get nothing.

## User Scenarios & Testing *(mandatory)*

The "users" of this feature are the rubric maintainers (interview engineers + the `prompt-engineer` agent) whose merged YAML edits must reach the runtime databases without manual SQL; the project owner/reviewer who needs destructive rubric changes to leave an ADR trail; and the operator (Ihor) who runs the one-time grants and wakes the cost-idled instances. T16 ships **no rubric content and no importer changes** — it ships the delivery pipe and its governance gate, completing the §16 story the T05a flag job started.

### User Story 1 — Benign rubric edit lands in both databases on merge (Priority: P1)

A maintainer edits a `label_uk`, adds a new competency, or adds a level in `configs/rubric/*.yaml` and merges to `main`. With the instances awake, the `sync-rubric` job seeds each environment: a new immutable `rubric_tree_version` (or a no-op when the payload hash is unchanged), prior versions untouched, one `audit_log` receipt row. No human touches a database.

**Why this priority**: This is the task — §16 says Git is the source of truth, and until T16 the rubric YAML only reached databases through a manually-invoked CLI.

**Independent Test**: Merge a label-only edit; watch both matrix legs go green; `SELECT count(*) FROM rubric_tree_version` incremented by one per environment, `audit_log` gained one `rubric.versioned` row each.

**Acceptance Scenarios**:

1. **Given** awake instances and a benign YAML diff on `main`, **When** the workflow runs, **Then** both `sync-rubric` legs succeed with a new `rubric_tree_version` per environment and prior-version rows byte-identical.
2. **Given** a merge that changes no rubric byte (e.g. flags-only change on the shared trigger paths), **When** `sync-rubric` runs, **Then** the seed is a hash-match no-op (zero rows inserted) and the job is green.
3. **Given** any successful seed, **Then** exactly one `audit_log` row (`action='rubric.versioned'`) exists per new version and none of the five other §3 tables were touched.

### User Story 2 — Destructive edits demand an ADR citation (Priority: P1)

A maintainer retires a topic or rewrites a level's `descriptor_en`. Unless the merged PR body or head commit message cites an `ADR-xxx` (regex `ADR-\d{3}`), the `sync-rubric` job fails **before any cloud step**, naming each destructive finding. With the citation present, the same change applies cleanly and the run annotates which ADR authorised it. Deleting a stable id outright fails no matter what — the error tells the maintainer to retire it instead.

**Why this priority**: Co-equal P1 — the gate is the governance half of the task. Without it, silent semantic drift of the rubric (what §4/ADR-018 versioning cannot see: *why* a level changed) is one merge away.

**Independent Test**: The gate is a pure YAML-vs-YAML comparison — `pytest app/backend/tests/contracts/test_rubric_sync_check.py` exercises benign / retired-topic / retyped-level / removed-id / ADR-authorised paths with no DB and no git.

**Acceptance Scenarios**:

1. **Given** a merged PR that flips a node to `retired: true` with no ADR reference anywhere, **When** the gate runs, **Then** the job fails with `NODE_RETIRED` naming the id, before WIF auth.
2. **Given** the same change with `ADR-024` in the PR body, **Then** the gate passes with a notice naming the citation, and the seed proceeds.
3. **Given** a diff that deletes a stable id from the payload, **Then** the job fails (exit 2, `NODE_REMOVED`) even when an ADR is cited, instructing retire-then-introduce (specs/010 FR-009).
4. **Given** a `descriptor_en` rewording of an existing level, **Then** the gate classifies it `LEVEL_RETYPED` and requires a citation; a `label_uk` edit on the same level does not.

### User Story 3 — The two config surfaces never block each other (Priority: P2)

A broken rubric payload (or a sleeping dev instance) must not stop flag defaults from syncing, and vice versa. The jobs share triggers but have no dependency edge; each matrixes `dev`+`prod` with `fail-fast: false`, so one red leg leaves the other three running.

**Acceptance Scenarios**:

1. **Given** a run where `sync-rubric (dev)` fails, **Then** `sync-feature-flags (dev/prod)` and `sync-rubric (prod)` still run to completion.
2. **Given** the workflow file, **Then** neither job declares `needs:` on the other.

### User Story 4 — Sleeping instances fail fast with a wake recipe (Priority: P2)

The Cloud SQL instances are STOPPED by default (cost-idle mode). When a maintainer merges without waking them, the DB steps must fail within seconds — not hang — and the failure annotation must contain the exact recovery: `scripts/cloud-sql-power.sh wake <env>`, then **Re-run failed jobs** (a re-run keeps the push's `before` SHA; a fresh `workflow_dispatch` degrades the gate baseline to `HEAD~1`).

**Acceptance Scenarios**:

1. **Given** a stopped instance, **When** `sync-rubric` reaches the seed step, **Then** it fails within the 20 s pre-flight timeout and the `::error::` annotation names the wake command for that matrix environment.
2. **Given** the failed run, **When** the operator wakes the instance and re-runs failed jobs, **Then** the re-run seeds successfully with the original destructive-gate baseline.

### Edge Cases

- **`workflow_dispatch` / unresolvable `before`** (force push, zero SHA): baseline falls back to `HEAD~1` with a workflow warning; for multi-commit pushes the documented recovery is re-running the failed run, which preserves the original event payload.
- **Initial commit / first sync**: empty baseline — every node is an addition, gate passes.
- **PR-list API failure**: warning emitted; the commit message alone is scanned for the citation (documented fallback).
- **Retiring a node that carries levels**: reported once as `NODE_RETIRED`; its level diffs are not double-reported.
- **File-level `retired: true`**: every node in the stack counts as retired — each previously-active node yields a `NODE_RETIRED` finding.
- **Rubric rows are never deleted**: there is no orphan concept here (unlike flags) — superseded content lives on under its old `rubric_tree_version` (§4/ADR-018), and retired ids persist in every new version forever.
- **Gate vs importer disagreement** (e.g. dev DB behind git because a previous sync failed): the gate is a git-diff policy layer; the importer re-checks disappeared ids against the actual DB per environment and refuses structurally.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The workflow MUST gain a second job `sync-rubric` in the same file as `sync-feature-flags`, with push triggers extended by `configs/rubric/**` and `docs/contracts/rubric.schema.json`; the jobs MUST be independent (no `needs:`), each matrixed `env: [dev, prod]` with `fail-fast: false`.
- **FR-002**: The workflow file MUST be renamed to `.github/workflows/sync-configs.yml` with every live reference updated (Terraform comments, `docs/engineering/cloud-setup.md`, `docs/engineering/feature-flags.md`, `docs/engineering/implementation-plan.md` notes, the flag-sync script docstring, and the workflow's own self-path trigger). Historical spec records keep the old name.
- **FR-003**: `sync-rubric` MUST reuse the T06 identity pattern unchanged: WIF auth as `techscreen-flag-sync@`, Cloud SQL Auth Proxy v2.13.0 with the pinned sha256, IAM DB user with the percent-encoded DSN username.
- **FR-004**: The job MUST validate `configs/rubric/*.yaml` against the committed schema (existing `scripts/check-rubric-schema.py`) before any other step touches the payload.
- **FR-005**: A destructive-change gate MUST run before any cloud step, comparing the working tree against the push's `before` commit and classifying: `NODE_RETIRED`, `NODE_UNRETIRED`, `LEVEL_REMOVED`, `LEVEL_RETYPED` (destructive — require citation regex `ADR-\d{3}` in the head commit message or associated PR bodies) and `NODE_REMOVED` (forbidden — always fails, retire instead, aligning with specs/010 FR-009). Untrusted event text MUST never be interpolated into `run:` blocks — commit messages via `git log`, PR bodies via `gh api`, both landing in files.
- **FR-006**: The sync step MUST apply changes via the T08 importer (`RubricImporter.seed`): schema re-validation, payload-hash no-op, a NEW immutable `rubric_tree_version` per content change, zero UPDATE/DELETE on any rubric row (§4/ADR-018), one `audit_log` receipt (INSERT only, §3/FR-010 of specs/010).
- **FR-007**: `scripts/cloud-db-grants.sql` MUST be extended with least-privilege grants for the sync identity: SELECT+INSERT on `rubric_tree_version`/`stack`/`competency_block`/`competency` (INSERT..RETURNING requires SELECT; `competency` is also read for the rename check), INSERT-only on `topic`/`level`, INSERT-only on `audit_log`, each grant justified in a comment; NO grant of any kind on the other five §3 append-only tables, and NO UPDATE/DELETE on any rubric table.
- **FR-008**: Against a stopped instance the sync MUST fail within a bounded pre-flight timeout (20 s) and the error MUST name the wake command for the failing environment and the re-run recovery path.
- **FR-009**: The destructive detector MUST be unit-testable without a database or git: fixtures for a benign edit, a removed (retired) topic, and a retyped level at minimum, runnable via `pytest`.
- **FR-010**: Documentation MUST record the all-surfaces ownership ("any future `configs/*` surface gets a third job here, not a new workflow") and the wake-the-DB-first rule, in `docs/engineering/cloud-setup.md` and the workflow header.

### Key Entities

- **Workflow** (`.github/workflows/sync-configs.yml`): the single §16 delivery pipe; two independent jobs, four matrix legs.
- **Destructive-change gate** (`scripts/sync_rubric_to_db.py check`): pure YAML-vs-YAML policy classifier + ADR-citation scanner; exit 0/1/2 contract in data-model.md.
- **Sync wrapper** (`scripts/sync_rubric_to_db.py sync`): thin CLI over `RubricImporter.seed` with the cost-idle pre-flight; no importer logic duplicated.
- **Grants** (`scripts/cloud-db-grants.sql`): the DB-privilege contract for the CI identity, now covering both surfaces.
- **Baseline snapshot**: the `configs/rubric/*.yaml` set at the push's `before` commit, extracted by the workflow into a temp dir — the gate's comparison anchor.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A benign rubric merge reaches both environments with zero manual steps (given awake instances): new `rubric_tree_version` per environment, prior rows untouched, one audit receipt each.
- **SC-002**: A destructive change without a citation fails the job before WIF auth with the finding named; adding `ADR-xxx` to the PR body (or commit message) and re-merging turns the same diff green.
- **SC-003**: Deleting a stable id fails the job regardless of citation, with retire-then-introduce guidance.
- **SC-004**: A failure in either job (or either matrix leg) never prevents the other job's legs from completing.
- **SC-005**: The detector test suite passes with no DB/git/network (`pytest app/backend/tests/contracts/test_rubric_sync_check.py`), and `pre-commit` (actionlint, shellcheck, gitleaks, rubric-schema, ruff) is green on every changed file.
- **SC-006**: No new secret, no JSON key, no unpinned binary: WIF-only auth and the sha256-pinned proxy are byte-identical to the flags job pattern.
- **SC-007**: Against a stopped instance the failure annotation appears within ~60 s of the seed step starting and contains the literal wake command for that environment.
