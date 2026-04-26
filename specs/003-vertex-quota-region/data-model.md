# Phase 1 — Data Model: Vertex AI quota + region request (T01a)

**Branch**: `003-vertex-quota-region` · **Date**: 2026-04-24 · **Input**: [plan.md](./plan.md), [spec.md](./spec.md) §Key Entities

T01a has no application database schema. This document re-expresses both (a) the spec's Key Entities (sections 1–6: quota log artefacts, budget rule, channel, re-evaluation trigger) **and** (b) the IAM seed introduced by the `iam.tf` slice of T01a's Terraform (sections 7–8: runtime SA + its two T01a-time bindings — see `plan.md` §"Structure Decision" and `research.md` §R6 for why this slice is in T01a) as a compact entity map with fields, allowed values, and lifecycle notes, so the `reviewer` sub-agent and every downstream consumer (T04 Vertex wrapper, T06 Cloud Run + Cloud SQL bring-up, T42 calibration, T48a concurrency smoke) share one canonical reading.

Each entity below lists: its **physical form** (where the row actually lives), its **fields** (with type/format), its **lifecycle** (what create/change looks like), and the **validation rules** that apply at commit time.

---

## 1. Quota request

**Physical form.** One row in the "Quota requests" Markdown table in [`docs/engineering/vertex-quota.md`](../../docs/engineering/vertex-quota.md). The exact column set is pinned by [`contracts/vertex-quota-log-format.md`](./contracts/vertex-quota-log-format.md).

**Fields.**

| Field | Type / format | Allowed values / example |
|-------|---------------|--------------------------|
| `date` | ISO 8601 date (`YYYY-MM-DD`) | `2026-04-24` (the date the support case was submitted) |
| `model` | Vertex publisher model ID | `gemini-2.5-flash`, `gemini-2.5-pro` |
| `metric` | GCP quota metric name | `GenerateContentRequestsPerMinutePerProjectPerModel` |
| `default` | integer rpm | observed default at request time (e.g. `10`) |
| `requested` | integer rpm | target raise (`60`) |
| `granted` | integer rpm, nullable until case closes | `60`, or `40`, or empty while pending |
| `case_id` | opaque identifier | the numeric GCP support-case ID (e.g. `52419317`) |
| `requester` | team/role alias | `project-owner (Ihor)`, `infra-engineer (delegate)` — role or alias, never personal contact detail (FR-008) |
| `status` | enum | `pending` · `granted` · `partial` · `denied` · `rolled-back` |
| `notes` | free text, one line | "Partial grant: Pro stayed at default" or empty |

**Lifecycle.**

1. **Created** when Ihor (or nominated delegate) submits the GCP Console quota-request case. At this moment `status = pending`, `granted` is empty, `case_id` may be pending capture.
2. **Updated** only by **appending a new row** when the case's terminal state changes (`granted`, `partial`, `denied`) or when a re-raise / scale-up is later requested. The earlier row is never edited — the table is append-only by convention (spec §Key Entities).
3. A `rolled-back` status is used if a grant is later revoked by GCP or withdrawn by us.

**Validation rules.**

- `model` must be one of `{gemini-2.5-flash, gemini-2.5-pro}` for as long as ADR-003 holds; any other value triggers an ADR amendment.
- `metric` must be literally `GenerateContentRequestsPerMinutePerProjectPerModel` for T01a; a different metric name is a different quota class and needs a different row.
- T01a cannot merge while any row for a covered model has `status = pending` AND no later row for the same model exists with a terminal status — the case must close, one way or another.
- Per Clarifications 2026-04-24, the terminal `granted` value for Flash must satisfy `granted ≥ 30` and for Pro must satisfy `granted ≥ 5`. Below the floor, T01a is blocked.

---

## 2. Budget alert rule

**Physical form.** A `google_billing_budget` resource in [`infra/terraform/billing.tf`](../../infra/terraform/billing.tf) (committed by T01a). T01a creates **two** instances of this resource.

**Fields.**

