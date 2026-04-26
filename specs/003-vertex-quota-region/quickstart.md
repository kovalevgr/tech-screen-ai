# Quickstart: Reviewer-facing validation for T01a

**Branch**: `003-vertex-quota-region` · **Date**: 2026-04-24 · **Input**: [plan.md](./plan.md), [spec.md](./spec.md), [contracts/vertex-quota-log-format.md](./contracts/vertex-quota-log-format.md)

This is the walkthrough a reviewer (human or the `reviewer` sub-agent) follows to validate the T01a PR end-to-end. It mirrors the spec's Acceptance Scenarios 1:1 and completes in under 10 minutes on a reviewer's laptop. It is deliberately sequential — each step yields a go/no-go signal for the next.

Two-line TL;DR: the PR passes iff (a) the quota log is correctly shaped, (b) the Terraform plans across both phases (Phase 5 + Phase 6) add exactly six resources (one channel + two budgets + one SA + two IAM bindings) and change/destroy zero, and (c) the smoke-test record shows `status=pass` with `latency_ms < 10000`.

---

## Prerequisites (one-time on the reviewer's machine)

- `gcloud` installed and logged in as a principal with `roles/viewer` on the `techscreen` GCP project (Owner for step 3 `terraform plan`, if reviewer re-runs it).
- `terraform` `>= 1.5`.
- `gh` (for fetching the PR).
- Repo checked out; branch `003-vertex-quota-region` checked out.

---

## Step 1 — Quota log shape (30 s)

Open [`docs/engineering/vertex-quota.md`](../../docs/engineering/vertex-quota.md). Verify:

- [ ] Top-level headings are **exactly** `# TechScreen — Vertex AI Quota Log`, `## Re-evaluation trigger`, `## Quota requests`, `## Region verification`, `## Smoke-test records`, `## Follow-ups`, in that order.
- [ ] "Quota requests" table columns match the contract schema: `date | model | metric | default | requested | granted | case_id | requester | status | notes`.
- [ ] Every row for Gemini 2.5 Flash and Gemini 2.5 Pro is present and its `status` is one of `granted` / `partial` (not `pending` — T01a cannot merge with a pending case per data-model §1).
- [ ] Granted values satisfy the per-model workload floors: Flash `granted >= 30`, Pro `granted >= 5` (Clarifications 2026-04-24 Q2, FR-002a).
- [ ] `requester` contains no personal contact detail (phone, home address). Role/alias only (FR-008).
- [ ] The "Re-evaluation trigger" paragraph names a concrete threshold (`> 20 concurrent sessions`), a concrete action (`raise T01a-v2`), and a concrete owner.

**Go/no-go**: any unchecked box blocks merge. Comment on the PR with the failing checklist item and the exact line.

## Step 2 — Region verification line (15 s)

Still in the quota log, "Region verification" section:

- [ ] At least one dated bullet lists **both** `gemini-2.5-flash` and `gemini-2.5-pro` (explicitly, or as a combined clause).
- [ ] Region on that bullet is **exactly** `europe-west1` (FR-003, ADR-015).
- [ ] Evidence source is named (e.g. "Vertex Model Garden Console, Google publisher filter") — screenshot is *not* required, and should not be committed (research R7).

**Go/no-go**: if either model is not verified in `europe-west1`, the PR must include a linked ADR-015 or ADR-003 amendment (FR-004). Otherwise block.

## Step 3 — Terraform plans (2 × 2 min)

T01a's `terraform apply` is split across **two phases** in [`tasks.md`](../../specs/003-vertex-quota-region/tasks.md) — Phase 5 (budgets + channel) and Phase 6 (runtime SA + IAM bindings). Each phase produces its own `tfplan-*` file and its own plan-summary in the PR description per [`docs/engineering/cloud-setup.md`](../../docs/engineering/cloud-setup.md) §"How to apply a change". A reviewer re-running the quickstart on a fresh backend MUST execute and verify both plans, in order — Phase 5 first (T015–T017), then Phase 6 (T018–T020). Six new resources land across both applies; nothing changes or is destroyed.

