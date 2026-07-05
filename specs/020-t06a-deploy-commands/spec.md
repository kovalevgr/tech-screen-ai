# Feature Specification: Deploy commands — `/deploy` + `/promote` + `/rollback` (T06a)

**Feature Branch**: `020-t06a-deploy-commands`
**Created**: 2026-07-05
**Status**: Draft
**Input**: User description: T06a — `/deploy` + `/promote` + `/rollback` per `docs/engineering/implementation-plan.md` Tier 1 / W1–W2 and constitution §19. Three GitHub Actions `workflow_dispatch` workflows build the `runtime` Docker targets, push immutable image tags to Artifact Registry, deploy Cloud Run revisions at **0 % traffic**, smoke-test the revision-specific URL, and shift/roll back traffic on operator command. The §10 migration gate (T10's `migration-approved` label) is enforced at deploy time. A dedicated CI identity (`techscreen-deployer@`) is authored in Terraform with least-privilege roles, WIF-bound — no JSON keys, no static secrets (§5–6). Both environments (`dev`, `prod` — ADR-023) are first-class targets.

## User Scenarios & Testing *(mandatory)*

The "users" of this feature are: the operator (Ihor) who ships and un-ships code; the reviewer who audits every traffic movement after the fact; T11's Tier-1 smoke, which deploys to `dev` via `/deploy`; and every later application task, which inherits this release path instead of inventing its own. T06a delivers the **command surface and CI identity** for releases — it does not change what runs inside the containers, and it does not apply database migrations (see Out of scope and research D2).

### User Story 1 — Operator deploys a merged ref to a 0 %-traffic revision (Priority: P1)

The operator runs the `Deploy` workflow (`gh workflow run deploy.yml -f env=… -f service=… -f git_ref=…`). The workflow builds the `runtime` Docker target(s) for `linux/amd64`, pushes them to Artifact Registry under an immutable `<git-sha>-<env>` tag, creates a new Cloud Run revision per service with `--no-traffic` (existing traffic untouched), assigns the `candidate` revision tag, runs an HTTP smoke against the tag-specific URL, and writes the revision name, image, URL, and smoke result to the workflow job summary. Live users never see the new revision until `/promote`.

**Why this priority**: P1 — this is the release path itself (ADR-012). Every acceptance criterion in implementation-plan T06a maps here, and T11 is blocked on it.

**Independent Test**: `gh workflow run deploy.yml -f env=dev -f service=frontend -f git_ref=main`; the run goes green, `gcloud run services describe techscreen-frontend-dev` shows a new revision at 0 % traffic carrying the `candidate` tag, and the job summary names the revision and the smoke verdict.

**Acceptance Scenarios**:

1. **Given** a merged `main` at SHA `S`, **When** the operator dispatches Deploy for `dev`/`both`/`S`, **Then** Artifact Registry contains `backend:S-dev` and `frontend:S-dev`, both services have a new 0 %-traffic revision, and prior traffic percentages are unchanged.
2. **Given** the new revision, **When** the smoke step runs, **Then** it polls the `candidate` tag URL (backend `/health` expecting `"status":"ok"`; frontend `/` expecting HTTP 200) within a 60-second budget and the verdict lands in the job summary.
3. **Given** `env=prod` and a `git_ref` **not** reachable from `main`, **When** the workflow runs, **Then** the gate job fails before anything is built ("prod deploys must come from main history").
4. **Given** a smoke failure, **When** the run finishes, **Then** the run is red, the summary says so, and traffic is still 100 % on the previous revision — nothing to undo.

---

### User Story 2 — Operator rolls back in one call, in minutes (Priority: P1)

Something is wrong after a promote. The operator runs the `Rollback` workflow for the affected env/service. The workflow finds the revision that was serving before the current primary (or takes an explicit revision input), shifts 100 % of traffic to it in a single `gcloud run services update-traffic` call, measures the wall-clock of the shift, and reports revision-from/revision-to/duration in the job summary. Constitution §19 requires reversal in under five minutes; ADR-012's working target for the traffic call itself is 30–60 seconds.

**Why this priority**: P1 — §19 says rollback is a first-class operation; the implementation plan's acceptance measures it end-to-end on `dev`.

**Independent Test**: On `dev` with two revisions (after a deploy + promote 100), `gh workflow run rollback.yml -f env=dev -f service=backend`; the run is green, traffic is 100 % on the older revision, and the summary reports a measured duration.

**Acceptance Scenarios**:

1. **Given** revision R2 serving 100 % and R1 the previous server, **When** Rollback is dispatched, **Then** traffic is 100 % on R1 in one `update-traffic` call and the measured duration is printed (target ≤ 60 s; hard §19 ceiling 5 min end-to-end).
2. **Given** an explicit `revision` input, **When** Rollback runs, **Then** that revision (after a readiness check) receives 100 % — the auto-detection is bypassed.
3. **Given** a Deploy or Promote in flight for the same environment, **When** Rollback is dispatched, **Then** the in-flight run is cancelled (shared concurrency group, `cancel-in-progress`) and the rollback proceeds — rollback preempts.

---

### User Story 3 — Operator ramps traffic in observed steps (Priority: P2)

After a green deploy, the operator runs the `Promote` workflow with `percent=10`, observes dashboards per the playbook, then `50`, then `100`. Each run resolves the service's **latest ready revision by name** and pins that name at the requested percentage (never the floating `LATEST` allocation — research D8); the remainder redistributes across currently-serving revisions. The job summary shows the before/after traffic split.

**Why this priority**: P2 — the deploy is useless without a ramp, but promote is mechanically the simplest of the three commands and depends on US1 existing.

**Independent Test**: After a US1 deploy on `dev`, `gh workflow run promote.yml -f env=dev -f service=frontend -f percent=10` puts 10 % on the new revision and 90 % on the old; `percent=100` completes the cutover.

**Acceptance Scenarios**:

1. **Given** a candidate revision at 0 %, **When** Promote 10 runs, **Then** the candidate serves 10 % (pinned by revision name) and the previous primary serves 90 %.
2. **Given** the latest *created* revision is not the latest *ready* revision (a failed deploy exists), **When** Promote runs, **Then** it promotes the latest **ready** revision and the summary warns about the newer failed one.
3. **Given** the target revision already serves 100 %, **When** Promote 100 runs, **Then** the run succeeds as a no-op and says so.

---

### User Story 4 — §10 migration gate blocks unapproved schema changes (Priority: P2)

A ref that includes commits touching `alembic/versions/**` may only deploy if the PR(s) that carried those commits hold the `migration-approved` label (T10's mechanic). The Deploy gate diffs the target ref against the **currently deployed backend image's git SHA** (parsed from the image tag); when no deployed SHA is available (placeholder image, or a tag not in history), it falls back to `origin/main~1`. On violation the run fails loudly, naming the offending files, commits, and unlabelled PRs.

**Why this priority**: P2 — constitution §10's deploy-side half. T10 shipped the label + SQL-render side; implementation-plan T06a explicitly defers this wiring to "after T10", and T10 is merged — so it ships here, in the same PR as `/deploy` itself.

**Independent Test**: Dispatch Deploy for a fixture branch that adds a file under `alembic/versions/` whose PR lacks the label → the gate job fails with the file, commit, and PR number in the error. Apply the label, re-run → gate passes.

**Acceptance Scenarios**:

1. **Given** a target ref whose diff-from-baseline touches `alembic/versions/`, **When** no associated PR carries `migration-approved`, **Then** the gate fails before any build/push and the error names files + commits + PRs.
2. **Given** the same ref after the label is applied, **When** Deploy re-runs, **Then** the gate passes.
3. **Given** a migration commit with **no** associated PR (direct push), **When** Deploy runs, **Then** the gate fails — there is nothing to have approved.
4. **Given** a redeploy of the already-deployed SHA, **When** Deploy runs, **Then** the diff is empty and the gate passes without API calls.

---

### User Story 5 — Cost-idle guard: fail fast when the database is asleep (Priority: P3)

The Cloud SQL instances are kept stopped (`activationPolicy=NEVER`) between work sessions to save cost. The Deploy gate checks the target environment's instance state; when the instance is asleep **and** a deploy step actually needs the database (today: backend revision startup **iff** the service template wires `DATABASE_URL` — see research D11), the run fails immediately with: *"instance is asleep — run `scripts/cloud-sql-power.sh wake <env>`"*. When the DB is asleep but no step needs it, the gate emits a notice and continues.

**Why this priority**: P3 — a convenience guard that converts a confusing 5-minute readiness-probe timeout into a 5-second actionable error. It protects nothing the smoke wouldn't eventually catch.

**Independent Test**: With `techscreen-pg-dev` set to `activationPolicy=NEVER` and `DATABASE_URL` wired into the dev backend template, Deploy for `dev`/`backend` fails in the gate with the wake message; with the wiring absent (today's reality), the same dispatch proceeds with a notice.

**Acceptance Scenarios**:

1. **Given** an asleep instance and a backend template that references `DATABASE_URL`, **When** Deploy targets backend or both, **Then** the gate fails with the wake instruction naming `scripts/cloud-sql-power.sh`.
2. **Given** an asleep instance and no `DATABASE_URL` wiring, **When** Deploy runs, **Then** a notice explains which steps *would* need the DB (backend startup once wired; operator-run migrations) and the deploy proceeds.

---

### Edge Cases

- **Placeholder baseline**: both services still run `us-docker.pkg.dev/cloudrun/container/hello`; the first real deploy has no deployed-SHA baseline → migration gate falls back to `origin/main~1` (documented, honest heuristic — research D7).
- **Backend cannot boot yet (known gap, out of scope to fix here)**: the T06 Cloud Run template sets **zero env vars**, and the `runtime` image bakes `APP_ENV=prod` while `LLM_BACKEND` defaults to `mock` — `Settings.assert_safe_for_environment()` raises at startup, so the first *backend* deploy will fail its readiness probe until a follow-up Terraform change wires `LLM_BACKEND=vertex` (+ `DATABASE_URL` secret ref + Cloud SQL attachment). `/deploy` surfaces this loudly at the deploy step; the frontend path is unaffected. See research D12 and quickstart §5.
- **Terraform template ownership**: T06's `ignore_changes` covers only `image`, `client`, `client_version`, `scaling` — so `/deploy` changes **nothing but the image** (plus `--port`, whose `ports` field the provider treats as computed; the quickstart schedules a post-first-deploy `terraform plan` zero-diff verification). Env vars, secrets, SQL attachments stay Terraform-owned.
- **Single-serving-revision promote**: `percent<100` when only one revision serves traffic → `gcloud` cannot distribute the remainder and errors; the summary explains (deploy first, then promote).
- **Revision-tag reuse**: the `candidate` tag is *moved* to each new revision via `update-traffic --update-tags` (not `deploy --tag`), so tags never accumulate and never collide.
- **Immutable tags by convention**: Artifact Registry tags embed the full 40-hex git SHA + env; the repository-level immutable-tags toggle is a Terraform follow-up (touches `artifact_registry.tf`, out of this task's file scope — research D3).
- **Concurrent operations**: all three workflows share the concurrency group `cloud-run-<env>`; deploy/promote queue, rollback preempts (`cancel-in-progress: true`).
- **Cold start on smoke**: `min_instances=0` means the first tag-URL request cold-starts the revision; the smoke retries within its 60 s budget.
- **Frontend images are env-specific**: `NEXT_PUBLIC_API_BASE_URL` is inlined at build time, fetched live from the target env's backend service URL — hence per-env tags are not just provenance, they are different bytes.
- **Untrusted input**: `git_ref` and `revision` are free-text `workflow_dispatch` inputs; they reach shell steps only via `env:` mappings, never inline `${{ }}` in `run:` blocks.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide `.github/workflows/deploy.yml` with `workflow_dispatch` inputs `env` (choice: `dev`|`prod`), `service` (choice: `backend`|`frontend`|`both`), and `git_ref` (free text, default `main`), authenticating to GCP exclusively via WIF (`id-token: write`, `google-github-actions/auth@v2` impersonating `techscreen-deployer@`) — no JSON keys, no repository secrets.
- **FR-002**: Deploy MUST build the `runtime` Docker target of each selected service for `linux/amd64` and push to `europe-west1-docker.pkg.dev/tech-screen-493720/techscreen/<service>` under the immutable tag `<full-git-sha>-<env>`; the frontend build MUST receive `NEXT_PUBLIC_API_BASE_URL` (the target env's live backend URL) and `NEXT_PUBLIC_APP_ENV` as build args.
- **FR-003**: Deploy MUST create the new Cloud Run revision with `--no-traffic` and a unique revision suffix, change **only** the image (and container port: backend 8000, frontend 3000) relative to the Terraform-owned template, move the `candidate` revision tag to the new revision, and leave existing traffic assignments untouched.
- **FR-004**: Deploy MUST smoke the revision-specific (tag-based) URL — backend `GET /health` expecting HTTP 200 with `"status":"ok"`, frontend `GET /` expecting HTTP 200 — within a 60-second retry budget, and MUST write revision name, image tag, tag URL, and smoke verdict to the GitHub job summary for success **and** failure.
- **FR-005**: Deploy MUST enforce the §10 migration gate before building: compute the changed set of `alembic/versions/**` between the deploy baseline (git SHA parsed from the currently-deployed backend image tag; fallback `origin/main~1` when unavailable) and the target ref; for every commit in that set, at least one associated PR must carry the `migration-approved` label; otherwise fail loudly naming files, commits, and PRs. Commits with no associated PR fail the gate.
- **FR-006**: Deploy MUST refuse `env=prod` for any `git_ref` not reachable from `origin/main` (ancestry check in the gate job, before any cloud mutation).
- **FR-007**: Deploy MUST check the target environment's Cloud SQL instance (`techscreen-pg`/`-dev`) state before deploying; if the instance is not `RUNNABLE` with `activationPolicy=ALWAYS` **and** the backend service template wires `DATABASE_URL` while backend is being deployed, it MUST fail with the message *"instance is asleep — run `scripts/cloud-sql-power.sh wake <env>`"*; otherwise it MUST emit a notice documenting which steps need the DB (backend revision startup once `DATABASE_URL` is wired; operator-run migrations).
- **FR-008**: System MUST provide `.github/workflows/promote.yml` with inputs `env`, `service`, `percent` (choice: `10`|`50`|`100`) that resolves the service's latest **ready** revision name and pins it at the requested percentage via one `gcloud run services update-traffic --to-revisions` call (never the floating `LATEST` allocation), reporting before/after traffic splits in the job summary.
- **FR-009**: System MUST provide `.github/workflows/rollback.yml` with inputs `env`, `service`, and optional `revision` that shifts 100 % of traffic to the previous serving revision (auto-detected as the newest ready revision older than the current primary, unless overridden) in a single `update-traffic` call, measures the shift's wall-clock, and reports from/to/duration in the job summary. Rollback MUST preempt in-flight deploy/promote runs for the same environment.
- **FR-010**: System MUST author (never apply) Terraform in `infra/terraform/iam.tf`: a `techscreen-deployer` service account, a WIF binding using the same repository-pinned principalSet as `techscreen-flag-sync@`, and least-privilege grants — `roles/run.developer` (project), `roles/artifactregistry.writer` **on the `techscreen` repository only**, `roles/cloudsql.viewer` (project, read-only, for the asleep guard), and `roles/iam.serviceAccountUser` **on the four runtime SAs only** (SA-level bindings, never project-level). Each role is justified in research.md.
- **FR-011**: System MUST ship `scripts/cloud-sql-power.sh` (`wake`|`sleep`|`status` × `dev`|`prod`) — the operator helper the FR-007 message references; it patches `activationPolicy` and reports instance state, and is never executed by CI.
- **FR-012**: System MUST update `docs/engineering/deploy-playbook.md` from descriptive to implemented reality — exact workflow names/inputs and `gh workflow run` invocations, the wake-the-DB rule, migration-gate mechanics, and an honest "not yet implemented" list (deploys audit table, ChatOps trigger, live-session drain, revision cleanup) — and bump its version block.
- **FR-013**: No workflow may interpolate free-text `github.event.*`/`inputs.*` values inline in `run:` blocks (env-mapping only), and every changed file MUST pass the repo pre-commit chain (actionlint, shellcheck, gitleaks, terraform_validate, forbid-env-values).

### Key Entities

- **Deploy workflow** (`deploy.yml`): gate job (ancestry, migration gate, DB guard) + per-service matrix deploy job (build → push → deploy 0 % → tag → smoke → summary).
- **Promote workflow** (`promote.yml`): pinned-revision traffic shift, per-service matrix.
- **Rollback workflow** (`rollback.yml`): previous-revision resolution + one-call shift + timer.
- **Deployer identity** (`techscreen-deployer@`): WIF-bound CI SA; role matrix in data-model.md.
- **Image tags**: `<service>:<full-sha>-<env>` in Artifact Registry `techscreen` — the provenance link the migration gate parses back out.
- **`candidate` revision tag**: stable, per-service pointer to "the revision smoke ran against"; the tag URL is the smoke surface.
- **`scripts/cloud-sql-power.sh`**: operator-side cost-idle lever the FR-007 guard points at.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: `pre-commit run --files <changed>` passes — actionlint and shellcheck accept all three workflows and the power script; gitleaks and forbid-env-values find nothing; `terraform validate` accepts the extended `iam.tf`.
- **SC-002**: A Deploy dispatch on `dev` produces: two immutable AR tags, a 0 %-traffic revision per service carrying `candidate`, an unchanged prior traffic split, and a job summary naming revision + smoke verdict. *(Live; recorded in quickstart §6.)*
- **SC-003**: Rollback on `dev` completes green with a measured `update-traffic` duration ≤ 60 s and end-to-end workflow wall-clock ≤ 2 min (implementation-plan T06a acceptance; §19 ceiling 5 min). *(Live.)*
- **SC-004**: A fixture ref touching `alembic/versions/` without the `migration-approved` label fails the gate with files/commits/PRs named; the same ref passes after labelling. *(Live.)*
- **SC-005**: Zero new secrets anywhere: no repository/environment secrets added in GitHub, no JSON keys, gitleaks clean; the only new cloud identity is `techscreen-deployer@` with exactly the FR-010 role set (`gcloud projects get-iam-policy` + per-SA policy diff). *(Live after apply.)*
- **SC-006**: `terraform -chdir=infra/terraform plan` shows **only** the deployer SA + its five bindings as additions; after apply, a repeat plan is zero-diff. *(Live.)*
- **SC-007**: `docs/engineering/deploy-playbook.md` v2.0 names the exact workflows/inputs; a reviewer can execute a dev deploy from the playbook alone without reading the YAML.
- **SC-008**: With the target instance set to `activationPolicy=NEVER`: the guard emits its notice (today's unwired template) or blocks with the wake message (once `DATABASE_URL` is wired) — verified once on `dev`. *(Live.)*

## Assumptions

- **T06 is fully applied and live** (verified 2026-07-05 context): four Cloud Run services on the placeholder image, Artifact Registry `techscreen`, WIF pool `github-actions`/provider `github` pinned to `kovalevgr/tech-screen-ai`, per-env runtime SAs. The deployer SA is *additive* Terraform; the operator applies it before the first dispatch (quickstart §2).
- **Cost-idle mode is live but previously untooled**: both Cloud SQL instances are stopped by default. No committed script or doc section described this before T06a; `scripts/cloud-sql-power.sh` + the playbook section close that gap (research D10).
- **Migrations are operator-run at MVP** (research D2): `/deploy` never applies Alembic migrations; the §10 gate at deploy time checks *approval*, the operator applies SQL via the Auth Proxy with the rotate-on-demand migrator password (specs/018 quickstart §4/§6 pattern).
- **The §10 label mechanic exists**: T10's `ci.yml` renders migration SQL to a PR comment and humans apply `migration-approved`. T06a consumes the label; it does not create it.
- **Task-order deviation, declared**: implementation-plan T06a says "ship `/deploy` without the check, then extend after T10" — T10 is already merged, so the gate ships *in* this PR rather than as a follow-up. Same plan intent, fewer PRs.
- **Job summary instead of PR comment**: the implementation plan (written pre-T10) says "reports result in PR comment"; `workflow_dispatch` runs are not bound to a PR, so the run's job summary is the report surface (research D5).
- Sequential single-agent execution (repo default); `infra-engineer` profile work, one PR, `parallel: false`.

## Out of scope

- **Applying Alembic migrations from CI** — decided against for MVP (research D2); operator-run via Auth Proxy stays the mechanism.
- **Fixing the backend env-wiring gap** (`LLM_BACKEND`/`DATABASE_URL`/Cloud SQL attachment in the Cloud Run template) — a named follow-up Terraform change; T06a documents the failure mode it causes (quickstart §5).
- **ChatOps trigger** (`/deploy` typed in a PR comment) — `gh workflow run` is the MVP invocation; the slash-command names survive as playbook verbs.
- **`deploys` audit table** — audit = workflow run history + job summaries + Cloud Run revision history at MVP; the table lands with the first backend task that owns ops tables.
- **Revision cleanup job** (`/deploy cleanup`, ADR-012's 7-day pruning) and the live-session drain check — future tasks; both stay listed in the playbook as not-yet-implemented.
- **Artifact Registry repository-level immutable-tags toggle** — Terraform follow-up touching `artifact_registry.tf`.
- **Monitoring dashboards / alert wiring for deploys** — T38.
- Any change to application code, Dockerfiles, compose files, or migration content.