| Field | Type / format | Allowed values / example |
|-------|---------------|--------------------------|
| `billing_account` | GCP billing account ID | N-iX billing account, referenced via `var.billing_account` |
| `display_name` | string | `"techscreen / project-wide $50"` or `"techscreen / vertex-only $20"` |
| `budget_filter.projects` | list | `["projects/${var.project_number}"]` for both |
| `budget_filter.services` | list, nullable | `null` for project-wide; `["services/aiplatform.googleapis.com"]` for Vertex-only |
| `amount.specified_amount.currency_code` | ISO 4217 | `"USD"` |
| `amount.specified_amount.units` | integer-as-string | `"50"` (project-wide) or `"20"` (Vertex-only) |
| `threshold_rules[]` | list of `{threshold_percent, spend_basis}` | `[{0.5, CURRENT_SPEND}, {0.9, CURRENT_SPEND}, {1.0, CURRENT_SPEND}]` for both |
| `all_updates_rule.monitoring_notification_channels` | list | `[google_monitoring_notification_channel.ops_email.id]` for both |

**Lifecycle.**

1. **Created** once per T01a apply. Not mutated during the MVP pilot window.
2. **Updated** only when the cap changes (e.g. a future ADR raises the Vertex-only budget to $30); edits are committed in Terraform as a diff and rolled via PR → `terraform apply`.
3. **Destroyed** only on project teardown; the §12 hard cap is not deletable during the MVP.

**Validation rules.**

- The project-wide `units` must equal `"50"` (constitution §12). Any other value needs an ADR.
- The Vertex-only `units` must equal `"20"` (Clarifications 2026-04-24). Any other value needs an ADR or a linked spec change.
- `threshold_rules` must include exactly the three tiers `0.5`, `0.9`, `1.0`.
- Both budgets must share the same notification channel (single recipient discipline, Clarifications 2026-04-24).

---

## 3. Notification channel

**Physical form.** A `google_monitoring_notification_channel` resource in [`infra/terraform/billing.tf`](../../infra/terraform/billing.tf).

**Fields.**

| Field | Type / format | Allowed values / example |
|-------|---------------|--------------------------|
| `display_name` | string | `"TechScreen budget alerts (MVP recipient)"` |
| `type` | string (GCP channel type) | `"email"` |
| `labels.email_address` | string | `var.ops_email`, resolved from `envs/prod/terraform.tfvars` |
| `enabled` | boolean | `true` |

**Lifecycle.**

