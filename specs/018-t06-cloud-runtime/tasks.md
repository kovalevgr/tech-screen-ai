# Tasks: Cloud runtime foundation — dev + prod (T06)

**Input**: Design documents from `specs/018-t06-cloud-runtime/`
**Prerequisites**: plan.md, spec.md (4 user stories), research.md (R1–R11), data-model.md, contracts/plan-contract.md, quickstart.md

**Tests**: no application test tasks — this feature ships HCL/YAML/SQL/docs. Verification = `terraform validate`/`plan`, `pre-commit` gates, and the operator acceptance sweep (quickstart § 8), encoded below as explicit tasks.

**Organization**: `agent: infra-engineer` for every task; `parallel: false` throughout (constitution §18; single state, single operator). Story labels map to spec.md: US1 = provision runtime, US2 = secrets, US3 = flag-sync live, US4 = DB migration-ready. Ordering honours the user constraint: governance → Terraform → workflow/scripts → docs → operator execution.

## Phase 1: Governance (FR-013 — must precede any HCL that assumes dev+prod)

- [ ] T001 Write `adr/023-dev-prod-environments.md` — context (owner decision 2026-07-02, spec Clarifications), decision (two long-lived envs in single project `tech-screen-493720`; release path keeps 0 %-traffic revision verification per ADR-012), alternatives (prod-only ADR-009 status quo; second GCP project), consequences (cost baseline ~$11–12 → ~$22–25/mo; drift risk owned by module symmetry; §12 interpretation intact), template per `adr/README.md` house style
- [ ] T002 Flip `adr/009-prod-only-topology.md` status block to `Status: Superseded by ADR-023` (keep body verbatim) and add the ADR-023 row to the `adr/README.md` index table
- [ ] T003 Amend `.specify/memory/constitution.md` §8 per the documented change procedure: retitle to "Two long-lived environments: dev and prod", rewrite body (single GCP project; no staging/QA/UAT gate; pre-release verification stays 0 %-traffic revisions; link ADR-023), fix the §7 cross-reference sentence ("We do not have a staging environment (see §8)" stays true — verify wording), bump Version section to v1.1 with dated changelog line

## Phase 2: Foundational Terraform (blocks US1–US4)

- [ ] T004 Create `infra/terraform/services.tf` — five `google_project_service` resources (`run`, `sqladmin`, `secretmanager`, `artifactregistry`, `clouderrorreporting`), `disable_on_destroy = false` (research R9: adopt already-enabled APIs)
- [ ] T005 Create `infra/terraform/modules/environment/variables.tf` and `outputs.tf` exactly per the data-model.md interface table (`env`, `name_suffix`, `secret_suffix`, `project_id`, `region`, `flag_sync_sa_email`, `backend_sa_create`; outputs: service URLs, `sql_connection_name`, SA emails)
- [ ] T006 Create `infra/terraform/modules/environment/main.tf` — part 1 (data plane): `google_sql_database_instance` (PG17, `db-f1-micro`, 10 GB SSD, daily backups 7-day retention, PITR, `deletion_protection = true`, flag `cloudsql.iam_authentication=on`, public IP no authorised networks), two `google_sql_database` (`techscreen`, `techscreen_shadow`), `google_sql_user` `techscreen_app` + `techscreen_migrator` (NO `password` attribute — research R6), `google_sql_user` type `CLOUD_IAM_SERVICE_ACCOUNT` for `var.flag_sync_sa_email` (research R5)
- [ ] T007 Extend `infra/terraform/modules/environment/main.tf` — part 2 (identity + secrets): backend SA (`count = var.backend_sa_create ? 1 : 0` for dev-create / prod-adopt shape per R3), frontend SA, five `google_secret_manager_secret` shells with `var.secret_suffix` naming and NO versions, per-secret `secretAccessor` bindings for the backend SA on `DATABASE_URL*`/`MAGIC_LINK_SIGNING_KEY*`/`SESSION_COOKIE_SECRET*`/`SENDGRID_API_KEY*` only (data-model matrix), project-level `cloudsql.client` + `logging.logWriter` + `monitoring.metricWriter` (+ `aiplatform.user` where `backend_sa_create`) for backend SA, `logWriter`+`metricWriter` for frontend SA
- [ ] T008 Extend `infra/terraform/modules/environment/main.tf` — part 3 (runtime): two `google_cloud_run_v2_service` (`techscreen-backend${var.name_suffix}`, `techscreen-frontend${var.name_suffix}`; min 0 / max 5, 1 vCPU / 1 GiB; image `us-docker.pkg.dev/cloudrun/container/hello`; `lifecycle { ignore_changes = [template[0].containers[0].image] }`; service accounts wired) + `google_cloud_run_v2_service_iam_member` `allUsers`/`roles/run.invoker` each (research R7)
- [ ] T009 Create `infra/terraform/artifact_registry.tf` (docker repo `techscreen`, `europe-west1`) and extend `infra/terraform/iam.tf` with `google_service_account` `techscreen-flag-sync`, `roles/cloudsql.client` + `roles/cloudsql.instanceUser` project bindings, and `google_service_account_iam_member` `roles/iam.workloadIdentityUser` for `principalSet://iam.googleapis.com/projects/463244185014/locations/global/workloadIdentityPools/github-actions/attribute.repository/<owner>/<repo>` (read exact repo from `git remote get-url origin`)
- [ ] T010 Create `infra/terraform/environments.tf` (`module "env_prod"` with empty suffixes + `backend_sa_create = false`; `module "env_dev"` with `-dev`/`_DEV` + `true`) and `infra/terraform/outputs.tf` (four service URLs, two connection names); remove the now-module-owned backend-SA trio from `infra/terraform/iam.tf` (state addresses documented in quickstart § 2); run `terraform fmt` + `terraform -chdir=infra/terraform validate` and reconcile quickstart § 2 `state mv` target addresses with the final resource labels