### Step 3a — Phase 5 plan (budgets + notification channel)

From the repo root:

```bash
cd infra/terraform
terraform init                       # first-time only; backend bucket is hardcoded in backend.tf (PR #2 baseline)
terraform plan -out=tfplan-phase5    # terraform.tfvars is auto-loaded from the working dir
```

Verify the Phase 5 plan summary against `tasks.md` T016 expectations:

- [ ] **Exactly three resources to add**: `google_monitoring_notification_channel.ops_email`, `google_billing_budget.project_wide`, `google_billing_budget.vertex_only`.
- [ ] **Zero resources to change or destroy** (first apply on a fresh backend; if the Phase 5 apply already happened, this section MAY show "Plan: 0 to add, 0 to change, 0 to destroy" — that means Phase 5 is already in state, which is fine).
- [ ] The project-wide budget's `amount.specified_amount.units = "50"`, `currency_code = "USD"` (constitution §12).
- [ ] The Vertex-only budget's `amount.specified_amount.units = "20"`, `currency_code = "USD"`, and `budget_filter.services = ["services/aiplatform.googleapis.com"]` (Clarifications 2026-04-24 Q5).
- [ ] Both budgets have exactly three `threshold_rules` at `0.5`, `0.9`, `1.0`.
- [ ] Both budgets reference the same `monitoring_notification_channels` (single shared channel).
- [ ] The notification channel `type = "email"` and the email address is the MVP recipient named in the clarifications — sanity-check against `terraform.tfvars`.

### Step 3b — Phase 6 plan (runtime SA + IAM bindings)

After (or alongside) Step 3a, generate the Phase 6 plan:

```bash
terraform plan -out=tfplan-phase6
```

If Step 3a's apply has already been executed, this plan shows only the IAM delta. If Step 3a has *not* yet been applied, this plan shows all six resources together — both interpretations are valid; what matters is the union below.

Verify the Phase 6 plan summary against `tasks.md` T020 expectations:

- [ ] **Exactly three additional resources to add** beyond Phase 5: `google_service_account.techscreen_backend`, `google_project_iam_member.techscreen_backend_aiplatform_user`, `google_service_account_iam_member.techscreen_backend_tokens_for_owner`.
- [ ] The service account's `account_id = "techscreen-backend"` and `display_name` mentions "TechScreen backend runtime" (per `tasks.md` T018).
- [ ] The project-level binding has `role = "roles/aiplatform.user"` and `member` references the new SA.
- [ ] The SA-level binding has `role = "roles/iam.serviceAccountTokenCreator"` and `member = "user:<…>"` — the principal that runs the smoke (per Clarifications 2026-04-24 + `tasks.md` T018). This is what makes `gcloud auth print-access-token --impersonate-service-account=…` work.
- [ ] Phase 5 budget resources from Step 3a remain unchanged (zero in the "change" / "destroy" buckets for those names).

### Combined go/no-go

- Across both plans, **6 resources to add** total (3 from Phase 5 + 3 from Phase 6), **0 to change**, **0 to destroy** on a fully fresh backend.
- Any unexpected resource in either plan blocks merge.
- Both plan summaries must be pasted into the PR description (one per phase) per [`docs/engineering/cloud-setup.md`](../../docs/engineering/cloud-setup.md) §"How to apply a change".

## Step 4 — Smoke-test record (30 s read, up to 2 min to re-run)

In the quota log, "Smoke-test records" section:

- [ ] At least one bullet has `runner=local-adc-impersonation`, `model=gemini-2.5-flash`, `region=europe-west1`, `latency_ms=<N>`, `status=pass`, and `N < 10000` (FR-006, SC-004).
- [ ] The date on that bullet is not older than the "Quota requests" table's most recent `granted` status row for Flash (i.e. the smoke was taken *after* the grant landed).
- [ ] The format exactly matches the contract schema (key=value pairs, no commas inside values).

