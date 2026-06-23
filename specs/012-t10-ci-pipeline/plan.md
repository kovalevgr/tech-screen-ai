# Implementation Plan: CI pipeline + migration approval gate (T10)

**Branch**: `012-t10-ci-pipeline` | **Date**: 2026-04-28 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/012-t10-ci-pipeline/spec.md`

## Summary

T10 lights up the project's PR-time safety net. Six deliverables in one PR:

1. **`.github/workflows/ci.yml`** — one workflow, five jobs. `backend` (alembic + pytest + ruff + ruff-format + mypy --strict + OpenAPI byte-identical), `frontend` (eslint + tsc + jest + tokens:check), `smoke` (T09's `scripts/smoke-docker-stack.sh` on host Docker), `lint` (`pre-commit run --all-files`), and a conditional `migration-sql-render` (only when `alembic/versions/**` changes). Concurrency-cancel per ref. Minimal `permissions:`; the migration job elevates to `pull-requests: write`.
2. **`scripts/ci-render-migration-sql.sh`** — renders `alembic upgrade head --sql` (offline; no live DB) and writes the DDL to stdout for the PR-comment step.
3. **`scripts/ci-detect-destructive-ddl.sh`** — scans changed `alembic/versions/*.py` for `DROP COLUMN` / `DROP TABLE` / type-narrowing `ALTER COLUMN ... TYPE`; sets `needs_adr=true|false` on `$GITHUB_OUTPUT`.
4. **`scripts/ci-reviewer.sh`** — placeholder; prints the DEFERRED message, exits 0. Real Claude-in-CI integration is a documented follow-up.
5. **`docs/engineering/ci.md`** — the canonical CI reference (sibling to T09's `docker.md`): jobs, required-checks branch-protection contract, the migration-approval gate end-to-end, the destructive-DDL pattern set, the reviewer-agent deferral, troubleshooting, caching.
6. **`README.md`** — a short "CI pipeline" subsection linking the new doc.

§10 migration approval is encoded as a **label-based** gate (no GitHub App): CI renders the SQL into a collapsed PR comment + auto-applies `needs-adr` on destructive DDL; a human applies the `migration-approved` label; T06a's `/deploy` (future) enforces it at deploy time. The reviewer-agent invocation the implementation-plan mentions is honestly DEFERRED — T10 ships a placeholder + the docs that say so; the real Anthropic-API-in-CI wiring (with cost controls) is a follow-up.

**Honest scope boundary**: the full workflow can only be *exercised* on GitHub (PR comments, labels, concurrency-cancel, branch protection). T10 validates by inspection + `actionlint` + local dry-runs of the bash helpers + a documented "first-PR-on-GitHub" checklist the operator runs once. This mirrors T06's "Terraform applies need a live project" honesty.

Single committer — `agent: infra-engineer`, `parallel: false`. No new Python dependency. No app code change. The 138-test backend suite stays the regression baseline.

## Technical Context

**Language/Version**: YAML (GitHub Actions) + Bash. No Python code authored beyond what the workflow invokes (the existing `app.backend.generate_openapi`, `alembic`, `pytest`).

**Primary Dependencies**: GitHub Actions ecosystem only — `actions/checkout@v4`, `docker/setup-buildx-action@v3`, `actions/github-script@v7` (PR comment + label), and the repo's existing `docker compose` + `pre-commit` + `actionlint`. No new entry in `pyproject.toml` / `uv.lock` / `package.json`.

**Storage**: N/A — CI is stateless. The `backend` and `migration-sql-render` jobs bring up an ephemeral tmpfs Postgres (the test-stack `db` profile) that dies with the runner.

**Testing**: T10 ships YAML + bash, so its "tests" are:
- `actionlint` on `ci.yml` (runs in the `lint` job on the very PR that introduces it — self-verifying; also runnable locally via the pre-commit `actionlint` hook).
- `shellcheck` on the three new bash helpers (added to `.pre-commit-config.yaml`; research §10).
- Local dry-runs: `ci-render-migration-sql.sh` produces SQL against the test stack; `ci-detect-destructive-ddl.sh` flags a `DROP COLUMN` fixture and passes an `ADD COLUMN` fixture.
- The existing 138-test backend suite remains green (regression baseline; the `backend` job runs it, and we re-run locally).
- The GitHub-only behaviours (PR comment in place, label application, concurrency-cancel) are validated by a documented manual first-PR checklist in `quickstart.md`, NOT by local execution — called out honestly.

**Target Platform**: GitHub-hosted `ubuntu-latest` runners (Docker + Compose v2 preinstalled). No self-hosted runner. The `smoke` job uses the runner's host Docker — no Docker-in-Docker.

**Project Type**: CI/infrastructure. No application slice.

**Performance Goals**:
- Warm-cache full run (4 required jobs in parallel): < 5 minutes (SC-001).
- Cold-cache full run: < 12 minutes (spec assumption).
- `migration-sql-render` job (when triggered): < 90 seconds (SC-002).
- `needs-adr` auto-label: < 60 seconds (SC-005).

**Constraints**:
- **§7 Docker parity** — `backend`/`frontend` jobs build the same `dev` Dockerfile targets used in dev + the test compose; `smoke` uses the dev compose via T09's script. CI does not introduce a third image shape.
- **§10 migration approval** — label-based, no GitHub App. CI renders SQL + auto-labels `needs-adr`; human applies `migration-approved`; T06a enforces. Documented in `ci.md`.
- **§5/§6 no secrets** — zero inline credential in `ci.yml`. Only the GitHub-provided `GITHUB_TOKEN` (scoped `pull-requests: write` on the migration job) + the pre-existing WIF placeholders in the unrelated `sync-feature-flags.yml`.
- **§14 contract-first** — the workflow + helper scripts + `ci.md` are the contract T06a (`/deploy` migration gate) and T11 (Tier-1 smoke) bind to.
- **§17 / §18** — spec precedes; single `infra-engineer`, `parallel: false`.
- **OpenAPI diff zero** — the `backend` job runs the regen-and-diff check; no route added by T10.
- **138 tests stay green** — the `backend` job is the enforcement; locally re-run to confirm.

**Scale/Scope**: One PR. 4 new files (workflow + 3 scripts), 1 new doc, 1 doc edit (README), 1 config edit (`.pre-commit-config.yaml` for shellcheck). ~400 lines net.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| §   | Principle                              | Applies to T10?                                                                                                                                          | Status |
| --- | -------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| 1   | Candidates and reviewers come first    | Indirect — CI is the gate that keeps every later auditability-bearing feature from regressing silently.                                                   | Pass   |
| 2   | Deterministic orchestration            | N/A — no LLM in T10 (the reviewer-agent step is a deferred placeholder).                                                                                  | N/A    |
| 3   | Append-only audit trail                | Indirect — the `backend` job runs the §3 invariant tests on every PR, making the append-only guarantee continuously enforced.                            | Pass   |
| 4   | Immutable rubric snapshots             | Indirect — the `backend` job runs T08's §4 immutability tests every PR.                                                                                   | Pass   |
| 5   | No plaintext secrets                   | Yes — no inline secret; only `GITHUB_TOKEN`. `gitleaks` + `detect-secrets` run in the `lint` job on the diff.                                              | Pass   |
| 6   | Workload Identity Federation only      | N/A in T10 — no GCP auth. (The unrelated `sync-feature-flags.yml` keeps its WIF placeholders.)                                                            | N/A    |
| 7   | Docker parity dev → CI → prod          | Yes — CI builds the same `dev` target as the test stack + uses T09's dev-stack smoke. No third image shape.                                                | Pass   |
| 8   | Production-only topology               | N/A — CI is ephemeral; no environment created.                                                                                                            | N/A    |
| 9   | Dark launch by default                 | N/A — CI is not a user-facing feature.                                                                                                                     | N/A    |
| 10  | Migration approval                     | **Primary purpose.** Label-based gate: SQL rendered into a PR comment, `needs-adr` auto-applied on destructive DDL, `migration-approved` human-applied.   | Pass   |
| 11  | Hybrid language                        | Yes — workflow, scripts, docs are English; no candidate-facing text.                                                                                       | Pass   |
| 12  | LLM cost and latency caps              | N/A — no LLM call (reviewer-agent deferred). The deferral itself is a cost-control decision (no uncontrolled Anthropic spend in CI yet).                  | Pass   |
| 13  | Calibration never blocks merge         | N/A — T10 adds no calibration gate. (Calibration is T40, warning-only.)                                                                                    | N/A    |
| 14  | Contract-first for parallel work       | Yes — the workflow + scripts + `ci.md` are the committed contract T06a + T11 bind to.                                                                      | Pass   |
| 15  | PII containment                        | Yes — CI logs HTTP status codes + test names + rendered DDL (no candidate PII). The migration SQL is schema DDL, never row data.                          | Pass   |
| 16  | Configs as code                        | Yes — the workflow is itself config-as-code; its canonical state is what this PR produces.                                                                | Pass   |
| 17  | Specifications precede implementation  | Yes — `speckit-specify` → this `speckit-plan` → `speckit-tasks` → `speckit-implement`.                                                                     | Pass   |
| 18  | Multi-agent orchestration is explicit  | Yes — `agent: infra-engineer`, `parallel: false`.                                                                                                          | Pass   |
| 19  | Rollback is a first-class operation    | Indirect — `git revert` of T10 cleanly removes the workflow; no production state.                                                                          | Pass   |
| 20  | Floor, not ceiling                     | Pass.                                                                                                                                                      | Pass   |

**Gate result**: PASS. No violations. The reviewer-agent deferral (§12 cost-control) and the GitHub-only-exercisable boundary are documented honestly, not as violations.

## Project Structure

### Documentation (this feature)

```text
specs/012-t10-ci-pipeline/
├── spec.md
├── plan.md                  # This file
├── research.md              # Phase 0 — 10 implementation-altitude decisions
├── data-model.md            # Phase 1 — operational entities (jobs, labels, marker, DDL patterns, required checks)
├── contracts/
│   └── plan-contract.md     # Phase 1 — pointer to the workflow + scripts + ci.md
├── quickstart.md            # Phase 1 — reviewer walkthrough + the manual first-PR-on-GitHub checklist
├── checklists/requirements.md
└── tasks.md                 # speckit-tasks (NOT this command)
```

### Source / config (repository root, after T10 merges)

```text
.
├── .github/
│   └── workflows/
│       ├── ci.yml                          # NEW — 5 jobs (backend / frontend / smoke / lint / migration-sql-render)
│       └── sync-feature-flags.yml          # untouched (T05a)
├── scripts/
│   ├── ci-render-migration-sql.sh          # NEW — alembic upgrade head --sql → stdout
│   ├── ci-detect-destructive-ddl.sh        # NEW — scan changed migrations; set needs_adr output
│   ├── ci-reviewer.sh                      # NEW — placeholder; prints DEFERRED, exits 0
│   ├── smoke-docker-stack.sh               # untouched (T09)
│   ├── check-feature-flag-registration.py  # untouched (T05a)
│   └── check-rubric-schema.py              # untouched (T08)
├── docs/engineering/
│   └── ci.md                               # NEW — canonical CI reference (7 sections)
├── .pre-commit-config.yaml                 # EDITED — add shellcheck for scripts/*.sh
└── README.md                               # EDITED — "CI pipeline" subsection → docs/engineering/ci.md
```

**Structure Decision**: The workflow joins `sync-feature-flags.yml` under `.github/workflows/`. The three CI helper scripts join the existing `scripts/` family (already copied into the test image by T05's Dockerfile `COPY scripts ./scripts`, so the migration-render helper can run inside the backend container). `docs/engineering/ci.md` sits beside `docker.md`, `feature-flags.md`, `cloud-setup.md`. `shellcheck` is added to the pre-commit chain so the new bash helpers (and T09's smoke script) stay honest going forward.

### Task labelling (for §18 / `/speckit-tasks`)

| Task slice                                              | Agent            | Parallel? | Depends on                  | Contract reference |
| ------------------------------------------------------- | ---------------- | --------- | --------------------------- | ------------------ |
| `scripts/ci-render-migration-sql.sh`                    | `infra-engineer` | false     | T05 alembic offline path    | spec FR-007        |
| `scripts/ci-detect-destructive-ddl.sh`                  | `infra-engineer` | false     | spec committed              | spec FR-008        |
| `scripts/ci-reviewer.sh`                                | `infra-engineer` | false     | spec committed              | spec FR-010        |
| `.pre-commit-config.yaml` shellcheck hook               | `infra-engineer` | false     | the 3 scripts exist         | research §10       |
| `.github/workflows/ci.yml` (5 jobs)                     | `infra-engineer` | false     | the 3 scripts exist         | spec FR-001..FR-009|
| `docs/engineering/ci.md`                                | `infra-engineer` | false     | workflow + scripts          | spec FR-013        |
| `README.md` CI subsection                               | `infra-engineer` | false     | ci.md exists                | spec FR-014        |
| Verification (actionlint + shellcheck + dry-runs + 138) | `infra-engineer` | false     | everything above            | spec SC-*          |

All slices sequential in one PR; no sub-agent fan-out.

## Phase 0 — Outline & Research

Research output: [research.md](./research.md). 10 implementation-altitude decisions, most pre-resolved by the user input:

1. **Reviewer-agent invocation** — placeholder + DEFERRED; follow-up task pointer; rationale (no API key in CI, no cost controls → §12 honesty).
2. **Cache strategy** — Buildx `type=gha` cache for the backend/frontend image layers; `actions/cache` for the pnpm store. Heaviest layer (`uv sync --frozen`) cached.
3. **Migration SQL offline render** — `alembic upgrade head --sql` from a fresh test-stack backend container (T05 research §1 confirmed offline rendering works).
4. **Destructive-DDL regex set** — `DROP\s+COLUMN`, `DROP\s+TABLE`, `ALTER\s+COLUMN\s+\w+\s+TYPE` (the type-narrowing case); matching inside `op.execute("…")` strings is CORRECT here (that's exactly where destructive DDL lives), unlike a code-comment false-positive concern.
5. **PR-comment marker** — `<!-- ci:migration-sql-render -->` HTML marker; `actions/github-script` finds-and-updates the prior comment.
6. **Branch-protection required checks** — `backend` / `frontend` / `smoke` / `lint` required; `migration-sql-render` informational. Documented for the operator (GitHub setting, not CI logic).
7. **Concurrency** — `group: ${{ github.workflow }}-${{ github.ref }}`, `cancel-in-progress: true`.
8. **Smoke on host Docker** — no Docker-in-Docker; the runner's Docker runs the dev compose.
9. **pre-commit in CI** — `pip install pre-commit` + `actions/cache` for `~/.cache/pre-commit`; the `lint` job runs the full chain. The frontend-scoped hooks (eslint, tokens-drift, visual-discipline) `cd app/frontend` and need pnpm+node — research decides to `SKIP` them in the `lint` job (the `frontend` job already owns eslint+tsc+tokens, so running them again is duplicative) via the pre-commit `SKIP` env var; documented.
10. **shellcheck** — add a `shellcheck` pre-commit hook for `scripts/*.sh` (cheap; keeps the three new helpers + T09's smoke honest).

## Phase 1 — Design & Contracts

**Prerequisites**: `research.md` complete.

### Data model

See [data-model.md](./data-model.md). No DB entities. Operational entities: the five-job matrix (what each enforces + whether it's required), the label set (`migration-approved` human-applied / `needs-adr` auto), the PR-comment marker contract, the destructive-DDL pattern table, and the required-status-checks set the operator configures.

### Contracts

See [contracts/plan-contract.md](./contracts/plan-contract.md) — pointer to the runtime artefacts (`.github/workflows/ci.yml` + the three helper scripts + `docs/engineering/ci.md`), which ARE the contract T06a + T11 bind to.

### Quickstart

See [quickstart.md](./quickstart.md) — local validation (actionlint, shellcheck, helper dry-runs, 138-test re-run, ci.md reading test) PLUS the documented manual first-PR-on-GitHub checklist for the GitHub-only behaviours (the PR comment, the labels, concurrency-cancel) once branch protection is configured.

### Agent context update

`CLAUDE.md` carries no `<!-- SPECKIT START/END -->` markers (verified across T05–T09). No auto-block reintroduced.

### Re-evaluate Constitution Check (post-design)

Phase 0/1 commitments (placeholder reviewer, gha cache, offline SQL render, DDL regex, comment marker, required-checks set, concurrency, host-Docker smoke, pre-commit with frontend-hook SKIP, shellcheck) are all consistent with §5/§7/§10/§12/§14/§16/§17/§18. Gate remains **PASS**.

## Complexity Tracking

Not applicable — no Constitution Check violations.

| Violation | Why Needed | Simpler Alternative Rejected Because |
| --------- | ---------- | ------------------------------------ |
| *(none)*  | —          | —                                    |
