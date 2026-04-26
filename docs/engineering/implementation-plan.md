# TechScreen — Implementation Plan (MVP, W1–W12)

**Version:** 1.0 · **Date:** 2026-04-19 · **Owner:** Ihor

Audience: Claude Code orchestrator and sub-agents (`backend-engineer`, `frontend-engineer`, `infra-engineer`, `prompt-engineer`, `reviewer`).

This document is the authoritative task breakdown for the 12-week MVP build. It follows the Spec Kit `/plan` convention described in [`CLAUDE.md`](../../CLAUDE.md) — every task carries explicit `agent:`, `parallel:`, `depends_on:`, `contract:`, and `acceptance:` fields so the orchestrator can fan out safely and `reviewer` can gate merges.

---

## 0. How to read this document

- **Tiers** map 1:1 to calendar weeks from [`docs/specs/mvp-scope.docx`](../specs/mvp-scope.docx) (W1 → Tier 1, W12 → Tier 12).
- **Task IDs** are stable: `T01`..`TNN`. Do not renumber; append instead.
- **`agent:`** is one of `backend-engineer`, `frontend-engineer`, `infra-engineer`, `prompt-engineer`, `orchestrator` (main Claude), or `human` (Ihor — business/ops decisions).
- **`parallel: true`** means this task can run concurrently with others in the same tier that also declare `parallel: true`, **provided the contract it depends on is already committed.** No contract → fan-out disabled (constitution §14, ADR-014).
- **`contract:`** points to the committed spec (OpenAPI path, JSON schema path, or `none`) that unblocks parallel work.
- **`depends_on:`** lists task IDs that must be `completed` before this task starts.
- **`acceptance:`** is the closure test. If `reviewer` cannot tick every bullet, the task is not done.

The floor that every sub-agent reads before touching a task in this plan:

1. `.specify/memory/constitution.md` — 20 invariants.
2. `adr/` — 21 decisions.
3. `docs/engineering/anti-patterns.md`, `docs/engineering/coding-conventions.md`, `docs/engineering/testing-strategy.md`.
4. For frontend PRs: `docs/design/principles.md`, `docs/design/tokens/colors.md`, and both `docs/design/references/*.png`.

Every sub-agent PR is gated by `reviewer` (`.claude/agents/reviewer.md`). A task is closed only after reviewer returns ✅.

---

## Tier 1 (W1–W2) — Foundation & Setup

**Goal:** team can write, test, and deploy code. Vertex is reachable from the backend. No product features yet — pure infrastructure.

**Entry criteria:** GCP project + billing approved · GitHub repo created · Google Workspace SSO group ready · Ihor available for one-off bootstraps.

### T00 — Initialize Spec Kit scaffolding

- **agent:** `human` (Ihor — local CLI on his Mac; sandbox has no PyPI/GitHub egress)
- **parallel:** false (pre-flight; every later task assumes Spec Kit commands exist)
- **depends_on:** []
- **contract:** none
- **description:**
  [`CLAUDE.md`](../../CLAUDE.md) and [ADR-017](../../adr/017-spec-driven-github-spec-kit.md) declare Spec Kit as the workflow, but the scaffolding is not in the repo yet. Today only `.specify/memory/constitution.md` exists; the templates, helper scripts, and Claude skills (`speckit-specify`, `speckit-plan`, `speckit-tasks`, `speckit-implement`, …) do not. This task commits them.

  **One-time, by one person.** The init output is committed to the repo — every other developer just `git pull`s and has the Spec Kit skills available in Claude Code. Do not re-run `specify init` on a clone that already has `.specify/templates/` populated: `--force` would overwrite the hand-authored constitution and any customisations. Re-init only as a deliberate upgrade, via a new task `T00-v2` with its own PR.

  The hand-authored `.specify/memory/constitution.md` must be preserved byte-for-byte — `specify init` does not overwrite an existing constitution, but verify with `git diff` before committing.

  Spec Kit `0.7.4` uses a **skills-based** integration for Claude (`.claude/skills/speckit-*`), not slash commands in `.claude/commands/`. The user invokes `speckit-specify`, `speckit-plan`, `speckit-tasks`, `speckit-implement`, `speckit-clarify`, `speckit-analyze`, `speckit-constitution`, `speckit-checklist`, `speckit-taskstoissues` via the skill picker. Every later task in this plan that says "run `/specify`" or "run `/plan`" refers to invoking the corresponding skill.

  Run on the Mac (sandbox is offline to PyPI / GitHub):

  ```bash
  uvx --from git+https://github.com/github/spec-kit.git specify init --here --ai claude --force
  ```

  Expected scaffolding after the run:
  - `.specify/templates/` — `spec-template.md`, `plan-template.md`, `tasks-template.md`, `checklist-template.md`, `constitution-template.md`.
  - `.specify/scripts/bash/` — helpers (`create-new-feature.sh`, `check-prerequisites.sh`, `setup-plan.sh`, `common.sh`).
  - `.specify/extensions/git/` — git automation extension; `auto_commit.default: false` at install, so no silent commits.
  - `.specify/extensions.yml`, `.specify/integration.json`, `.specify/init-options.json`, `.specify/integrations/*.manifest.json`, `.specify/workflows/` — Spec Kit CLI metadata. Commit as a set.
  - `.claude/skills/speckit-*` — 14 skills: 9 workflow (specify, plan, tasks, implement, clarify, analyze, constitution, checklist, taskstoissues) + 5 git helpers (initialize, feature, commit, remote, validate).

  Existing assets that must remain untouched: `.specify/memory/constitution.md`, every file under `.claude/agents/`, and the pre-existing skills (`vertex-call`, `agent-prompt-edit`, `rubric-yaml`, `calibration-run`). If the init touches any of them, revert that hunk before commit.

  **Trim before commit:** init appends a generic `<!-- SPECKIT START --> ... <!-- SPECKIT END -->` block to `CLAUDE.md`. Remove it — our `CLAUDE.md` already has a richer "How work happens here (Spec Kit)" section. The marker comments let future init re-add it idempotently; we delete it again.

  Commit as a separate PR titled `chore: initialize spec kit scaffolding`. No production code in the same PR.

- **acceptance:**
  - `.specify/templates/` contains at minimum `spec-template.md`, `plan-template.md`, `tasks-template.md`.
  - `.specify/scripts/bash/` contains at least `create-new-feature.sh` and `check-prerequisites.sh`.
  - `.claude/skills/` contains at minimum `speckit-specify`, `speckit-plan`, `speckit-tasks`, `speckit-implement`.
  - `.specify/memory/constitution.md` is byte-identical to its pre-init version (`git diff --exit-code`).
  - `.claude/agents/*` and the pre-existing `.claude/skills/{vertex-call,agent-prompt-edit,rubric-yaml,calibration-run}` are byte-identical.
  - `CLAUDE.md` has no `<!-- SPECKIT … -->` block.
  - In a fresh Claude Code session inside the repo, the `speckit-specify` skill appears in the skill picker and executes when invoked.
- **references:** [`CLAUDE.md`](../../CLAUDE.md) §"How work happens here (Spec Kit)", [ADR-017](../../adr/017-spec-driven-github-spec-kit.md), constitution §17

### T01 — Monorepo layout + tooling baseline

- **agent:** `orchestrator`
- **parallel:** false (seeds everything else)
- **depends_on:** [T00]
- **contract:** none
- **description:**
  Create `app/backend/`, `app/frontend/`, `alembic/`, `configs/`, `prompts/`, `infra/terraform/`, `docs/`, `.github/workflows/`, `evals/` folders. Commit `.pre-commit-config.yaml` (already in repo) and install hooks. Configure `pyproject.toml` for ruff + mypy; `app/frontend/package.json` for pnpm + eslint + prettier + tsc.
- **acceptance:**
  - `pre-commit run --all-files` green on a clean tree.
  - `pnpm --dir app/frontend lint` exits 0.
  - `ruff check app/backend && mypy app/backend` exit 0 (empty targets are fine).

### T01a — Vertex AI quota + region request

- **agent:** `human` + `infra-engineer`
- **parallel:** true (runs independently of code in W1–W2)
- **depends_on:** [T01]
- **contract:** `docs/engineering/vertex-quota.md` (one-pager: region, quotas requested, current limits, who approved)
- **description:**
  PoC scope — request **standard** quotas, not enterprise. Resist the urge to over-provision; we'll re-evaluate before Phase 2 scale.

  **Deliverables:**
  - Region: `europe-west1` (Belgium) per ADR-015 — do not change here. T01a verifies at quota-request time that Gemini 2.5 Pro and Flash are both available in `europe-west1`; if either is missing, flag back to ADR-015 for a considered amendment rather than silently switching region.
  - Request (via GCP Console → Quotas): `aiplatform.googleapis.com` — `GenerateContentRequestsPerMinutePerProjectPerModel` raised from default to ~60 rpm for both models (enough for 3× concurrent sessions + calibration batch).
  - `docs/engineering/vertex-quota.md` logs: what was requested, what was granted, GCP support-case ID, requested-by, granted-on.
  - **Re-evaluation trigger:** if Phase 2 (post-pilot) targets > 20 concurrent sessions, raise a new task `T01a-v2` to request higher quota before any rollout.

