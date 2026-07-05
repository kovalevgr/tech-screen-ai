# Quickstart — T06a operator runbook + acceptance sweep

Audience: the operator (Ihor) applying the deployer IAM and rehearsing the three commands on `dev`, and the reviewer verifying acceptance. Every command runs from the repo root on the operator's machine (gcloud authenticated, ADC pre-flight from `cloud-setup.md` § Operator pre-flight done). **Nothing in this feature was executed against live GCP during authoring** — this runbook is the execution.

> ⚠️ Apply **only from this branch's checkout** — shared GCS state (`cloud-setup.md` § How to apply a change).

## 1. Pre-flight (read-only)

```bash
pre-commit run --files .github/workflows/deploy.yml .github/workflows/promote.yml \
  .github/workflows/rollback.yml scripts/cloud-sql-power.sh infra/terraform/iam.tf
terraform -chdir=infra/terraform init      # backend unchanged; re-init harmless
terraform -chdir=infra/terraform plan      # expect ONLY: +deployer SA, +5 bindings (SC-006)
```

## 2. Apply the deployer identity

```bash
export GOOGLE_BILLING_PROJECT=tech-screen-493720 USER_PROJECT_OVERRIDE=true
terraform -chdir=infra/terraform apply
terraform -chdir=infra/terraform plan      # zero diff
```

Verify least privilege (SC-005):

```bash
gcloud projects get-iam-policy tech-screen-493720 \
  --flatten='bindings[].members' \
  --filter='bindings.members:techscreen-deployer@' \
  --format='value(bindings.role)'
# expect exactly: roles/run.developer, roles/cloudsql.viewer
gcloud iam service-accounts get-iam-policy \
  techscreen-backend@tech-screen-493720.iam.gserviceaccount.com
# expect deployer as roles/iam.serviceAccountUser (repeat for the other 3 runtime SAs)
```

## 3. Wake the dev database (cost-idle mode)

The deploy gate reads instance state; today's unwired backend template means an asleep DB only produces a notice — but wake it anyway so the rehearsal covers the real world:

```bash
scripts/cloud-sql-power.sh status dev
scripts/cloud-sql-power.sh wake dev      # gcloud sql instances patch … --activation-policy=ALWAYS
```

Remember to `scripts/cloud-sql-power.sh sleep dev` when the session ends.

## 4. Rehearse on dev — frontend first (it can actually pass smoke)

```bash
gh workflow run deploy.yml -f env=dev -f service=frontend -f git_ref=main
gh run watch                                   # or the Actions UI
```

Expected: gate green (ancestry skipped for dev, migration gate empty diff or fallback notice, DB notice), image `frontend:<sha>-dev` pushed, new revision at 0 % with `candidate` tag, smoke 200, summary filled (SC-002).

Then ramp and roll back, with a stopwatch on the rollback (SC-003):

```bash
gh workflow run promote.yml  -f env=dev -f service=frontend -f percent=10
gh workflow run promote.yml  -f env=dev -f service=frontend -f percent=100
gh workflow run rollback.yml -f env=dev -f service=frontend
# summary reports the measured update-traffic duration; record it below
```

## 5. Backend expectation — known failure until env wiring lands (research D12)

`gh workflow run deploy.yml -f env=dev -f service=backend -f git_ref=main` will build and push fine, then **fail at the `gcloud run deploy` step**: the `runtime` image bakes `APP_ENV=prod`, `LLM_BACKEND` defaults to `mock`, and `Settings.assert_safe_for_environment()` raises → readiness probe fails. This is the T06 template's missing env block, not a workflow bug. The follow-up (separate PR, `infra/terraform/modules/environment/main.tf`): add `env { name = "LLM_BACKEND" value = "vertex" }` (+ `DATABASE_URL` secret ref + Cloud SQL attachment when backend DB routes arrive). Record the observed failure here as confirmation the workflow surfaces it loudly, then re-run backend once the wiring PR is applied.

After the first successful backend deploy, also verify the template-ownership assumption (research D12):

```bash
terraform -chdir=infra/terraform plan   # expect zero diff (ports is computed; image ignored)
```

## 6. Migration-gate fixture (SC-004)

```bash
git checkout -b fixture/migration-gate && touch alembic/versions/9999_fixture_noop.py
git commit -am "test: migration gate fixture" && git push -u origin fixture/migration-gate
gh pr create --fill                      # do NOT label it
gh workflow run deploy.yml -f env=dev -f service=frontend -f git_ref=fixture/migration-gate
# expect: gate job FAILS naming the file, commit, and unlabelled PR
gh pr edit --add-label migration-approved
gh workflow run deploy.yml -f env=dev -f service=frontend -f git_ref=fixture/migration-gate
# expect: gate passes. Then close the PR unmerged and delete the branch.
```

## 7. Acceptance sweep (record results in the PR)

| # | Check | Command / source | Pass condition |
| --- | --- | --- | --- |
| SC-001 | lint chain | `pre-commit run --files <changed>` | actionlint, shellcheck, gitleaks, terraform_validate green |
| SC-002 | dev deploy | §4 dispatch + `gcloud run services describe techscreen-frontend-dev --region europe-west1` | 0 % revision + `candidate` tag + summary with revision/smoke |
| SC-003 | rollback timing | §4 rollback summary | `update-traffic` ≤ 60 s; workflow ≤ 2 min |
| SC-004 | §10 gate | §6 fixture | fails unlabelled with names; passes labelled |
| SC-005 | least privilege | §2 policy queries; `gh secret list` empty of new entries; gitleaks | exact role set; no new secrets/keys |
| SC-006 | terraform scope | §1/§2 plans | only deployer additions; zero-diff after |
| SC-007 | playbook accuracy | reviewer executes §4 from `deploy-playbook.md` alone | no step missing/wrong |
| SC-008 | asleep guard | `scripts/cloud-sql-power.sh sleep dev` then a dev deploy dispatch | notice today (unwired) / hard fail with wake message once wired |

## 8. Reviewer walkthrough (no cloud access needed)

1. `pre-commit run --files <changed>` green.
2. Workflows: no `${{ inputs.* }}`/`${{ github.event.* }}` inline in any `run:` block (env-mapped only); `permissions` minimal; concurrency groups as designed; no repository secrets referenced.
3. `iam.tf`: deployer roles match the data-model matrix exactly — especially `serviceAccountUser` on the four runtime SAs and **not** project-level; WIF member string mirrors `flag_sync_wif`.
4. `scripts/cloud-sql-power.sh`: wake/sleep/status only, no credentials, shellcheck-clean.
5. Playbook v2.0 vs workflows: names, inputs, and the not-yet-implemented list all truthful.
6. specs/020 internal consistency: FR ↔ SC ↔ research decisions (D2 migrations, D4 roles, D12 known gap declared, not hidden).
