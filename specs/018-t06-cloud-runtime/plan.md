# Implementation Plan: Cloud runtime foundation — dev + prod (T06)

**Branch**: `018-t06-cloud-runtime` | **Date**: 2026-07-02 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/018-t06-cloud-runtime/spec.md` (topology clarified 2026-07-02: **dev + prod**)

## Summary

T06 turns the bootstrapped-but-empty GCP project into a runnable two-environment runtime. One PR, `agent: infra-engineer`, sequential (`parallel: false`). Deliverables:

1. **`infra/terraform/modules/environment/`** — reusable per-environment module: Cloud SQL PG17 instance (`db-f1-micro`, 10 GB, PITR, deletion protection, `cloudsql.iam_authentication=on`) with `techscreen` + `techscreen_shadow` databases and passwordless `techscreen_app`/`techscreen_migrator` users + a `CLOUD_IAM_SERVICE_ACCOUNT` user for the flag-sync SA; five Secret Manager shells; backend + frontend Cloud Run v2 services (placeholder hello image, `ignore_changes` on image) with per-env runtime SAs and per-secret accessor grants.
2. **Root instantiation** — `module "env_prod"` (documented names; adopts the existing `techscreen-backend@` SA via 3 × `terraform state mv`) and `module "env_dev"` (`-dev`/`_DEV` suffixes), plus project-global resources: 5 × `google_project_service` (adopting the APIs enabled during research), Artifact Registry repo `techscreen`, flag-sync SA + WIF binding to the existing `github-actions` pool.
3. **`.github/workflows/sync-feature-flags.yml`** — `<TODO-T06>` placeholders filled with real values; job matrixed over `env: [dev, prod]`, `fail-fast: false`; `DATABASE_USER` corrected to the IAM username `techscreen-flag-sync@tech-screen-493720.iam`.
4. **`scripts/cloud-db-grants.sql`** — post-migration grants for the flag-sync IAM user on `feature_flag`.
5. **Governance (FR-013)**: `adr/023-dev-prod-environments.md` (supersedes ADR-009), ADR-009 status flip, constitution §8 rewrite + v1.1 changelog, `adr/README.md` index row.
6. **Docs**: `cloud-setup.md` rewrite (dev+prod topology, real Terraform layout, updated runbooks), correcting notes in `implementation-plan.md` T06 (workspaces wording, stale `enable_pgvector` flag), `.env.example` header stays accurate.
7. **Operator execution** (Ihor's machine, this checkout): `terraform apply`, out-of-band passwords, secret fills, `alembic upgrade head` × 2 via Auth Proxy, grants SQL, §3 trigger smoke, `workflow_dispatch` of the flag sync — the full acceptance sweep (SC-001…SC-008).

**Honest scope boundary**: everything cloud-side can only be *exercised* against the live project; CI cannot re-run applies. Validation = `terraform validate`/`plan` + `pre-commit` (terraform_validate, actionlint, gitleaks) + the operator acceptance sweep recorded in quickstart.md — same honesty pattern as T10's "GitHub-only" boundary.

## Technical Context

**Language/Version**: Terraform HCL (Terraform 1.5.2 local, `required_version >= 1.5.0, < 2.0.0`), `hashicorp/google` `~> 6.0`; GitHub Actions YAML; Bash + SQL for operator scripts. No application code.

**Primary Dependencies**: existing GCS state backend + default-workspace state (6 T01a resources — verified 2026-07-02); existing `github-actions` WIF pool/provider (`projects/463244185014/.../providers/github`); Alembic chain 0001–0005 (schema source for the cloud DBs); T05a sync scripts (`scripts/sync_feature_flags_to_db.py`).

**Storage**: 2 × Cloud SQL PG17 (`techscreen-pg`, `techscreen-pg-dev`), each with `techscreen` + `techscreen_shadow`; 10 × Secret Manager shells; Artifact Registry `techscreen` (shared).

**Testing**: `terraform fmt -check` / `validate` / `plan` (clean second plan = SC-001); `pre-commit run --all-files` (gitleaks, terraform_validate, actionlint, shellcheck); operator acceptance sweep SC-002…SC-008 (live `gcloud`/`psql`/workflow run) recorded in quickstart.md; existing 163-test backend suite untouched (regression baseline — no app code changes).

**Target Platform**: GCP project `tech-screen-493720`, region `europe-west1`, single project hosting both environments (ADR-023).

**Project Type**: infrastructure (Terraform + CI workflow + governance docs). No application slice.

**Performance Goals**: apply completes in one operator session; placeholder services answer HTTP 200 within 10 s (SC-002); repeat `terraform plan` zero-diff (SC-001).

**Constraints**: §5/§6 — no plaintext secrets, no SA JSON keys, WIF-only CI; §8 (as amended by ADR-023) — two long-lived envs, no staging gate; §10 — no migration content changes (chain 0001–0005 applied as-is); §12 — new baseline ~$22–25/mo stays under PLN 200 budget; §16 — flag sync goes live for both envs; §17/§18 — this spec flow, single infra-engineer.

**Scale/Scope**: ~8 new/changed Terraform files (module + root), 1 workflow edit, 1 SQL script, 1 new ADR + 2 governance edits, 2 doc rewrites/notes. ~700 lines net. Zero app-code lines.

## Constitution Check

*GATE: evaluated against the constitution as it will stand post-ADR-023 (the §8 amendment ships in this PR per the constitution's own change procedure — ADR + owner acceptance, recorded in spec Clarifications 2026-07-02).*

| §   | Principle                             | Applies to T06?                                                                                                                                              | Status |
| --- | ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------ |
| 1   | Candidates and reviewers come first   | Indirect — cloud runtime is what makes audited real interviews possible at all.                                                                                | Pass   |
| 2   | Deterministic orchestration           | N/A — no LLM.                                                                                                                                                  | N/A    |
| 3   | Append-only audit trail               | Yes — migrations 0001–0005 applied to both cloud DBs bring the triggers + REVOKEs; operator smoke proves the trigger fires in the cloud (SC-004).             | Pass   |
| 4   | Immutable rubric snapshots            | Indirect — schema arrives with the migration chain; no behaviour change.                                                                                       | Pass   |
| 5   | No plaintext secrets                  | **Core.** Secret shells only; passwords set out-of-band (R6); nothing credential-shaped in Git/state/PR; gitleaks + forbid-env-values keep running.            | Pass   |
| 6   | WIF only                              | **Core.** Flag-sync SA authenticates via the existing OIDC pool; zero JSON keys (SC-006 checks `keys list`).                                                   | Pass   |
| 7   | Docker parity                         | N/A — no image content change; placeholder image is a bootstrap artefact explicitly handed off to T06a.                                                        | N/A    |
| 8   | Long-lived environments               | **Amended in this PR** — ADR-023 supersedes ADR-009; §8 text updated to dev+prod in one project, release path still 0 %-traffic revisions (ADR-012).           | Pass*  |
| 9   | Dark launch by default                | N/A — no user-facing feature; flag infra itself goes live syncing `enabled=false` defaults.                                                                    | N/A    |
| 10  | Migration approval                    | Yes — no new migration files; the chain 0001–0005 was already approved in its PRs; cloud application is an operator runbook step, not new DDL.                 | Pass   |
| 11  | Hybrid language                       | Yes — all artefacts English; no candidate-facing text.                                                                                                         | Pass   |
| 12  | LLM cost caps                         | Indirect — budgets untouched; ADR-023 records the doubled infra baseline so §12's $50 interpretation stays honest.                                             | Pass   |
| 13  | Calibration never blocks merge        | N/A.                                                                                                                                                           | N/A    |
| 14  | Contract-first for parallel work      | N/A — single agent, sequential; the module interface is documented in data-model.md for future tasks.                                                          | N/A    |
| 15  | PII containment                       | Yes — no PII exists in any T06 artefact; DBs start empty.                                                                                                      | Pass   |
| 16  | Configs as code                       | Yes — flag sync goes live for both envs; orphan-warning semantics preserved.                                                                                   | Pass   |
| 17  | Specs precede implementation          | Yes — this flow.                                                                                                                                               | Pass   |
| 18  | Multi-agent explicit                  | Yes — `agent: infra-engineer`, `parallel: false` throughout.                                                                                                   | Pass   |
| 19  | Rollback first-class                  | Yes — Terraform-managed resources revert by plan/apply of the previous HCL; deletion protection guards the DBs; no traffic shifts happen in T06.               | Pass   |
| 20  | Floor, not ceiling                    | Pass.                                                                                                                                                          | Pass   |

**Gate result**: PASS with one starred row — §8 changes *inside this PR* via the constitution's own documented procedure (ADR-023 + owner decision 2026-07-02). No silent edit: the changelog + ADR trail is FR-013/SC-008. Post-design re-check: unchanged.

## Project Structure

### Documentation (this feature)

```text
specs/018-t06-cloud-runtime/
├── spec.md
├── plan.md                  # This file
├── research.md              # Phase 0 — R1..R11 (live-verified where possible)
├── data-model.md            # Phase 1 — resource/identity/grant model, module interface
├── contracts/
│   └── plan-contract.md     # Phase 1 — pointer: module interface + workflow env contract
├── quickstart.md            # Phase 1 — operator runbook: state mv, apply, passwords, secrets, migrations, grants, acceptance sweep
├── checklists/requirements.md
└── tasks.md                 # speckit-tasks (NOT this command)
```

### Source / config (repository root, after T06 merges)

```text
.
├── adr/
│   ├── 009-prod-only-topology.md        # EDIT — Status: Superseded by ADR-023
│   ├── 023-dev-prod-environments.md     # NEW  — topology decision, cost, trade-offs
│   └── README.md                        # EDIT — index row
├── .specify/memory/constitution.md      # EDIT — §8 rewrite + v1.1 changelog (procedure-compliant)
├── .github/workflows/
│   └── sync-feature-flags.yml           # EDIT — placeholders filled; matrix over dev/prod
├── infra/terraform/
│   ├── backend.tf / provider.tf / versions.tf / variables.tf / terraform.tfvars   # untouched (backend/state key stable)
│   ├── billing.tf / iam.tf              # iam.tf EDIT — backend-SA resources move into the module (state mv), flag-sync SA + WIF binding added
│   ├── services.tf                      # NEW — 5 × google_project_service (disable_on_destroy=false)
│   ├── artifact_registry.tf             # NEW — shared docker repo `techscreen`
│   ├── environments.tf                  # NEW — module "env_prod" + module "env_dev"
│   ├── outputs.tf                       # NEW — service URLs, instance connection names
│   └── modules/environment/
│       ├── main.tf                      # SQL instance + dbs + users, Cloud Run v2 ×2, secrets ×5, SAs, IAM
│       ├── variables.tf                 # env, name_suffix, secret_suffix, project, region, flag_sync_sa_email, ...
│       └── outputs.tf
├── scripts/
│   └── cloud-db-grants.sql              # NEW — flag-sync IAM user grants on feature_flag
└── docs/engineering/
    ├── cloud-setup.md                   # REWRITE — dev+prod topology, real layout, runbooks
    └── implementation-plan.md           # NOTE — T06 wording corrections (workspaces → module×2; enable_pgvector stale)
```

**Structure Decision**: single root config + `modules/environment` instantiated twice in the existing default-workspace state (research R2); prod adopts the T01a backend SA via `terraform state mv` (R3); global resources stay at root.

## Complexity Tracking

No constitution violations to justify. The one deliberate governance change (§8) is executed through the constitution's own amendment procedure inside this PR — tracked as FR-013/SC-008, not as a violation.