- **acceptance:**
  - `docs/engineering/vertex-quota.md` committed with granted quota values.
  - Smoke: `curl` against Vertex Flash from `dev` Cloud Run returns within 10 s.
  - Budget alerts configured per §12 (50% / 90% / 100% of $50/mo).
- **references:** constitution §1 (candidates first — fail-open on quota is unacceptable), §12 (budget caps), ADR-006

### T02 — FastAPI skeleton

- **agent:** `backend-engineer`
- **parallel:** true (with T03, T04, T06 after T01 lands)
- **depends_on:** [T01]
- **contract:** `app/backend/openapi.yaml` (empty-but-valid stub committed by this task)
- **description:**
  `app/backend/main.py` with `GET /health` returning `{"status":"ok","version":<git sha>}`. Pydantic `Settings` loaded from env. Structured JSON logging via `structlog` with a **PII-stripping processor** (§15): drops / hashes known-PII keys (`email`, `candidate_email`, `name`, `full_name`, `cv_text`, `transcript`, `message_text`, `turn_text`) before emit; anything matching an email regex in free-form values is replaced with `<email:sha1:...>`. Allowlist of keys lives at `app/backend/logging/pii_allowlist.py` and is asserted in a unit test. DI layout: `api/`, `services/`, `db/`, `llm/`. Minimal `pytest` config.
- **acceptance:**
  - `uvicorn app.backend.main:app` starts locally.
  - `GET /health` returns 200 JSON.
  - `openapi.yaml` committed and regenerated by `python -m app.backend.generate_openapi`.
  - One smoke test in `app/backend/tests/test_health.py`.
  - **§15 PII test:** logger called with `{"candidate_email": "x@y.com", "msg": "foo bar x@y.com"}` produces output where both locations are redacted/hashed.
- **references:** constitution §15

### T03 — Next.js skeleton

- **agent:** `frontend-engineer`
- **parallel:** true
- **depends_on:** [T01]
- **contract:** `app/backend/openapi.yaml` (stub) — client not generated yet
- **description:**
  Next.js App Router + TypeScript + Tailwind. Init shadcn/ui (`button`, `card`, `input`, `label`, `dialog`, `dropdown-menu`, `tooltip`, `popover`, `table`). Admin shell layout with left nav stub. `src/design/tokens.ts` seeded from `docs/design/tokens/*.md`. Base primitives on Chat-iX baseline (1-px borders, light theme, N-iX orange `#E8573C` only on allowlisted slots).
- **acceptance:**
  - `pnpm dev` serves `/` with admin shell.
  - Jest + React Testing Library configured; one smoke test green.
  - `tokens.ts` round-trips values from markdown source; reviewer visual-discipline hooks pass.

### T04 — Vertex client wrapper

- **agent:** `backend-engineer`
- **parallel:** false (blocks T17, T18, T20, T21 — all LLM-touching tasks)
- **depends_on:** [T02, T01a]
- **contract:** none (internal package `app/backend/llm/`; public entry point re-exported from `app/backend/llm/__init__.py`)
- **description:**
  Single async entry-point `call_model(request, *, sink, ledger, settings)` exported from the `app/backend/llm/` package (re-exported from `vertex.py`). Wraps Vertex AI via the `google-genai` async client. Must: enforce §12 hard caps via Pydantic field validators, retry on transient upstream failures (uniform 3-attempt budget; `DeadlineExceeded` excluded) with tenacity exponential backoff under a 30-s wall-clock cap, write a `TraceRecord` synchronously before returning (sink failure → `TraceWriteError`; auditability §1 trumps the otherwise-OK call), raise typed errors (`ModelCallConfigError`, `VertexTimeoutError`, `VertexUpstreamUnavailableError`, `VertexSchemaError`, `SessionBudgetExceeded`, `TraceWriteError`). Schema-miss raises `VertexSchemaError` immediately — per-agent retry policies live in agent modules (T18–T21). Pre-commit hook `no-provider-sdk-imports` (script: `scripts/check-no-provider-sdk-imports.sh`) enforces that no module outside the `_real_backend.py` / `_mock_backend.py` allowlist imports a model-provider SDK.
- **acceptance:**
  - Smoke test hits Gemini 2.5 Flash and returns parsed JSON conforming to a supplied schema.
  - Unit tests cover: timeout >30s raises `VertexTimeoutError`; schema miss raises `VertexSchemaError` immediately; per-agent retry policies live in agent modules; cost recorded via injected tracker.
  - `ruff` + `mypy --strict` pass.
- **references:** ADR-006, ADR-013, constitution §12, docs/engineering/vertex-integration.md
- **note:** Schema-miss policy reconciled per `specs/007-t04-vertex-client-wrapper/spec.md` Clarifications 2026-04-26 — the wrapper raises immediately; Assessor / Planner / Interviewer each apply their own retry / fallback / escalation in T18–T21.

### T05 — DB schema v0 + Alembic baseline + append-only enforcement

