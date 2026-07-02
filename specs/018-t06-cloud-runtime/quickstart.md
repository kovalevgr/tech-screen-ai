# Quickstart — T06 operator runbook + acceptance sweep

Audience: the operator (Ihor) applying T06 from this branch checkout, and the reviewer verifying acceptance. Every command runs from the repo root on the operator's machine (gcloud authenticated as `ikovalov@n-ix.com`, ADC pre-flight from `cloud-setup.md` § Operator pre-flight already done).

> ⚠️ Apply **only from this branch's checkout** — shared GCS state (see `cloud-setup.md` § How to apply a change).

## 1. Pre-flight (read-only)

```bash
terraform -chdir=infra/terraform init            # backend unchanged; re-init harmless
terraform -chdir=infra/terraform state list      # expect the 6 T01a resources
```

## 2. State surgery — adopt the T01a backend SA into the prod module

Run **after** checking out this branch's HCL, **before** the first plan:

```bash
terraform -chdir=infra/terraform state mv \
  google_service_account.techscreen_backend \
  'module.env_prod.google_service_account.backend[0]'
terraform -chdir=infra/terraform state mv \
  google_project_iam_member.techscreen_backend_aiplatform_user \
  'module.env_prod.google_project_iam_member.backend_aiplatform'
terraform -chdir=infra/terraform state mv \
  google_service_account_iam_member.techscreen_backend_tokens_for_owner \
  'module.env_prod.google_service_account_iam_member.backend_tokens_for_owner'
```

*(Exact target addresses are asserted by `tasks.md` against the final module code; adjust here if the module uses different resource labels — the tasks phase keeps this file in sync.)*

## 3. Plan + apply

```bash
export GOOGLE_BILLING_PROJECT=tech-screen-493720 USER_PROJECT_OVERRIDE=true
terraform -chdir=infra/terraform plan    # paste summary into the PR
terraform -chdir=infra/terraform apply
terraform -chdir=infra/terraform plan    # SC-001: zero pending changes
```

Expected new resources: ~45 (5 API services, registry, flag-sync SA + WIF binding, 2 × [SQL instance + 2 DBs + 3 users + 2 Cloud Run + 2 SAs + 5 secrets + IAM bindings]).

## 4. Set DB passwords (out-of-band; nothing in Git/state)

```bash
for inst in techscreen-pg techscreen-pg-dev; do
  gcloud sql users set-password techscreen_app       --instance=$inst --prompt-for-password
  gcloud sql users set-password techscreen_migrator  --instance=$inst --prompt-for-password
done
```

## 5. Fill secret values (per environment)

```bash
# prod                                     # dev
printf '%s' "$VALUE" | gcloud secrets versions add DATABASE_URL --data-file=-        # DATABASE_URL_DEV
# repeat: MAGIC_LINK_SIGNING_KEY(_DEV), SESSION_COOKIE_SECRET(_DEV), SENDGRID_API_KEY(_DEV)
# CALIBRATION_DATASET_KEY(_DEV) may stay version-less until calibration needs it
```

`DATABASE_URL` shape: `postgresql+asyncpg://techscreen_app:<pw>@127.0.0.1:5432/techscreen` (proxy-relative; T06a finalises the Cloud-Run-side wiring).

## 6. Apply migrations to both instances (Auth Proxy)

```bash
cloud-sql-proxy --port 5432 tech-screen-493720:europe-west1:techscreen-pg &     # then :techscreen-pg-dev
DATABASE_URL='postgresql+asyncpg://techscreen_migrator:<pw>@127.0.0.1:5432/techscreen' \
  alembic upgrade head
```

## 7. Grants for the flag-sync IAM user (per instance)

```bash
psql 'postgresql://techscreen_migrator:<pw>@127.0.0.1:5432/techscreen' \
  -f scripts/cloud-db-grants.sql
```

## 8. Acceptance sweep (record results in the PR)

| # | Check | Command | Pass condition |
| --- | --- | --- | --- |
| SC-001 | clean plan | `terraform plan` | "No changes" |
| SC-002 | 4 services live | `gcloud run services list --region europe-west1` + `curl -s -o /dev/null -w '%{http_code}' <url>` ×4 | all listed; 200 ×4 |
| SC-003 | 10 secret shells + scoped IAM | `gcloud secrets list`; `gcloud secrets get-iam-policy DATABASE_URL` | 10 names; per-secret accessor = matching env backend SA |
| SC-004 | pgvector + §3 + head | `psql … -c "SELECT extname FROM pg_extension WHERE extname='vector'"`; `UPDATE turn_trace SET agent='x'` as `techscreen_app`; `alembic current` | 1 row; trigger error; `0005` — on **both** instances |
| SC-005 | flag sync live | `gh workflow run sync-feature-flags.yml`; then `SELECT name, enabled, updated_by FROM feature_flag` ×2 | green, `skip=false`, rows `updated_by='configs-as-code'` in both DBs |
| SC-006 | no keys | `gcloud iam service-accounts keys list --iam-account=<each SA>`; gitleaks via pre-commit | only system-managed; clean |
| SC-007 | cost | Billing console after 48 h | run-rate consistent with ~$22–25/mo; budgets untouched |
| SC-008 | governance trail | `adr/023` merged + README row; ADR-009 superseded; constitution v1.1; `git grep -n "prod-only\|only prod" docs/ adr/README.md` | no stale active-doc claims |

## 9. Reviewer walkthrough (no cloud access needed)

1. `pre-commit run --all-files` green (terraform_validate, actionlint, gitleaks, shellcheck).
2. `terraform -chdir=infra/terraform validate` green; module inputs/outputs match [data-model.md](./data-model.md).
3. `sync-feature-flags.yml`: placeholders gone, matrix over dev/prod, `fail-fast: false`, `DATABASE_USER` = IAM username.
4. Governance: ADR-023 content vs research R10; §8 text + v1.1 changelog; ADR-009 status; README index.
5. No secret-shaped strings anywhere in the diff; no `google_sql_user.password` attributes; `ignore_changes` present on both Cloud Run services.
6. PR body contains the pasted `terraform plan` summary + this acceptance table filled in.
