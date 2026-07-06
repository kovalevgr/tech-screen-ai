# Tasks: Configs-as-Code sync — rubric job (T16)

**Input**: Design documents from `specs/022-t16-rubric-sync/`
**Prerequisites**: plan.md, spec.md (4 user stories), research.md (R1–R9), data-model.md, contracts/plan-contract.md, quickstart.md

**Tests**: the destructive-change gate is fully unit-tested locally (no DB/git); everything cloud-side is operator-verified per quickstart.md, encoded below as explicit unchecked tasks.

**Organization**: `parallel: false` throughout (constitution §18 — one branch, coupled artefacts). `agent:` per task: `infra-engineer` for workflow/SQL/Terraform/docs, `backend-engineer` for Python + tests. Story labels map to spec.md: US1 = benign apply, US2 = ADR gate, US3 = job independence, US4 = cost-idle.

## Phase 1: Workflow (US1+US3) — agent: infra-engineer

- [X] T001 [US3] `git mv .github/workflows/sync-feature-flags.yml .github/workflows/sync-configs.yml` (research R1: push-trigger safe, no required-check/workflow_run edges; history via `--follow`)
- [X] T002 [US1] Rewrite the workflow header (all-surfaces §16 ownership, rename note, cost-idle recovery), rename the flags job id to `sync-feature-flags`, extend shared `paths:` with `configs/rubric/**` + `docs/contracts/rubric.schema.json` + the new self-path, add `pull-requests: read`
- [X] T003 [US1+US3] Add the `sync-rubric` job: matrix dev/prod `fail-fast: false`, same WIF/instance/user env block, checkout `fetch-depth: 0`, schema validation via `scripts/check-rubric-schema.py`, baseline extraction (`github.event.before` via env indirection; `HEAD~1`/empty fallbacks with warnings), ADR-context collection (`git log -1` + `gh api commits/{sha}/pulls` → file), destructive gate, guard, WIF auth, sha256-pinned proxy (same `CSP_SHA256`), seed step with `SYNC_ENV`; **no `needs:` anywhere**

## Phase 2: Gate + sync script (US2+US4) — agent: backend-engineer

- [X] T004 [US2] Create `scripts/sync_rubric_to_db.py` `check`: pure YAML-vs-YAML classifier per the data-model taxonomy (`NODE_REMOVED` forbidden exit 2; `NODE_RETIRED`/`NODE_UNRETIRED`/`LEVEL_REMOVED`/`LEVEL_RETYPED` destructive exit 1 without `\bADR-\d{3}\b` citation), GitHub annotations, file-level `retired:` handling, no third-party deps beyond pyyaml
- [X] T005 [US1+US4] Add the `sync` subcommand: 20 s pre-flight connect with the cost-idle wake hint (`SYNC_ENV`), then `RubricImporter.seed` (deferred namespace import off the repo root; research R2 — the T08 CLI is not reused), importer-error mapping, dry-run passthrough
- [X] T006 [US2] Create `app/backend/tests/contracts/test_rubric_sync_check.py` — subprocess pattern, 9 cases: benign edit, retired topic, retyped level, removed level, ADR-authorised, forbidden removal (citation ignored), un-retire, empty baseline, word-bounded regex

## Phase 3: Grants + Terraform (US1) — agent: infra-engineer

- [X] T007 [US1] Extend `scripts/cloud-db-grants.sql` per the data-model privilege matrix — per-table justification comments; SELECT+INSERT on `rubric_tree_version`/`stack`/`competency_block`/`competency`, INSERT-only on `topic`/`level`, INSERT-only on `audit_log` (research R6 §3 argument), nothing on the other five §3 tables, zero UPDATE/DELETE on rubric tables
- [X] T008 Update `infra/terraform/iam.tf` (SA comment + `description` — one in-place update on next apply) and `infra/terraform/outputs.tf` comments to the new workflow name

## Phase 4: Docs — agent: infra-engineer

- [X] T009 `docs/engineering/cloud-setup.md`: new "Configs-as-code sync — one workflow, all surfaces (§16)" subsection (job table, gate summary, wake-the-DB-first rule), flag-sync SA bullet updated (privilege list incl. INSERT-only audit_log), versioning bump to v2.1
- [X] T010 `docs/engineering/feature-flags.md` workflow pointer → `sync-configs.yml` + wake note; `docs/engineering/implementation-plan.md` T05a rename note + T16 implementation-notes blockquote; `scripts/sync_feature_flags_to_db.py` docstring pointer
- [X] T011 Spec Kit artefacts (this directory) committed with the feature PR

## Phase 5: Pre-merge verification (branch-local)

- [X] T012 `uv run pytest app/backend/tests/contracts/test_rubric_sync_check.py` green (9/9) and full contracts subset unaffected; `pre-commit run --files <every changed file>` green (actionlint, shellcheck-via-actionlint, gitleaks, rubric-schema, ruff, terraform_validate)

## Phase 6: Operator execution + acceptance (live GCP — quickstart.md)

- [ ] T013 [US1] Quickstart §§ 1–3: wake instances, apply `scripts/cloud-db-grants.sql` to both, verify `\dp` (rubric tables granted, `turn_trace` not), apply the one-line Terraform SA-description diff
- [ ] T014 [US1] Quickstart § 4: first live run — both `sync-rubric` legs green; `rubric_tree_version` + `audit_log` receipt verified per environment (SC-001)
- [ ] T015 [US2+US3] Quickstart §§ 5–6: destructive-without-ADR fails before WIF with the finding named while the flags job runs on (SC-002/SC-004); with citation applies; forbidden removal fails despite citation (SC-003)
- [ ] T016 [US4] Quickstart § 7: sleeping-dev failure ≤ ~60 s with the wake command in the annotation; wake + re-run-failed-jobs goes green (SC-007); then sleep all and record the sweep in the PR body