- **agent:** `backend-engineer`
- **parallel:** true (with T06, T07 after T02)
- **depends_on:** [T02]
- **contract:** `alembic/versions/0001_baseline.py`
- **description:**
  Alembic baseline migration `0001_baseline.py`. Forward-only invariant enforced (§10). SQLAlchemy models under `app/backend/db/models/`.

  **Extensions enabled (at baseline, even though MVP doesn't use them):**
  - `CREATE EXTENSION IF NOT EXISTS vector;` — pgvector for H2 RAG (ADR-008). Enabling at baseline avoids a destructive migration later.
  - `CREATE EXTENSION IF NOT EXISTS pgcrypto;` — for `gen_random_uuid()` used by several PKs.

  **Tables created:**
  - Rubric read-only tree: `user`, `stack`, `competency_block`, `competency`, `topic`, `level`, `rubric_tree_version`.
  - Session placeholders (columns filled later): `interview_session`, `position_template`, `interview_plan`.
  - **All six §3 append-only tables** (schema only; code that writes to them lives in later tiers):
    `turn_trace`, `assessment` (per-session, per-competency final score + confidence),
    `assessment_correction`, `turn_annotation`, `audit_log` (actor_id, action, subject_hash, ts — no PII per §15),
    `session_decision`.

  **§3 DB-level enforcement (critical):**
  - Postgres `BEFORE UPDATE OR DELETE` trigger on each of the six tables raising `RAISE EXCEPTION 'append-only: % not allowed on %'`.
  - `REVOKE UPDATE, DELETE ON <tables> FROM techscreen_app` on the application role.
  - Re-enabled only for `techscreen_migrator` role during migrations.

- **acceptance:**
  - `alembic upgrade head` on fresh Postgres creates every table.
  - `alembic downgrade base` reverses cleanly (migration is reversible even though project is forward-only; needed for local dev resets).
  - Integration test: open a transaction, insert a `stack`, rollback.
  - **§3 invariant tests (6 total, one per append-only table):** attempting `UPDATE` or `DELETE` via the application role raises from the trigger AND from the revoked grant. Reviewer greps the migration file for `REVOKE UPDATE, DELETE` on all six tables.
- **references:** constitution §3, §10, §15, ADR-019

### T05a — Feature-flag infrastructure (§9 dark-launch enabler)

- **agent:** `backend-engineer`
- **parallel:** true (with T06, T07, T08 after T05)
- **depends_on:** [T05]
- **contract:** `docs/contracts/feature-flag.schema.json` + `configs/feature-flags.yaml`
- **description:**
  §9 says every risky feature ships behind a flag that starts `false`. Without this infrastructure landing in Tier 1, every Tier 3+ task that introduces a new agent/WS/auto-save will silently violate §9.

  **Deliverables:**
  - `feature_flag` table: `name TEXT PK, enabled BOOL NOT NULL DEFAULT false, owner TEXT NOT NULL, default_value JSONB, updated_at TIMESTAMPTZ, updated_by TEXT`. Migration in `0002_feature_flags.py`.
  - `app/backend/services/feature_flags.py`: `is_enabled(name, *, session_id=None) -> bool` with in-process cache (60s TTL) + Postgres LISTEN/NOTIFY for invalidation.
  - `configs/feature-flags.yaml`: source-of-truth file under §16 Configs-as-Code. Schema validated by JSON schema (the contract above).
  - **Self-contained GHA workflow** `.github/workflows/sync-feature-flags.yml` (does not depend on T16): on `main` merge, diff `configs/feature-flags.yaml` against DB, upsert with `updated_by = 'configs-as-code'`. T16 (Configs-as-Code sync for rubric) extends this same workflow with rubric-sync as a second job — see T16.
  - `docs/engineering/feature-flags.md`: index of every flag, owner, default, "what flipping it does". Each entry has lifecycle state: `active` or `sunset` (with `sunset_pr:` back-reference and `sunset_date:`).
  - Pre-commit hook `feature-flag-registered` is **bidirectional**:
    - Any new `is_enabled("xxx")` call must have `xxx:` in `configs/feature-flags.yaml`.
    - Any PR that removes the last `is_enabled("xxx")` call must flip the yaml entry to `state: sunset` and add an entry to `docs/engineering/feature-flags.md` sunset table (not delete it — sunset flags remain documented for audit).

  **Out of scope for this task:** Admin UI for toggling flags (Phase 2). MVP toggles via PR to `configs/feature-flags.yaml` or direct SQL on prod for emergency disable.

- **acceptance:**
  - Flag created via YAML → `main` merge → DB row exists with `enabled=false`.
  - Removing a flag from YAML does not delete the DB row (orphan flagged in CI as warning).
  - Unit test: cache invalidation fires within 1 s of NOTIFY.
  - Reviewer can grep PRs for `is_enabled(` and confirm the name is in `configs/feature-flags.yaml`.
  - Fixture PR that removes the last `is_enabled("xxx")` without flipping to `sunset` is blocked by pre-commit.
- **references:** constitution §9, §16, ADR-011, ADR-021

### T06 — Cloud Run + Cloud SQL + Secret Manager (dev + prod)

- **agent:** `infra-engineer`
- **parallel:** true
- **depends_on:** [T01]
- **contract:** `infra/terraform/` module layout
- **description:**
  Two Cloud Run services (`techscreen-backend`, `techscreen-frontend`), Cloud SQL Postgres 17 instance with **pgvector extension enabled at provisioning** (`database_flags { name = "cloudsql.enable_pgvector", value = "on" }` in Terraform; verify PG17 + pgvector availability in `europe-west1` during this task and fall back to PG16 only if blocked — see ADR-001 amendment 2026-04-19), Secret Manager for every key listed in `.env.example`. Workload Identity Federation only — no JSON service-account keys anywhere (§5–6, ADR-013). Two workspaces: `dev`, `prod` (no staging — ADR-009). Cloud Logging + Error Reporting wired.
- **acceptance:**
  - `terraform plan -workspace=dev` clean diff after bootstrap.
  - `gcloud run services describe techscreen-backend` returns the service after `apply`.
  - `gcloud secrets list` shows every key from `.env.example` (values placeholder).
  - `psql -c "SELECT extname FROM pg_extension WHERE extname = 'vector';"` returns one row on the provisioned instance.
  - No `keyfile.json` anywhere in repo (`reviewer` checks via gitleaks + grep).

### T06a — `/deploy` + `/rollback` slash commands (§19)

- **agent:** `infra-engineer`
- **parallel:** true (with T07, T09 after T06)
- **depends_on:** [T06]
- **contract:** `.github/workflows/deploy.yml` + `.github/workflows/rollback.yml` + `docs/engineering/deploy-playbook.md`
- **description:**
  §19 says rollback must complete in under five minutes. That requires the commands to exist, be documented, and be tested — not just implied.

  **Deliverables:**
  - `/deploy` slash command (GitHub Actions `workflow_dispatch` + ChatOps trigger): builds `prod` Docker target, pushes to Artifact Registry, deploys new Cloud Run revision at **0% traffic**, runs post-deploy smoke against the new revision URL, reports result in PR comment. **Migration-approval gate wiring is deferred until T10 lands** — ship `/deploy` without the check, then extend in a follow-up PR once T10's `migration-approved` label mechanic is in place (same W1–W2 window).
  - `/promote N` command: shifts traffic to the latest revision in steps (`/promote 10`, `/promote 50`, `/promote 100`).
  - `/rollback` command: single `gcloud run services update-traffic --to-revisions=<previous>=100` call. Target wall-clock ≤ 60 s from invocation.
  - `docs/engineering/deploy-playbook.md`: runbook with the exact commands, who has access, what to do if the command fails.

- **acceptance:**
  - `/deploy` on a trivial PR produces a 0%-traffic revision and posts its URL.
  - `/rollback` completes end-to-end in under 2 minutes on `dev` (measured in CI timer).
  - Deploy step fails loudly when `migration-approved` label is absent on a PR that touched `alembic/versions/` (follow-up after T10).
- **references:** constitution §10, §19, ADR-009, ADR-012

### T07 — Identity Platform SSO + role claims

- **agent:** `infra-engineer`
- **parallel:** true
- **depends_on:** [T06]
- **contract:** JSON schema for `IdTokenClaims` at `docs/contracts/id-token-claims.json`
- **description:**
  Identity Platform with Google provider constrained to `n-ix.com`. Custom claim `role ∈ {admin, recruiter, reviewer}` injected by a Cloud Function trigger; membership driven by Workspace groups. Backend middleware validates JWT and populates `request.state.user`.
- **acceptance:**
  - Signing in with a `@n-ix.com` account returns a token whose `role` claim matches Workspace group.
  - Non-`@n-ix.com` tokens are rejected with 401.
  - Middleware unit-tested against three role fixtures.

### T08 — Matrix importer (xlsx → YAML → DB)

- **agent:** `backend-engineer`
- **parallel:** true (after T05)
- **depends_on:** [T05]
- **contract:** `configs/rubric/<stack>.yaml` JSON schema at `docs/contracts/rubric.schema.json`
- **description:**
  CLI `python -m app.backend.cli.import_matrix <xlsx>` that validates the Excel against the rubric schema, emits canonical YAML per stack into `configs/rubric/`, and — on seed — populates `stack`/`competency_block`/`competency`/`topic`/`level`. Idempotent; re-running with unchanged YAML is a no-op. Uses the `rubric-yaml` skill.
- **acceptance:**
  - Import of the provided C# + React matrix produces two YAMLs that round-trip (import → YAML → DB → export → YAML) byte-identical.
  - Changing a `topic.name` in YAML bumps `rubric_tree_version` and writes an audit row (§4).

### T09 — Docker stacks (dev + test)

- **agent:** `infra-engineer`
- **parallel:** true
- **depends_on:** [T01, T05]
- **contract:** none (local-only)
- **description:**
  `docker-compose.yml` (backend + frontend + Postgres + pgvector + Vertex mock) and `docker-compose.test.yml` (backend + Postgres + mock only, for CI). Pre-commit hooks run inside a container in CI. The Vertex mock is a tiny FastAPI echo server (`infra/vertex-mock/`) returning canned JSON per model+prompt hash.
- **acceptance:**
  - `docker compose up` brings everything up on first invocation with `docker compose build`.
  - `docker compose -f docker-compose.test.yml run --rm backend pytest` green.
  - CI workflow (T10) uses the test stack.

### T10 — CI pipeline (lint + test on PR) + migration approval gate

- **agent:** `infra-engineer`
- **parallel:** true (after T09)
- **depends_on:** [T09]
- **contract:** none
- **description:**
  GitHub Actions workflow `.github/workflows/ci.yml`: matrix of (backend, frontend), pre-commit run, ruff+mypy+pytest for backend, eslint+tsc+jest for frontend, compose-based integration smoke, actionlint, gitleaks. Reviewer sub-agent invoked on every PR.

  **§10 migration approval gate (label-based, no GitHub App):**
  - When a PR touches `alembic/versions/*.py`, CI runs `alembic upgrade head --sql` against a fresh Postgres and posts the generated SQL as a PR comment (collapsed by default).
  - A reviewer (human) inspects the SQL and applies the `migration-approved` label to the PR. The label is the explicit go/no-go signal — no GitHub App needed.
  - `/deploy` (T06a) refuses to proceed on PRs that touched `alembic/versions/` without the `migration-approved` label.
  - Destructive DDL (`DROP COLUMN`, `DROP TABLE`, type-narrowing `ALTER`) auto-adds the `needs-adr` label via a separate workflow step; reviewer agent blocks merge without a linked ADR.

- **acceptance:**
  - PR from a trivial branch goes green end-to-end.
  - A PR that removes a test or violates an invariant is blocked by `reviewer` comment.
  - Fixture PR touching a migration: SQL appears as PR comment; without `migration-approved` label, `/deploy` exits non-zero with a clear message.
  - Fixture PR with `DROP COLUMN` auto-gets `needs-adr` label; reviewer agent blocks merge if ADR missing.
- **references:** constitution §10

### T11 — Tier-1 checkpoint (smoke)

- **agent:** `human` + `orchestrator`
- **parallel:** false (gate)
- **depends_on:** [T01a, T02, T03, T04, T05, T05a, T06, T06a, T07, T08, T09, T10]
- **contract:** none
- **description:**
  Run the Tier-1 smoke: local `docker compose up` → open admin shell → backend health 200 → `uvicorn` backend calls Vertex wrapper via `/debug/vertex-ping` (temp endpoint) → deploy to `dev` Cloud Run via `/deploy` → same ping from deployed backend. Also verify: append-only triggers fire on a direct SQL attempt (§3), and a dummy flag from `configs/feature-flags.yaml` is `is_enabled=false` via the service (§9). Remove the `/debug/*` endpoints afterwards.
- **acceptance:**
  - Ihor signs off with `LGTM` on the checkpoint PR.
  - `/debug/*` routes are not present in `openapi.yaml`.
  - Invariant smoke tests green: §3 trigger fires on test UPDATE; §9 service returns `false` for a seed flag.

---

## Tier 2 (W3) — Position Template + Rubric Snapshot

**Goal:** recruiter can create/edit a Position Template; the system can snapshot the rubric immutably for a session.

**Entry criteria:** Tier 1 signed off.

### T12 — Position Template schema + contract

- **agent:** `backend-engineer`
- **parallel:** false (unlocks T13, T14 parallel)
- **depends_on:** [T08]
- **contract:** `app/backend/openapi.yaml` (Position Template endpoints) + `docs/contracts/position-template.schema.json`
- **description:**
  SQLAlchemy model `PositionTemplate` + migration. Pydantic request/response schemas. Validation rules: stacks must exist, level in `{Junior, Middle, Senior, Tech Leader}`, must-have competencies subset of optional. Regenerate `openapi.yaml` in the same PR (§14).
- **acceptance:**
  - OpenAPI diff is clean and committed.
  - `reviewer` sees both `openapi.yaml` and schema file changed together.

### T13 — Position Template CRUD endpoints

- **agent:** `backend-engineer`
- **parallel:** true
- **depends_on:** [T12]
- **contract:** `app/backend/openapi.yaml`
- **description:**
  `POST/GET/PATCH/DELETE /position-templates`. Soft-delete only (set `archived_at`); no row removal. Authorization: `recruiter` or `admin` role. Integration tests hit real Postgres (docker-compose.test).
- **acceptance:**
  - All four verbs covered by tests.
  - Archived templates excluded from list by default, included with `?include_archived=true`.

### T14 — Position Template admin UI

- **agent:** `frontend-engineer`
- **parallel:** true
- **depends_on:** [T12]
- **contract:** `app/backend/openapi.yaml` (frozen for T12 endpoints)
- **description:**
  Two screens: list view (`/admin/positions`) and create/edit form (`/admin/positions/new`, `/admin/positions/:id`). Per-screen spec lives at `docs/design/screens/02-positions/spec.md`. Client regenerated from `openapi.yaml` via `openapi-typescript`. React Query for state.
- **acceptance:**
  - Screen spec present and matches implemented components.
  - Visual discipline pre-commit hooks pass (no arbitrary Tailwind, no raw hex, no `dark:`).
  - `Baseline Check` block in PR body per `.claude/agents/frontend-engineer.md`.

### T15 — Rubric snapshot (deep-copy on session start)

- **agent:** `backend-engineer`
- **parallel:** false
- **depends_on:** [T08, T12]
- **contract:** `docs/contracts/rubric-snapshot.schema.json`
- **description:**
  `rubric_snapshot` JSONB column on `interview_session`. Service function `snapshot_rubric(rubric_tree_version_id) -> RubricSnapshot` deep-copies stack → competency_block → competency → topic → level. Pre-commit-like assertion: the snapshot never references the live tables by FK after the session starts. Tested with a mutation: after session created, bump `rubric_tree_version` → snapshot unchanged (§4).
- **acceptance:**
  - Integration test covers the "rubric edit must not affect running session" invariant.

### T16 — Configs-as-Code sync (YAML → DB on merge)

- **agent:** `infra-engineer`
- **parallel:** true
- **depends_on:** [T05a, T08]
- **contract:** none (internal job)
- **description:**
  Extends `.github/workflows/sync-feature-flags.yml` (created in T05a) with a second job `sync-rubric` that diffs `configs/rubric/` against DB and applies validated changes via the importer. Guarded: destructive changes (removed topic, retyped level) require the PR body to include `ADR-xxx` citation; otherwise the job fails.

  After T16: the same workflow handles **all** Configs-as-Code surfaces (feature flags from T05a, rubric from T16, and any future `configs/*.yaml` added by Phase 2). Single source of truth for the §16 invariant.

- **acceptance:**
  - Merging a benign YAML change applies on `dev` without manual steps.
  - A destructive change without ADR citation fails the job and emits a GH check failure.
  - Both `sync-feature-flags` and `sync-rubric` jobs run independently; failure of one does not block the other.

---

## Tier 3 (W4–W5) — Core Agents + State Machine

**Goal:** end-to-end mock conversation loop works. Candidate types → Interviewer responds → Assessor scores each turn.

**Entry criteria:** Tier 2 merged.

### T17 — Prompt structure + output schemas

- **agent:** `prompt-engineer`
- **parallel:** false (unlocks T18, T19, T20 parallel)
- **depends_on:** [T04]
- **contract:** `prompts/interviewer/v0001/schema.json`, `prompts/assessor/v0001/schema.json`
- **description:**
  `prompts/interviewer/v0001/{system.md, schema.json, few_shot.md, notes.md}` and same for `assessor/`. System prompt in English; candidate-facing examples in Ukrainian (§11, ADR-008). Output schema is strict JSON: Interviewer `{message_uk, intent, next_topic_hint, end_of_phase}`; Assessor `{concepts_covered, concepts_missing, red_flags, level_estimate, confidence}`.

  **Ownership note:** per-agent schema files under `prompts/<agent>/v0001/schema.json` are the single source of truth. **There is no `docs/contracts/agent-interfaces.schema.json` aggregate** — backend agent wrappers (T18/T19/T24) import directly from the per-agent files. This simplifies ownership: prompt-engineer fully owns agent schemas.

- **acceptance:**
  - Calibration-run smoke against a 3-dialog tiny fixture produces schema-valid output.
  - `prompts/**/notes.md` explains the design choices.

### T18 — Interviewer agent wrapper

- **agent:** `backend-engineer`
- **parallel:** true (with T19, T20)
- **depends_on:** [T17]
- **contract:** `prompts/interviewer/v0001/schema.json` (per-agent, no aggregate — see T17)
- **description:**
  `app/backend/agents/interviewer.py`: build prompt from template + session state, call `llm.vertex.call` with schema, validate, retry once on schema miss, surface parsed object. Pure — no DB writes except via TurnTrace (T21).
- **acceptance:**
  - Unit test with mocked Vertex returns parsed object.
  - Schema miss → single retry → failure → typed exception.

### T19 — Assessor agent wrapper

- **agent:** `backend-engineer`
- **parallel:** true
- **depends_on:** [T17]
- **contract:** `prompts/assessor/v0001/schema.json` (per-agent, no aggregate — see T17)
- **description:**
  Same pattern as Interviewer. Input: (full turn transcript so far, active rubric node, candidate last answer). Output: per-turn coverage and flags. Async — call does not block the Interviewer's next turn (ADR-007, voice-readiness).
- **acceptance:**
  - Async scoring test: Interviewer produces turn N+1 while Assessor is still scoring turn N.

### T20 — State machine (orchestrator)

- **agent:** `backend-engineer`
- **parallel:** false (depends on T18 + T19 contracts)
- **depends_on:** [T18, T19]
- **contract:** `docs/contracts/state-machine.md` (narrative + transition table)
- **description:**
  Pure Python state machine at `app/backend/orchestrator/state_machine.py`. Phases: `INTRO → TECH(competency→topic→probe) → QA → CLOSE`. Transitions are deterministic functions of (current state, agent outputs, timers, plan). LLMs suggest but never decide (§2, ADR-005). Persists `session_state` to DB; resumable after reconnect.
- **acceptance:**
  - Transition table unit-tested: every edge has at least one input fixture covering it.
  - No `if llm_output.should_…:` patterns (checked by `reviewer` via grep).

### T21 — TurnTrace logger + cost middleware + per-session ceiling (§12)

- **agent:** `backend-engineer`
- **parallel:** true (with T22)
- **depends_on:** [T04, T05, T05a]
- **contract:** `docs/contracts/turn-trace.schema.json`
- **description:**
  Append-only `turn_trace` table. One row per agent call. Fields: full prompt, raw response, parsed output, tokens_in, tokens_out, latency_ms, model, agent_type, cost_usd, session_id, turn_id. `UPDATE`/`DELETE` blocked at SQLAlchemy event level + DB trigger (§3). Cost middleware aggregates running total per session; exposed via metric `techscreen_session_cost_usd`.

  **§12 per-session cost ceiling (enforced, not just observed):**
  - Default ceiling `$5` per session, overridable via `configs/llm-limits.yaml` (Configs-as-Code, §16).
  - `session_cost_guard` middleware checks cumulative `cost_usd` before each Vertex call. On breach:
    1. Raise `SessionCostCeilingError`.
    2. State machine transitions session to `flagged_for_review`, writes a `session_decision` row with `reason=cost_ceiling`.
    3. Cloud Monitoring alert fires (dashboards set up in T38).
  - Feature flag `enforce_session_cost_ceiling` (default **false** in Tier 3, flipped **true** before T49 pilot dry-run) — dark-launch per §9.

- **acceptance:**
  - Attempting UPDATE via a raw SQL test raises from the DB trigger.
  - Cost metric correctly aggregates across two consecutive sessions.
  - Integration test: mocked cost stream crosses `$5` → `SessionCostCeilingError` raised, `session_decision` row inserted, flag observed as `false` in default state.
- **references:** constitution §3, §9, §12, §16

### T22 — Dev conversation UI

- **agent:** `frontend-engineer`
- **parallel:** true
- **depends_on:** [T20]
- **contract:** `app/backend/openapi.yaml` (session + websocket endpoints stubbed)
- **description:**
  Internal `/dev/session` page: minimal chat UI driven by a mock session, WebSocket to backend, shows raw TurnTrace in a collapsible side panel for debugging. Not on Chat-iX baseline (dev-only, excluded from design gates).
- **acceptance:**
  - Team can drive a full mock session end-to-end from this UI.
  - Side panel shows JSON of each turn trace.

### T23 — End-to-end mock session test

- **agent:** `orchestrator`
- **parallel:** false (gate)
- **depends_on:** [T18, T19, T20, T21]
- **contract:** none
- **description:**
  `app/backend/tests/e2e/test_mock_session.py`: spin up docker-compose.test, run a scripted 8-turn session through state machine with Vertex mock returning canned outputs, assert every turn has a `turn_trace` row and transitions match the fixture table.
- **acceptance:**
  - Test is stable (green on 5/5 consecutive runs in CI).

---

## Tier 4 (W6) — PreInterviewPlanner + Recruiter Review UI

**Goal:** recruiter can generate, review, edit, and approve an InterviewPlan before the session starts.

### T24 — Planner agent v0001

- **agent:** `prompt-engineer`
- **parallel:** false
- **depends_on:** [T17]
- **contract:** `prompts/planner/v0001/schema.json`
- **description:**
  `prompts/planner/v0001/*`. Input: Position Template + rubric snapshot. Output: ordered competencies, target minutes per competency, topics with target level and priority (`must_cover` / `nice_to_have`), seed questions (Ukrainian). Model: Gemini 2.5 Pro (offline, cost-insensitive).
- **acceptance:**
  - Schema-valid plan generated for a dummy template against the mock Vertex.

### T25 — InterviewPlan data model + freeze

- **agent:** `backend-engineer`
- **parallel:** true (with T26)
- **depends_on:** [T15, T24]
- **contract:** `docs/contracts/interview-plan.schema.json` + `app/backend/openapi.yaml`
- **description:**
  `interview_plan` table: `plan_json JSONB`, `generated_by`, `approved_by`, `approved_at`, `status ∈ {draft, approved, frozen}`. Freeze rule: once a session starts referencing a plan, PATCH on that plan returns 409. Service function `freeze_plan(session_id, plan_id)`.
- **acceptance:**
  - Integration test: approve → start session → PATCH plan → 409.

### T27a — Planner OpenAPI contract commit (unblocks T26 || T27 fan-out)

- **agent:** `backend-engineer`
- **parallel:** false (gates T26 and T27)
- **depends_on:** [T25]
- **contract:** `app/backend/openapi.yaml` (diff: `POST /plans/generate`, `POST /plans/:id/approve`)
- **description:**
  Contract-first commit per §14. Adds endpoint definitions + request/response schemas to `openapi.yaml` and regenerates the schema file — **no implementation yet**. Frozen after merge for downstream parallel fan-out.

  The diff includes: request body schema for `/plans/generate`, response schema referencing `InterviewPlan` (already added by T25), error shapes for 402 (cost ceiling), 409 (plan frozen), 404.

- **acceptance:**
  - `openapi.yaml` validates (`openapi-spec-validator`).
  - Diff contains only declarations (no `app/backend/api/plans.py` yet).
  - Reviewer confirms `app/backend/api/plans.py` stub returns `501 Not Implemented`.

### T26 — Recruiter Review UI (plan editor)

- **agent:** `frontend-engineer`
- **parallel:** true (with T27 after T27a lands)
- **depends_on:** [T25, T27a]
- **contract:** `app/backend/openapi.yaml` (frozen by T27a)
- **description:**
  `/admin/plans/:id` screen. List of competencies/topics, inline edit seed questions, reorder (drag handle using `@dnd-kit`), priority toggle, add/remove topic, Approve button. Per-screen spec at `docs/design/screens/03-plan-review/spec.md`. Latency target: Approve completes within 300ms.
- **acceptance:**
  - Recruiter creates a plan + approves in ≤15 min on the fixture template (measured in calibration dry-run W10).
  - Visual discipline hooks pass.

### T27 — Planner endpoints + cost guard (implementation)

- **agent:** `backend-engineer`
- **parallel:** true (with T26 after T27a lands)
- **depends_on:** [T25, T27a]
- **contract:** `app/backend/openapi.yaml` (frozen by T27a — implementation must conform)
- **description:**
  Replace the 501 stubs from T27a with the real implementation. `POST /plans/generate` (Template → Plan draft) + `POST /plans/:id/approve`. Planner runs on Gemini 2.5 Pro with a per-generation cost ceiling (`max_usd_per_plan=0.30`) that short-circuits before LLM call if the projected cost exceeds ceiling.

  **Drift check:** if implementation requires changing the schema, bump the contract as a separate PR (T27a v2) before re-opening this PR. Silent schema drift blocks merge.

- **acceptance:**
  - Cost-ceiling test: mocked high-cost projection causes endpoint to return 402 with an explanatory body.
  - Running `openapi-diff` between committed `openapi.yaml` and server-introspected shows zero delta.

---

## Tier 5 (W7) — Candidate Session (end-to-end UX)

**Goal:** real candidate enters via link, runs a timed interview, session saves reliably.

### T28 — Magic-link + session start endpoint

- **agent:** `backend-engineer`
- **parallel:** false
- **depends_on:** [T25]
- **contract:** `app/backend/openapi.yaml`
- **description:**
  `POST /sessions/start?token=…`: token is a signed JWT (HS256) with `plan_id`, `candidate_email`, `exp` (48h). On start, snapshot rubric is pinned, plan is frozen, `interview_session.status = in_progress`. Consent gate: first message from backend requires consent flag in request body (§14).
- **acceptance:**
  - Expired token → 410 Gone.
  - Replay token (same `jti`) after session start → 409.

### T29a — WebSocket protocol contract commit (unblocks T29 || T30 fan-out)

- **agent:** `backend-engineer`
- **parallel:** false (gates T29 and T30)
- **depends_on:** [T28]
- **contract:** `docs/contracts/ws-protocol.md` + `docs/contracts/ws-messages.schema.json`
- **description:**
  Contract-first per §14. Commit the WebSocket protocol document and JSON schemas for every message type — no implementation.

  **Scope:**
  - Connection lifecycle (handshake, auth via JWT from T28, heartbeat cadence, close codes).
  - Server → client messages: `interviewer_turn`, `phase_change`, `session_end`, `error`, `reconnect_replay`.
  - Client → server messages: `candidate_turn`, `heartbeat`, `consent_given`.
  - Reconnect semantics: server buffers last `interviewer_turn` for 30 min; client re-auth replays it via `reconnect_replay`.
  - JSON schemas for every message type committed as `.schema.json` and referenced from `ws-protocol.md`.

- **acceptance:**
  - Every message type has a schema file.
  - Reviewer can diff protocol vs frontend client types (generated in T30) without mismatch.

### T29 — WebSocket streaming channel (implementation)

- **agent:** `backend-engineer`
- **parallel:** true (with T30 after T29a lands)
- **depends_on:** [T28, T29a]
- **contract:** `docs/contracts/ws-protocol.md` (frozen by T29a)
- **description:**
  Implement `/ws/sessions/:id` per the frozen protocol. Auto-save on every turn (server side). Graceful reconnect within 30 min resumes state (ADR-007). Message validation against committed JSON schemas on every inbound/outbound frame.
- **acceptance:**
  - Disconnection test: close socket mid-turn, reconnect, server replays last `interviewer_turn` via `reconnect_replay`.
  - Invalid message shape rejected with close code `1003` and logged.

### T30 — Candidate landing + chat UI

- **agent:** `frontend-engineer`
- **parallel:** true (with T29 after T29a lands)
- **depends_on:** [T28, T29a]
- **contract:** `docs/contracts/ws-protocol.md` (frozen by T29a) + `app/backend/openapi.yaml`
- **description:**
  `/s/:token` landing page with intro + consent checkbox. On consent, `/s/:token/session` chat UI (Chat-iX baseline). Progress indicator shows phase + elapsed time (monotonic, from server). Connection-lost banner with auto-retry. Client types generated from `ws-messages.schema.json`. Screen specs: `docs/design/screens/04-candidate-intro/spec.md`, `docs/design/screens/05-candidate-session/spec.md`.
- **acceptance:**
  - Chromium + Safari + Firefox smoke: intro → consent → full mock session.
  - Baseline Check block in PR body.

### T31 — Session reliability (timeout, autosave)

- **agent:** `backend-engineer`
- **parallel:** false
- **depends_on:** [T29]
- **contract:** none
- **description:**
  Hard 120-minute session cap with graceful close and partial-save; idle timeout 10 min with warning ping; autosave after every parsed Assessor output (async). Background job closes orphan sessions nightly.
- **acceptance:**
  - Integration test **run locally via docker-compose.test**: `docker compose kill backend` mid-session, restart, reconnect from the candidate client — server returns `session_end` with `reason=interrupted` and a saved partial transcript. (Cloud Run does not allow killing/restarting a single instance, so this invariant is tested locally only.)

### T32 — Candidate warning copy (anti-cheat deterrent)

- **agent:** `prompt-engineer`
- **parallel:** true
- **depends_on:** [T30]
- **contract:** `prompts/shared/candidate-warnings.md`
- **description:**
  Ukrainian warning text shown on the intro page and referenced by the Interviewer when the candidate appears to paste long blocks (heuristic in T33 below). No proctoring — deterrent only (MVP scope §3).
- **acceptance:**
  - Copy reviewed by Ihor + one reviewer; stored under `prompts/shared/`.

### T33 — Paste / burst heuristic flag

- **agent:** `backend-engineer`
- **parallel:** true
- **depends_on:** [T29]
- **contract:** none (internal signal)
- **description:**
  Simple server-side heuristic on WebSocket: messages > 600 chars or arriving within 250 ms of each other are flagged in `turn_trace.flags`. Assessor sees the flag and weighs its `level_estimate`; Interviewer may surface the warning.

  **Thresholds (600 chars, 250 ms) are seed values** — expected to produce false positives on long legitimate answers. Tune in Tier 8 (calibration) using real session data: record FP rate, adjust, commit new thresholds under `configs/heuristics.yaml` (§16 Configs-as-Code).

- **acceptance:**
  - Unit test: synthetic paste storm raises the flag; normal typing does not.
  - Thresholds live in `configs/heuristics.yaml`, not hard-coded — so Tier 8 tuning does not require a code change.

---

## Tier 6 (W8) — Reviewer / Annotation UI

**Goal:** reviewer can open a completed session, see transcript + scores, annotate, correct, sign off.

### T34 — Session detail endpoint

- **agent:** `backend-engineer`
- **parallel:** false
- **depends_on:** [T21, T25]
- **contract:** `app/backend/openapi.yaml`
- **description:**
  `GET /sessions/:id/review` returns transcript, TurnTraces, Assessor outputs, current final decision, rubric snapshot. Reviewer role only. Paginated by turn.
- **acceptance:**
  - Endpoint returns <400 ms on a 90-turn fixture.

### T35 — TurnAnnotation + AssessmentCorrection (append-only)

- **agent:** `backend-engineer`
- **parallel:** true (with T36)
- **depends_on:** [T34]
- **contract:** `app/backend/openapi.yaml`
- **description:**
  Both tables are append-only. `TurnAnnotation`: per-turn quality tags + free text. `AssessmentCorrection`: per-competency override score + reason tags. DELETE always returns 405. UPDATE via POST a new row (corrections_of_correction supported).
- **acceptance:**
  - DB trigger blocks UPDATE/DELETE (§3).
  - API integration test: correct a score → list corrections → see ordered history.

### T36 — Reviewer UI (session detail)

- **agent:** `frontend-engineer`
- **parallel:** true
- **depends_on:** [T34]
- **contract:** `app/backend/openapi.yaml`
- **description:**
  `/review/sessions/:id`: turn-by-turn transcript, Assessor panel side-by-side, per-turn annotation controls, per-competency correction controls, final decision card (`approve`/`reject`/`request_more_info`). Screen spec at `docs/design/screens/06-reviewer-session/spec.md`. Keyboard shortcuts for fast annotation.
- **acceptance:**
  - Reviewer completes annotation of a 60-min fixture in ≤30 min (dry-run in W10).
  - Visual discipline hooks pass.

### T37 — Final decision endpoint + Markdown report

- **agent:** `backend-engineer`
- **parallel:** false
- **depends_on:** [T35]
- **contract:** `app/backend/openapi.yaml`
- **description:**
  `POST /sessions/:id/decision`. Writes to `session_decision` (append-only). `GET /sessions/:id/report.md` renders a Markdown template from transcript + corrections + final decision.

  **Language:** reports are produced in **English** — audience is reviewers and hiring managers. Transcript excerpts stay in the candidate's original language (Ukrainian per §11); surrounding narrative, scores, and rationale are English. Template file lives at `app/backend/templates/report.md.j2` and is explicit about which sections are EN-only vs. verbatim.

- **acceptance:**
  - Sample report renders and is reviewed for tone by Ihor.
  - EN/UA separation verified: a fixture session with Ukrainian transcript produces a report where only quoted answers are Ukrainian; all headings, scoring prose, and decision rationale are English.

---

## Tier 7 (W9) — Observability & Evals

**Goal:** team has dashboards for quality + cost; golden-dataset framework in place.

### T38 — Cloud Monitoring dashboards + alerts

- **agent:** `infra-engineer`
- **parallel:** true (with T39, T40)
- **depends_on:** [T21]
- **contract:** none (dashboards as Terraform)
- **description:**
  Dashboards: cost/session, latency per agent (p50/p95), error rate per agent, schema-miss rate. Alerts (Terraform): cost_per_session > $2.5, p95_latency > 20 s, error_rate > 5 %, schema_miss_rate > 3 %. All alerts routed to #techscreen-ops Slack.
- **acceptance:**
  - Synthetic overrun test fires each alert at least once.

### T39 — TurnTrace viewer (internal)

- **agent:** `frontend-engineer`
- **parallel:** true
- **depends_on:** [T21]
- **contract:** `app/backend/openapi.yaml`
- **description:**
  `/admin/traces`: filter by session, agent, model, error-type; view raw prompt/response; side-by-side diff across prompt versions. Internal-only, `admin` role.
- **acceptance:**
  - Diff view works on two prompt versions of the same agent.

### T40 — Golden-dataset framework + calibration CI (§13)

- **agent:** `prompt-engineer`
- **parallel:** true
- **depends_on:** [T17, T24]
- **contract:** `evals/schema.md` + `.github/workflows/calibration.yml`
- **description:**
  `evals/interviewer/`, `evals/assessor/`, `evals/planner/` — each a JSONL of (input, expected_output, evaluation_mode). CLI `python -m evals.run --agent assessor --version v0001` runs the agent against the golden set and reports coverage agreement + schema validity. Uses the `calibration-run` skill.

  **Why both T17 and T24 are required:** T17 provides Interviewer + Assessor schemas; T24 provides Planner schema. Evals for all three agents need their schemas committed before the runner can validate outputs.

  **§13 calibration CI (warning-only, never blocks merge):**
  - `.github/workflows/calibration.yml` triggered on: PRs that touch `prompts/**`, nightly cron, manual dispatch.
  - Runs the three agents against the golden set using the PR's prompt version, posts a PR comment with: agreement % vs baseline, trend arrow, schema-miss rate, cost delta.
  - `continue-on-error: true` — results **never** hard-fail the build (§13). Reviewer agent flags if agreement drops > 10 pp but does not block merge.

- **acceptance:**
  - Baseline report for each agent (interviewer, assessor, planner) committed at `evals/reports/v0001-baseline.md`.
  - Calibration workflow runs on a fixture PR touching `prompts/assessor/` and posts a comment; red result does **not** block merge.
- **references:** constitution §13

---

## Tier 8 (W10) — Calibration

**Goal:** prompts tuned on known candidates; model A/B decision made; ready for pilot.

### T41 — Internal calibration interviews (3–5)

- **agent:** `human` + `prompt-engineer`
- **parallel:** false
- **depends_on:** [Tier 7 complete]
- **contract:** none
- **description:**
  Run 3–5 mock interviews with internal engineers role-playing strong/weak/middle candidates. Review `turn_trace` rows end-to-end. Iterate Interviewer + Assessor prompts using the `agent-prompt-edit` skill (produces versioned `prompts/<agent>/v0002/`). Lock prompts when agreement hits target.
- **acceptance:**
  - At least one `v0002` prompt folder committed per agent with `notes.md` explaining the delta.

### T42 — Model A/B: Gemini 2.5 Pro vs Claude Sonnet 4.6

- **agent:** `prompt-engineer`
- **parallel:** true (with T41, T43 — W9→W10 slack)
- **depends_on:** [T40]
- **contract:** `adr/ADR-022-pilot-model-choice.md`
- **description:**
  Run both models against the same Assessor golden set. Measure: coverage agreement vs reviewer, schema-miss rate, p95 latency, cost/1k tokens. Decision written as ADR-022; commit the ADR in the same PR.

  **Template:** Copy `adr/TEMPLATE.md` (same structure as ADR-001..021) — sections: Context, Decision, Alternatives considered, Consequences, Measurements (new for -022). Measurements table schema: `model | coverage_agreement_% | schema_miss_% | p95_latency_s | cost_per_1k_tokens_usd | n_sessions`.

  **Why parallel with T41:** earlier plan gated T42 on T41 (prompt-freeze) — that serialised the whole calibration tier. With golden set (T40) landed, A/B can run against **current** prompts (v0001). If T41 later produces v0002 that materially changes agent behaviour, T42 re-runs — cheap (<15 min) vs. losing a week of wall-clock.

- **acceptance:**
  - ADR merged with decision + measurements table.
  - If T41 lands v0002 after T42 merges, a `T42-rerun` follow-up task is auto-filed (the `prompt-engineer` agent template includes this rule).

### T43 — Reviewer dry-runs

- **agent:** `human`
- **parallel:** true (with T42)
- **depends_on:** [T41]
- **contract:** none
- **description:**
  Two tech experts each annotate 2 of the calibration sessions through the Reviewer UI. Capture UX issues in GitHub issues with label `reviewer-ux`. Prioritise blockers for Tier 9.
- **acceptance:**
  - Reviewer UX issues triaged; no P0/P1 left open.

### T44 — Pilot prompt freeze

- **agent:** `prompt-engineer`
- **parallel:** false (gate)
- **depends_on:** [T41, T42, T43]
- **contract:** none
- **description:**
  Tag `prompts/interviewer/v1.0-pilot/`, `prompts/assessor/v1.0-pilot/`, `prompts/planner/v1.0-pilot/`. Update `configs/models.yaml` with the A/B winner.

  **Risk — T41 / T42 mismatch:** T42 (model A/B) runs against v0001 prompts (see T42 "parallel with T41" rationale). If T41 lands a material v0002 after T42's ADR-022 merges, the A/B result may no longer hold on the tuned prompts. Handling:
  - If v0002 delta is **cosmetic** (wording tweaks, no new scoring logic): freeze as-is, note in ADR-022 addendum.
  - If v0002 delta is **material** (new rubric paths, new schema fields, different evaluation flow): file `T44a-recalibrate` — re-run A/B on v0002, update ADR-022 with a follow-up measurement row, refreeze. Budget: 1 day.
  - Decision gate lives in T44, not T42 — prompt-engineer owns the material/cosmetic call, reviewer signs off.

- **acceptance:**
  - Tag present; CI calibration eval on the tagged prompts is warning-only (§13).
  - If `T44a-recalibrate` was filed, it is closed before Tier 9 starts (blocks T45+).

---

## Tier 9 (W11) — Pilot Preparation

**Goal:** everything needed to launch with real candidates is in place.

### T45 — Security review

- **agent:** `human` + `infra-engineer`
- **parallel:** true (with T46, T47, T48)
- **depends_on:** [Tier 8 complete]
- **contract:** none
- **description:**
  Checklist: SSO config, secret rotation plan, data-access audit (read-only queries on audit tables never raise), dependency scan (Dependabot + `pip-audit` + `pnpm audit`), Terraform drift check.

  **Caveat — retention policy is an internal draft, not legally reviewed.** The 18-month retention window in T46 was set by Ihor as a reasonable internal default for a proof-of-concept. No external DPO, privacy counsel, or compliance review has validated it against GDPR / N-iX corporate policy / candidate-consent language. This review:
  - Documents the 18-month window as _provisional_.
  - Logs a follow-up action item to commission legal review **before scale** (before Phase 2 or before onboarding external candidates beyond the pilot cohort — whichever comes first).
  - Does **not** block pilot launch — the pilot cohort is internal/invited, consent is handled by the pilot intro page, and any deletion request within the 18-month window is honoured via T46.

- **acceptance:**
  - Sign-off in `docs/engineering/security-review-2026-pilot.md`; no Critical CVEs open.
  - Retention-policy caveat recorded in the sign-off doc with a "re-evaluate before scale" flag.

### T46 — GDPR delete endpoint + retention policy

- **agent:** `backend-engineer`
- **parallel:** true
- **depends_on:** [T34]
- **contract:** `app/backend/openapi.yaml`
- **description:**
  `DELETE /candidates/:email` soft-erases PII (name, email → hash, raw transcript → redacted), but preserves `turn_trace`/`assessment` as required by §3. Background job purges beyond window with audit row.

  **Retention window — 18 months — is an internal draft policy, not legally reviewed.** See T45 caveat. For the MVP pilot this is sufficient because:
  - Consent is collected on the intro page (UA copy in T48), referencing the 18-month window.
  - The pilot cohort is small and invited; no external data subjects outside the consenting set.
  - `DELETE /candidates/:email` honours earlier deletion requests immediately, regardless of window.

  **Before scale** (Phase 2 / external rollout): the retention window, consent copy, and soft-erase semantics must be reviewed by privacy counsel and reconciled with N-iX corporate policy. Re-evaluation action item tracked in T45 sign-off doc.

- **acceptance:**
  - Integration test: delete → GET returns redacted rows; `turn_trace` still exists with candidate PII removed.
  - `configs/retention.yaml` commits the 18-month value with a header comment marking it "internal draft, not legally reviewed, re-evaluate before Phase 2".

### T47 — Pilot operations playbook

- **agent:** `human`
- **parallel:** true
- **depends_on:** []
- **contract:** `docs/engineering/pilot-ops-playbook.md`
- **description:**
  How recruiters assign interviews, incident handling (where to look in dashboards, who to page), escalation path. Include a runbook for "candidate reports a bug mid-session".
- **acceptance:**
  - Playbook reviewed by recruiter team lead.

### T48 — Candidate comms templates

- **agent:** `human` + `prompt-engineer`
- **parallel:** true
- **depends_on:** [T30]
- **contract:** none
- **description:**
  Ukrainian copy: invitation email, intro page, FAQ, incident-apology template. Reviewed by Ihor + recruiter team.
- **acceptance:**
  - Copy committed under `prompts/shared/candidate-comms/`.

### T48a — Concurrent-session smoke

- **agent:** `backend-engineer` + `infra-engineer`
- **parallel:** true (with T45, T46, T47, T48)
- **depends_on:** [T44]
- **contract:** none
- **description:**
  **Why this exists:** the whole plan through T48 validates a _single_ session end-to-end. The pilot (T50) sends 12–15 invitations; reviewers will kick off multiple sessions in the same day, some overlapping. We have never exercised the system under concurrency — Vertex quota contention, Cloud Run autoscale cold-starts, WebSocket connection limits, DB connection pool saturation, session-cost-guard middleware under parallel writes.

  **Scope:** launch **3 concurrent sessions** against the Cloud Run deploy (traffic split can stay at 0 %; target `--revision` directly) using three internal runners + a scripted Vertex-mock-fallback candidate. Watch:
  - Vertex 429s (should see 0 at 60 rpm × 3 ≤ quota — see T01a).
  - WebSocket message ordering within each session (no cross-session bleed).
  - Cloud Run instance count and cold-start latency.
  - DB connection pool (`SELECT count(*) FROM pg_stat_activity WHERE datname='techscreen'`) ≤ pool size.
  - Per-session cost-ceiling enforcement (T21) — each session tracked independently.

  3 is the floor, not a target: enough to catch pool/quota/state-bleed issues without burning cost budget. Pilot will ramp higher; if anything fails here, scale-up after T50 will be worse.

- **acceptance:**
  - 3 sessions complete concurrently with zero Vertex 429s, zero WebSocket cross-talk, Cloud Run scales as expected, DB pool stays under 80 % utilisation.
  - Results recorded in `docs/engineering/load-smoke-2026-pilot.md`. Any failure files a P0 blocker for T49.

### T49 — Full pilot dry-run

- **agent:** `human` + `orchestrator`
- **parallel:** false (gate)
- **depends_on:** [T45, T46, T47, T48, T48a]
- **contract:** none
- **description:**
  One internal candidate runs the full pilot flow end-to-end: invitation email → intro → session → reviewer annotation → final decision. Observability dashboards watched live.
- **acceptance:**
  - Dry-run completes with zero P0/P1 bugs; retro notes added to `docs/engineering/pilot-ops-playbook.md`.

---

## Tier 10 (W12) — Pilot Execution

**Goal:** run real pilot, collect metrics, validate success criteria.

### T50 — Pilot candidate rollout

- **agent:** `human`
- **parallel:** false
- **depends_on:** [T49]
- **contract:** none
- **description:**
  Send 12–15 invitations (targeting 10 completed interviews). Daily triage of incidents. No new features; only bug fixes behind feature flags.
- **acceptance:**
  - ≥10 completed interviews in the 1-week pilot window.

### T51 — Metrics collection + report

- **agent:** `prompt-engineer` + `human`
- **parallel:** false
- **depends_on:** [T50]
- **contract:** `docs/engineering/pilot-report-2026-qN.md`
- **description:**
  Measure against §7 targets: inter-rater agreement, FP/FN, session completion rate, cost/session, avg LLM latency, coverage. Per-candidate pass, per-competency breakdown. Data pulled from append-only audit tables.

  **Scope — internal, not a polished stakeholder deliverable.** This report's primary audience is the engineering team + Ihor, driving the T52 go/no-go gate. It is **not** a packaged executive summary — no marketing polish, no external formatting. A separate stakeholder brief can be derived later if Phase 2 is approved.

  **Language:** English. Section structure:
  1. Raw metrics table vs §7 targets (✅ / ⚠ / ❌).
  2. Per-session notes (one line each): completed / failed-reason / cost / p95 latency.
  3. Per-competency coverage heatmap.
  4. Incidents log pointer (`docs/engineering/pilot-ops-playbook.md` retro section).
  5. Recommendation for T52: proceed / iterate / pivot, with rationale in ≤ 300 words.

- **acceptance:**
  - Report merged; table of metrics vs targets with ✅/⚠/❌ per row.
  - Recommendation block present; T52 retro can cite it directly.

### T52 — Retrospective + gate decision

- **agent:** `human`
- **parallel:** false (gate)
- **depends_on:** [T51]
- **contract:** none
- **description:**
  Retro with engineers + recruiters + reviewers. Decision: proceed to Phase 2 / iterate MVP / pivot. Capture decisions in `docs/specs/roadmap.docx` (update H1 triggers).
- **acceptance:**
  - Retro notes committed; Phase 2 kickoff plan (if applicable) drafted.

---

## Appendix A — Cross-cutting contracts

These files must exist and stay committed before parallel fan-out in their respective tiers:

| Contract                                                      | Commit task | Blocks tier                    | Owner                                                                                    |
| ------------------------------------------------------------- | ----------- | ------------------------------ | ---------------------------------------------------------------------------------------- |
| `app/backend/openapi.yaml` (stub)                             | T02         | 2, 4, 5, 6, 7, 9               | backend-engineer                                                                         |
| `app/backend/openapi.yaml` (Planner slice)                    | T27a        | 4                              | backend-engineer                                                                         |
| `docs/contracts/rubric.schema.json`                           | T08         | 2                              | backend-engineer                                                                         |
| `docs/contracts/rubric-snapshot.schema.json`                  | T15         | 3                              | backend-engineer                                                                         |
| `docs/contracts/feature-flag.schema.json`                     | T05a        | 1+ (every risky feature after) | backend-engineer                                                                         |
| `prompts/<agent>/v0001/schema.json` (per-agent, no aggregate) | T17         | 3                              | prompt-engineer — backend wrappers (T18/T19/T24) import directly; see T17 ownership note |
| `docs/contracts/turn-trace.schema.json`                       | T21         | 3                              | backend-engineer                                                                         |
| `docs/contracts/state-machine.md`                             | T20         | 3                              | backend-engineer                                                                         |
| `docs/contracts/ws-protocol.md` + `ws-messages.schema.json`   | T29a        | 5                              | backend-engineer                                                                         |
| `docs/contracts/interview-plan.schema.json`                   | T25         | 4                              | backend-engineer                                                                         |
| `docs/contracts/id-token-claims.json`                         | T07         | 1                              | infra-engineer                                                                           |

**Rule:** a task with `parallel: true` whose `contract:` points to a row in this table cannot start until the corresponding **Commit task** is merged. Reviewer checks this on every PR.

---

## Appendix B — Reviewer gate (applies to every task)

Every PR is reviewed by `.claude/agents/reviewer.md` before merge. The task is not `completed` until reviewer returns ✅. Violations that block merge:

- Constitution invariants (§1–§20 per `.specify/memory/constitution.md`).
- Secrets in diff (gitleaks hit).
- New service function or endpoint without adjacent test.
- Migration without linked ADR when destructive.
- Prompt version edited in place (must create new `v<next>/` folder).
- Frontend PR without `Baseline Check` block.
- Visual discipline: arbitrary Tailwind, raw hex outside `tokens.ts`, `dark:`, shadows outside primitives, multiple primary CTAs, brand orange outside allowlist, decorative motion.
- Cross-layer parallel work without a committed contract (Appendix A).

---

## Appendix C — How to propose a change to this plan

1. Open a `/specify` session for the scope change.
2. Produce a diff against this file in the same PR.
3. Do **not** renumber existing task IDs; append `T53+` or mark a task `deprecated: true` with a pointer.
4. If the change adds parallel fan-out, commit the contract file(s) in the same PR.
5. `reviewer` verifies Appendix A and Appendix B compliance.

---

## Appendix D — Per-agent workload + bottlenecks

Counts are absolute task counts per agent across the full 12-week plan. Flags highlight weeks where one agent is the critical path.

| Agent               | Tasks | Peak week                                         | Notes                                                                                                                                                                                                                                                                                                                                                          |
| ------------------- | ----- | ------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `backend-engineer`  | 25    | W7 (T28, T29a, T29, T31)                          | **Bottleneck tier.** T30 (frontend) can start right after T29a lands, so frontend is not blocked — but backend has four sequential tasks in one week. Mitigation: T31 (session reliability) can slip into W8 if needed without blocking Tier 5 gate, since T31's acceptance criteria are about robustness not correctness. T48a shares load with infra in W11. |
| `frontend-engineer` | 7     | W7 (T30), W9 (T36)                                | Light load; spare cycles available for design polish or helping with T37 Markdown templates.                                                                                                                                                                                                                                                                   |
| `infra-engineer`    | 10    | W1 (T06, T06a, T09, T10)                          | Front-loaded; after W2 mostly observability (T38) + security review (T45) + concurrent-session smoke (T48a). Also owns T01a (Vertex quota) and co-owns T48a.                                                                                                                                                                                                   |
| `prompt-engineer`   | 9     | W10 (T41, T42, T44)                               | Calibration tier is the prompt-engineer's heavy week. After W6 T27a unblock, T42 can run in parallel with T41 (see W6 fix). Counts include shared slots with `human` on T48 and with `prompt-engineer` on T51.                                                                                                                                                 |
| `human`             | 11    | W10–W11 (T41, T43, T45, T47)                      | Ihor + recruiter team + tech experts. No code but heavy calendar load. Shared slots with `prompt-engineer` and `infra-engineer`.                                                                                                                                                                                                                               |
| `orchestrator`      | 4     | W1 (T11), W5 (T23), W9 (T40 framework), W11 (T49) | Gate/checkpoint only; shared human-paired slots.                                                                                                                                                                                                                                                                                                               |

**Note on counts:** tasks with multiple agents (e.g., T48a: `backend-engineer` + `infra-engineer`) are counted once per agent. This reflects that each co-owner carries real work on that task. Total per-agent count sums above the 57 unique tasks because of this deliberate double-counting.

**Escalation rules:**

- If any agent finishes their week's tasks more than 2 days behind the tier gate, orchestrator escalates to Ihor with proposed re-slicing.
- If `backend-engineer` is the bottleneck on a given week, frontend/infra cycles are **not** re-allocated without a spec change — cross-agent substitution requires a `/specify` amendment per Appendix C.

---

**End of plan.** Entry point back: [`CLAUDE.md`](../../CLAUDE.md) · [`docs/specs/mvp-scope.docx`](../specs/mvp-scope.docx) · [`docs/engineering/multi-agent-workflow.md`](./multi-agent-workflow.md).