1. **Created** once per T01a apply.
2. **Updated** via tfvars: rotating the recipient (e.g. swap Ihor's mailbox for `techscreen-alerts@n-ix.com` once provisioned) is a one-line `terraform.tfvars` edit followed by `terraform apply`. No resource replacement.
3. **Destroyed** only if the budget alerts themselves are destroyed.

**Validation rules.**

- `type` must be `"email"` at T01a. A Pub/Sub / Slack channel is explicitly deferred.
- The `labels.email_address` value must not be a secret-shaped string — email addresses are not secrets, but the T01 guardrails still scan it; keeping it as a Terraform variable sourced from `tfvars` is what makes the value auditable without being pasted across files.

---

## 4. Region verification record

**Physical form.** One dated bullet in the "Region verification" section of [`docs/engineering/vertex-quota.md`](../../docs/engineering/vertex-quota.md).

**Fields.**

| Field | Type / format | Example |
|-------|---------------|---------|
| `date` | ISO 8601 date | `2026-04-24` |
| `model` | publisher model ID | `gemini-2.5-flash`, `gemini-2.5-pro` |
| `region` | GCP region | `europe-west1` |
| `evidence` | free text, one line | "Model Garden, Google publisher filter, region=europe-west1 — both models visible" |
| `verified_by` | alias | `project-owner (Ihor)` |

**Lifecycle.**

1. **Created** at T01a submission time, one bullet per covered model (or one combined bullet for both models if verified together).
2. **Appended** (never edited) on any re-verification event — a future model-version GA, a region change proposal, or the annual ADR-015 re-review.
3. Old bullets remain readable as historical evidence.

**Validation rules.**

- If any bullet's `region` ≠ `europe-west1` for ADR-003's models, T01a must raise an ADR-015 amendment (FR-004) before merge.
- A bullet must name both Gemini 2.5 Flash and Gemini 2.5 Pro (explicitly or collectively) for T01a acceptance (FR-003).

---

## 5. Smoke-test record

**Physical form.** One dated bullet in the "Smoke-test records" section of [`docs/engineering/vertex-quota.md`](../../docs/engineering/vertex-quota.md).

**Fields.**

| Field | Type / format | Example |
|-------|---------------|---------|
| `date` | ISO 8601 date | `2026-04-24` |
| `runner` | enum | `local-adc-impersonation` (T01a merge) · `cloud-run-revision-<id>` (T11 re-run) |
| `model` | publisher model ID | `gemini-2.5-flash` |
| `region` | GCP region | `europe-west1` |
| `latency_ms` | integer ms (wall-clock) | `1180` |
| `status` | enum | `pass` · `fail` |
| `notes` | free text, one line, optional | error class if `fail` |

**Lifecycle.**

1. **Created** after the operator runs `infra/scripts/vertex-smoke.sh` against the prod project with impersonation of `techscreen-backend@<project>`.
2. **Appended** at T11 checkpoint time (FR-006a) with a second bullet, `runner = cloud-run-revision-<revision>`.
3. Failed bullets remain — they are the record of the failure and the fix.

**Validation rules.**

- `latency_ms` must be `< 10000` for T01a acceptance (FR-006, SC-004).
- `status = pass` for at least one bullet is required for T01a acceptance; a failed initial attempt is not disqualifying if a later `pass` bullet exists with the same `runner`.
- `runner = cloud-run-revision-*` is not required for T01a merge; it is required before T11 can sign off.

---

## 6. Re-evaluation trigger

**Physical form.** A short paragraph in the preamble of [`docs/engineering/vertex-quota.md`](../../docs/engineering/vertex-quota.md) (not a row, not a bullet — a named conditional).

**Fields.**

| Field | Type / format | Example |
|-------|---------------|---------|
| `condition` | plain-English clause | "If projected or realised concurrent sessions exceed 20 …" |
| `action` | concrete next-task name | "… raise a new Spec Kit feature named `T01a-v2` …" |
| `owner` | agent/role | "`infra-engineer` + project owner" |
| `originating_source` | reference | constitution §12 + implementation-plan T01a |

**Lifecycle.**

1. **Created** in the same commit as the quota log itself (T01a).
2. **Updated** only by a follow-up task that changes the concurrency threshold or the hard cap; such a change requires an ADR.
3. **Fires** exogenously — when a human or agent reading the log notices the condition is met — not automatically. The trigger is discipline, not code.

**Validation rules.**

- The trigger text must name a concrete threshold (`> 20 concurrent sessions`) and a concrete follow-up task name (`T01a-v2`), not a vague "re-evaluate if things scale up". Ambiguity here defeats the point.

---

## 7. Runtime service account (T01a seed)

**Physical form.** A `google_service_account "techscreen_backend"` resource in [`infra/terraform/iam.tf`](../../infra/terraform/iam.tf) (committed by T01a). T01a creates this SA so the FR-006 smoke test can impersonate it via local ADC; T06 later attaches additional role bindings to the same SA without recreating it (see [research.md](./research.md) §R6).

**Fields.**

| Field | Type / format | Allowed values / example |
|-------|---------------|--------------------------|
| `account_id` | string, lowercase, kebab-case | `"techscreen-backend"` (fixed — cited by name in `docs/engineering/cloud-setup.md` and by every downstream task that impersonates the runtime identity) |
| `display_name` | string | `"TechScreen backend runtime"` |
| `description` | string | `"Runtime identity for the Cloud Run backend (seeded by T01a; T06 extends)"` |
| `email` (derived) | `<account_id>@<project_id>.iam.gserviceaccount.com` | not authored — Terraform derives it from `account_id` + `project_id` |
| `disabled` | boolean | `false` (omitted; provider default) |

**Lifecycle.**

1. **Created** once per T01a apply (Phase 6, T020).
2. **Mutated** never during the MVP pilot. T06 *adds bindings to* the SA via separate `google_project_iam_member` and `google_secret_manager_secret_iam_member` resources — it does not edit the SA itself.
3. **Destroyed** only on project teardown. Per constitution §6, **no JSON service-account key is ever created** (`gcloud iam service-accounts keys create` is forbidden); the SA is consumed exclusively via Workload Identity Federation (Cloud Run runtime) and short-lived ADC impersonation (smoke test from operator laptop).

**Validation rules.**

- `account_id` must be exactly `"techscreen-backend"` for as long as `docs/engineering/cloud-setup.md` and downstream tasks reference that name. Any rename requires updating those files in the same PR.
- No `key.create_time` field — keys are not created (§6).
- `description` must include the substring "seeded by T01a" so a future reader of the Terraform state can locate the originating spec without guessing.

---

## 8. IAM binding (T01a seed)

**Physical form.** Two distinct binding resources in [`infra/terraform/iam.tf`](../../infra/terraform/iam.tf):

1. A `google_project_iam_member "techscreen_backend_aiplatform_user"` granting the runtime SA `roles/aiplatform.user` at the project level (so the SA can call Vertex AI).
2. A `google_service_account_iam_member "techscreen_backend_tokens_for_owner"` granting the human Owner principal `roles/iam.serviceAccountTokenCreator` on the runtime SA (so the operator can `gcloud auth print-access-token --impersonate-service-account=techscreen-backend@…` from their laptop for the smoke).

T06 later adds *more* `google_project_iam_member` and `google_secret_manager_secret_iam_member` resources for additional roles (Cloud SQL client, Secret Manager accessor, logging writer, monitoring writer) on the same SA — it does not modify the two T01a bindings.

**Fields.**

| Field | Type / format | Allowed values / example |
|-------|---------------|--------------------------|
| `project` (project-level binding only) | string | `var.project_id` |
| `service_account_id` (SA-level binding only) | resource reference | `google_service_account.techscreen_backend.name` |
| `role` | GCP IAM role | T01a allows exactly two: `"roles/aiplatform.user"` (project-level) and `"roles/iam.serviceAccountTokenCreator"` (SA-level). Any other role at T01a-time is out of scope. |
| `member` | IAM member string | Project-level: `"serviceAccount:${google_service_account.techscreen_backend.email}"`. SA-level: `"user:<Ihor's N-iX identity>"` (a real human principal — see `tasks.md` T018). |

**Lifecycle.**

1. **Created** once per T01a apply (Phase 6, T020), alongside the SA itself.
2. **Mutated** never during the MVP pilot — T06 only *adds* sibling binding-resources for additional roles; it does not modify the role or member of these two.
3. **Destroyed** only on project teardown.

**Validation rules.**

- Project-level binding's `role` must be `"roles/aiplatform.user"` and **must not** be `"roles/owner"`, `"roles/editor"`, or any other broad role (constitution §6 spirit + least-privilege baseline). T06 may add narrower roles via additional resources; it may not widen this one.
- SA-level binding's `member` must be `user:` or `group:` (a human or human-group principal) — never `serviceAccount:`. SA-to-SA token-creation is not a T01a use-case and would be a different decision.
- The `member` value for the SA-level binding must be the **same** principal that runs `terraform apply` and the smoke. A binding granting impersonation to a principal who never executes the smoke is dead code.

---

## Cross-entity relationships

```text
Quota request (row)  ──references──▶ Region verification bullet (same model, same region)
                     │
                     └──gated by──▶ Per-model workload floor (Flash ≥ 30 rpm, Pro ≥ 5 rpm)

Budget alert rule  ──uses──▶ Notification channel (single shared instance)
                    │
                    └──enforces──▶ constitution §12 cap

Runtime service account  ──bound to──▶ IAM binding (project-level: roles/aiplatform.user)
                         │
                         └──impersonated via──▶ IAM binding (SA-level: roles/iam.serviceAccountTokenCreator)
                                                                         │
                                                                         └──by──▶ human Owner principal (also runs terraform apply)

Smoke-test record  ──proves──▶ Quota request is reachable from the intended runtime identity
                   │           via the Runtime SA + both IAM bindings (FR-006 chain)

Re-evaluation trigger  ──names──▶ follow-up task (`T01a-v2`) that would raise a new Quota request row
```

No foreign keys, no IDs — the references above are textual and human-navigable. That is sufficient for an 8-entity, single-file domain.