## Phase 3: US3 wiring — flag-sync workflow + grants (files only; execution in Phase 6)

- [ ] T011 [US3] Rewrite `.github/workflows/sync-feature-flags.yml`: fill `WIF_PROVIDER`/`WIF_SERVICE_ACCOUNT`/`GCP_PROJECT` with the data-model contract values, convert the job to `strategy: matrix: env: [dev, prod]` + `fail-fast: false` with per-env `CLOUD_SQL_INSTANCE` includes, set `DATABASE_USER: techscreen-flag-sync@tech-screen-493720.iam` (correcting the stale `techscreen_migrator` example), update the T05a-inert header comment to a "live since T06" note, keep Guard step semantics; verify with `actionlint` via pre-commit
- [ ] T012 [US3] Create `scripts/cloud-db-grants.sql` per data-model.md (GRANT `SELECT, INSERT, UPDATE` ON `feature_flag` TO the IAM user; header comment: per-env application, §3 tables untouched)

## Phase 4: Docs (US1–US4 supporting)

- [ ] T013 Rewrite `docs/engineering/cloud-setup.md` for post-T06 reality: dev+prod topology citing ADR-023, updated resource inventory (two instances, four services, ten secrets, registry), actual flat-root + `modules/environment` Terraform layout replacing the aspirational `envs/prod/` tree, updated IAM model (per-env SAs + flag-sync SA), updated cost table (~$22–25/mo), secret-fill + password + migration runbooks aligned with quickstart.md, document-versioning bump
- [ ] T014 Add correcting notes to `docs/engineering/implementation-plan.md` T06 description (Appendix C compliant — no renumbering): "Two workspaces" → "two environments via module × 2 in a single state (see specs/018 R2)"; `cloudsql.enable_pgvector` flag text → stale, extension created by migration 0001 (R1); acceptance bullet list appended with ADR-023 governance artefacts

## Phase 5: Pre-merge verification (branch-local)

- [ ] T015 Run `pre-commit run --all-files` (terraform_validate, actionlint, gitleaks, shellcheck, prettier) and `terraform -chdir=infra/terraform fmt -check` + `validate`; fix fallout; confirm zero credential-shaped strings and zero `google_sql_user.password` attributes in the diff (`git diff main --stat` review per quickstart § 9)

## Phase 6: Operator execution + acceptance (US1+US2+US3+US4 — live GCP, this checkout)

- [ ] T016 [US1] Execute quickstart §§ 1–3: `terraform init`/`state list`, the three `state mv` commands, `plan` (paste summary into PR body), `apply`, repeat `plan` → record SC-001 zero-diff
- [ ] T017 [US1] Acceptance SC-002: `gcloud run services describe` × 4 + `curl` 200 × 4; record in PR body table
- [ ] T018 [US2] Execute quickstart §§ 4–5 (set `techscreen_app`/`techscreen_migrator` passwords on both instances; fill secret versions per environment) then acceptance SC-003 (`gcloud secrets list` = 10 shells; per-secret IAM = matching env backend SA only) and SC-006 (`gcloud iam service-accounts keys list` per SA = system-managed only; gitleaks clean)
- [ ] T019 [US4] Execute quickstart § 6 (Auth Proxy + `alembic upgrade head` on `techscreen-pg` and `techscreen-pg-dev`) and § 7 (`scripts/cloud-db-grants.sql` on both), then acceptance SC-004 on both instances (pgvector row present; §3 trigger blocks `UPDATE turn_trace` as `techscreen_app`; `alembic current` = `0005`)
- [ ] T020 [US3] Trigger `sync-feature-flags.yml` via `workflow_dispatch` after merge-to-main (or branch-dispatch if configured); confirm Guard `skip=false`, both matrix legs green, `feature_flag` rows in both DBs with `updated_by='configs-as-code'` → SC-005; verify orphan-warning path still intact (T05a FR-009)
- [ ] T021 Governance + cost closure: SC-008 sweep (`git grep -n "prod-only\|only prod"` over active docs returns nothing stale; ADR index/status/constitution v1.1 verified) and SC-007 note (billing run-rate check scheduled +48 h; budgets untouched) — record both in the PR body acceptance table

## Dependencies

```text
Phase 1 (T001–T003) → Phase 2 (T004–T010) → Phase 3 (T011–T012) → Phase 4 (T013–T014) → Phase 5 (T015) → Phase 6 (T016 → T017 → T018 → T019 → T020 → T021)
```

Strictly sequential — single infra-engineer, one shared Terraform state, operator steps depend on the exact HCL from Phases 2–3. No [P] markers by design (constitution §18; plan.md `parallel: false`).

## Implementation strategy

- MVP increment = US1 (T016–T017): infrastructure exists and answers. US2/US4/US3 layer on the same apply without re-planning.
- T020 has a merge-order nuance: `push`-triggered sync runs on `main` only; the task allows `workflow_dispatch` from the PR branch if enabled, otherwise SC-005 is recorded immediately post-merge — noted so the PR isn't blocked on its own merge.
- Rollback story: pre-apply state backup is implicit in GCS versioning; `deletion_protection` guards instances; placeholder services carry no traffic.
