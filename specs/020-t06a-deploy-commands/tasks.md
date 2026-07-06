# Tasks: Deploy commands — `/deploy` + `/promote` + `/rollback` (T06a)

**Input**: Design documents from `specs/020-t06a-deploy-commands/`
**Prerequisites**: plan.md, spec.md (5 user stories), research.md (D1–D12), data-model.md, contracts/plan-contract.md, quickstart.md

**Tests**: no application test tasks — this feature ships YAML/HCL/bash/docs. Verification = `pre-commit` gates (actionlint, shellcheck, gitleaks, terraform_validate) plus the operator acceptance sweep (quickstart §7), encoded below as explicit tasks.

**Organization**: `agent: infra-engineer` for every task; `parallel: false` throughout (constitution §18; single branch, single operator). Story labels map to spec.md: US1 = deploy at 0 %, US2 = rollback, US3 = promote, US4 = §10 gate, US5 = asleep guard. Checked boxes attest to what this PR *authors*; Phase 5 tasks are operator-executed live and stay unchecked until the sweep runs.

## Phase 1: Workflows (US1–US5 core)

- [X] T001 [US1][US4][US5] Write `.github/workflows/deploy.yml`: `workflow_dispatch(env, service, git_ref)`; gate job — checkout `git_ref` fetch-depth 0, prod-ancestry check (D6), WIF auth as `techscreen-deployer@`, §10 migration gate (baseline from deployed backend image tag, fallback `origin/main~1`; PR-label verification via `gh api` with the run's own token — D7), Cloud SQL asleep guard with conditional severity (D11), gate summary; deploy job — per-service matrix (`fail-fast: false`), buildx `runtime` target linux/amd64, push `<sha>-<env>` to Artifact Registry (docker login via auth-step access token), `gcloud run deploy --no-traffic` with unique revision suffix + `--port` (backend 8000 / frontend 3000), move `candidate` tag via `update-traffic --update-tags`, 60 s HTTP smoke on the tag URL, always-run job summary. Frontend build args `NEXT_PUBLIC_API_BASE_URL` (live backend URL) + `NEXT_PUBLIC_APP_ENV`. No untrusted `${{ }}` inline in `run:` (FR-013)
- [X] T002 [US3] Write `.github/workflows/promote.yml`: `workflow_dispatch(env, service, percent)`; resolve `status.latestReadyRevisionName`, warn when a newer failed revision exists, no-op success when the target already serves the requested percent, `update-traffic --to-revisions=<name>=<pct>` (pinned, never `LATEST` — D8), before/after split in the summary
- [X] T003 [US2] Write `.github/workflows/rollback.yml`: `workflow_dispatch(env, service, revision?)`; primary = max-percent revision, target = override (readiness-checked) or newest ready revision older than primary (D9); one `update-traffic --to-revisions=<target>=100`, `date +%s` wall-clock around the call, duration + §19 framing in the summary; concurrency `cloud-run-<env>` with `cancel-in-progress: true` (preempts deploy/promote)

## Phase 2: Operator tooling (US5 supporting)

- [X] T004 [US5] ~~Write~~ `scripts/cloud-sql-power.sh` — **amended post-review: shipped separately via PR #19** (this branch forked before that merge and re-authored it; integration kept main's superset version, reviewer PR#20 W1). Original intent: — `wake|sleep|status` × `dev|prod`; thin `gcloud sql instances patch --activation-policy` wrapper + state report; operator-only (deployer SA cannot patch instances — D4/D10); shellcheck-clean

## Phase 3: Deployer identity (author-only Terraform)

- [X] T005 Extend `infra/terraform/iam.tf`: `google_service_account.deployer` (`techscreen-deployer`), WIF `google_service_account_iam_member` with the same repository-pinned principalSet as `flag_sync_wif`, `roles/run.developer` + `roles/cloudsql.viewer` project bindings, `roles/artifactregistry.writer` on `google_artifact_registry_repository.techscreen`, and four SA-level `roles/iam.serviceAccountUser` bindings on the runtime SAs via `module.env_{prod,dev}` outputs (D4 matrix); `terraform fmt` + `validate` green. **NEVER apply from this session**

## Phase 4: Docs

- [X] T006 Rewrite `docs/engineering/deploy-playbook.md` → v2.0: exact `gh workflow run` invocations for all three verbs, gate mechanics (§10 label, prod ancestry, asleep guard), cost-idle wake/sleep rule + which steps need the DB, migrations-are-operator-run section replacing the old Steps 3–4, honest not-yet-implemented list (deploys table, ChatOps, drain check, `/deploy cleanup`), version block bumped

## Phase 5: Verification

- [X] T007 Run `pre-commit run --files <every changed file>`; fix all actionlint/shellcheck/gitleaks/terraform_validate fallout; confirm zero credential-shaped strings and zero inline untrusted interpolations (SC-001)
- [ ] T008 [US1] Operator: quickstart §§1–2 — plan (deployer-only additions), apply, repeat-plan zero-diff, IAM policy verification (SC-005, SC-006)
- [ ] T009 [US1][US3][US2] Operator: quickstart §§3–4 — wake dev DB, frontend deploy → promote 10 → 100 → rollback with timing (SC-002, SC-003)
- [ ] T010 [US4][US5] Operator: quickstart §§5–6 + §7 row SC-008 — backend known-failure confirmation (D12), migration-gate fixture (SC-004), asleep-guard check; record the sweep table in the PR body (SC-007 via reviewer)

## Dependencies

```text
Phase 1 (T001–T003) → Phase 2 (T004) → Phase 3 (T005) → Phase 4 (T006) → Phase 5 (T007 → T008 → T009 → T010)
```

Strictly sequential — single infra-engineer; T008–T010 additionally require the operator's live credentials and must not run from the authoring session (no cloud mutations). No [P] markers by design (constitution §18; plan.md `parallel: false`).

## Implementation strategy

- MVP increment = US1 on the frontend path (T001 + T005 + T008 + T009): a service can ship dark and roll back, measurably. US4/US5 ride the same gate job; US2/US3 are the remaining verbs.
- The backend path is *expected* to fail its first live deploy until the env-wiring follow-up PR (research D12) — T010 records that failure as evidence the workflow surfaces it, not as a defect of this feature.
- Rollback story for this PR itself: workflows are inert until dispatched; the IAM change is additive and reverts with a plan/apply of the previous HCL.