To re-run the smoke from the reviewer's own machine (optional but recommended):

```bash
PROJECT_ID=<prod-project-id> \
RUNTIME_SA=techscreen-backend@<prod-project-id>.iam.gserviceaccount.com \
bash infra/scripts/vertex-smoke.sh
```

Expected stdout (one line, at a pass — comma-separated per contract §5):

```text
runner=local-adc-impersonation, model=gemini-2.5-flash, region=europe-west1, latency_ms=<N>, status=pass
```

The operator appends `- YYYY-MM-DD — <stdout line>` verbatim to the "Smoke-test records" section of the quota log (no re-formatting; the script already emits the contract-correct format).

**Go/no-go**: no pass bullet, or `latency_ms >= 10000`, blocks merge. A failed bullet is acceptable only if a later pass bullet exists for the same `runner`.

## Step 5 — Docs cross-references (1 min)

- [ ] [`docs/engineering/cloud-setup.md`](../../docs/engineering/cloud-setup.md) line 52 (the "Alerts fire to the ops inbox" sentence) has been updated to name **Ihor's N-iX mailbox** explicitly as the MVP recipient, with a visible follow-up to swap for a shared group alias once provisioned.
- [ ] [`docs/engineering/directory-map.md`](../../docs/engineering/directory-map.md) has a new row pointing at `docs/engineering/vertex-quota.md` (or a note under the `docs/engineering/` row explaining its ownership).
- [ ] [`docs/engineering/directory-map.md`](../../docs/engineering/directory-map.md) `infra/terraform/` row is annotated to note that `billing.tf` was seeded by T01a (T06 later extends).

**Go/no-go**: missing cross-reference is not a blocker per se, but the `reviewer` sub-agent flags it as FR-009 non-compliance (discoverability).

## Step 6 — Secret hygiene scan (SC-006)

Let the T01 guardrails do their job:

```bash
pre-commit run --all-files
```

- [ ] `gitleaks` and `detect-secrets` pass with zero findings on the PR's changed files (FR-008, SC-006).
- [ ] No file committed by this PR contains a plaintext credential, API key, service-account JSON, OAuth token, or personal identifier beyond the role/alias attribution.

**Go/no-go**: any guardrail finding blocks merge automatically via CI; the reviewer just confirms CI is green.

## Step 7 — Sign-off

Post a short approval comment on the PR with the six checklists above marked green, plus any follow-ups that were flagged for future tasks. Merge is then a standard squash via the CODEOWNERS review.

After merge, the orchestrator (or Ihor) pencils the T11 Tier-1 checkpoint note that, once T06 has deployed a Cloud Run revision, the smoke script must be re-executed from that revision and a `runner=cloud-run-revision-<id>` bullet appended (FR-006a).

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `terraform plan` fails on `billing_account` unknown | `terraform.tfvars` missing or wrong billing ID | Obtain billing ID from GCP Console (Billing → Settings); update `tfvars`; re-run plan. |
| Smoke script exits non-zero with HTTP 403 | `techscreen-backend@` SA missing `roles/aiplatform.user`, or the reviewer lacks permission to impersonate it | Check `cloud-setup.md` §IAM — runtime SA has the role; reviewer uses an Owner or `roles/iam.serviceAccountTokenCreator` identity. |
| Smoke script exits non-zero with HTTP 429 | Quota grant didn't land yet | Re-check the "Quota requests" table — all rows should be `granted` or `partial`, none `pending`. |
| `latency_ms` between 8 000 and 9 999 | Cold Vertex endpoint or slow local network — borderline | Re-run the smoke 3× and take the median. If median still ≥ 10 000, block merge and investigate. |
| `terraform plan` wants to change an existing resource | Someone ran `terraform apply` out-of-band | Stop — investigate the drift before applying; T01a is supposed to be a clean initial apply. |
