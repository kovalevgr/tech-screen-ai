# Phase 0 — Research: Vertex AI quota + region request (T01a)

**Branch**: `003-vertex-quota-region` · **Date**: 2026-04-24 (post-rebase amendment 2026-04-26) · **Input**: [plan.md](./plan.md)

This document resolves the implementation-detail questions raised in `plan.md` §Phase 0. Each section records the **Decision**, **Rationale**, and **Alternatives considered**. Sources are cited inline so a reviewer can follow up without rediscovering them.

> **POST-REBASE NOTE (2026-04-26).** Between T01a's `/speckit-plan` and `/speckit-implement`, **PR #2 (`002-terraform-backend-bootstrap`, commit `a4ed063`)** landed on main. PR #2 seeded `infra/terraform/` with a different convention than R6 originally proposed: `provider.tf` (singular, provider-only), `versions.tf` (separate, terraform{} block, **provider pinned to `~> 6.0`** not `~> 5.30`), `backend.tf` (hardcoded bucket `tech-screen-493720-tf-state`, no `-backend-config=` indirection), `terraform.tfvars` in repo root (no `envs/prod/` split), `.gitignore`. T01a was rebased onto that baseline; the active layout is the rebased one. Decisions R3 and R6 below are **amended in place** to reflect the rebased reality; the original wording is preserved by intent (decisions stand) but file/path/version specifics are corrected. The rationale and alternatives sections still describe the original reasoning.

---

## R1 — Vertex quota mechanics: metric name + default value

**Decision.** The per-model rate-limit metric on Vertex Generative AI endpoints in `europe-west1` is referenced by the `aiplatform.googleapis.com` service as `GenerateContentRequestsPerMinutePerProjectPerModel`. Defaults for a freshly bootstrapped project are **below** our 60 rpm target on both Gemini 2.5 Flash and Pro (Flash typically starts around 60 rpm in many regions but can be as low as 10 rpm in `europe-west1` depending on activation date; Pro typically starts at 5–10 rpm for new customers). The exact defaults as observed on `techscreen` at request time are **recorded in the `default` column** of the quota log when the request is submitted — the log reflects reality, not assumptions.

**Rationale.** GCP does not publish a single stable "default quota" table that survives model-version churn. The right source of truth is the live `gcloud` readout on the target project at the moment of the request:

```bash
gcloud alpha services quota list \
  --service=aiplatform.googleapis.com \
  --consumer=projects/${PROJECT_ID} \
  --filter="metric=GenerateContentRequestsPerMinutePerProjectPerModel" \
  --format="table(metric, unit, quota_buckets.effective_limit, quota_buckets.dimensions)"
```

This is the same command committed in the quickstart so the log's `default` values are reproducible.

**Alternatives considered.**

- **Hard-coded defaults in the spec.** Rejected — values drift between regions and over time. Locking them in a spec would make the spec wrong on first reread.
- **A single combined metric across all models.** Rejected — GCP scopes the limit per model by design (`GenerateContentRequestsPerMinutePerProjectPerModel`), which is exactly what we want: an over-exercised Flash does not eat Pro's headroom.

---

## R2 — Quota-request channel

**Decision.** **GCP Console → IAM & Admin → Quotas** is the canonical channel. The operator selects the `aiplatform.googleapis.com` metric `GenerateContentRequestsPerMinutePerProjectPerModel`, filters by model (Gemini 2.5 Flash, Gemini 2.5 Pro) and region (`europe-west1`), clicks *Edit quotas*, enters the requested value (60 rpm), and submits. The resulting support-case ID is captured and logged. A `gcloud alpha services quota update-quota-override` variant is permitted only as a rehearsal step in a non-Owner account — Ihor (Owner) files the production request via Console for the audit trail.

**Rationale.** Console produces a first-class GCP support case with a stable numeric ID, status transitions, and an email thread — i.e. the audit surface the quota log points at. `gcloud` quota-override commands bypass the support workflow for a subset of metrics but also bypass the auditable case. Since §12 hinges on this decision being legible to a reviewer months later, optimise for the audit artefact, not the keystrokes.

**Alternatives considered.**

- **`gcloud alpha services quota update-quota-override` only.** Rejected — no human-readable case ID, no reviewer-visible status field, harder to cite in the quota log.
- **Terraform `google_service_usage_consumer_quota_override`.** Rejected — the resource exists but (a) it applies only after the underlying quota allows the override, (b) GCP may still require a support case for rate-limit metrics on aiplatform, and (c) the declarative model would undo a human-approved raise if someone later trims the Terraform — the wrong semantics for a request that is a *conversation with GCP*, not a project resource.

---

## R3 — `google_billing_budget` Terraform shape

**Decision.** Each budget is a `google_billing_budget` resource attached to the N-iX billing account (scoped to the `techscreen` project via `budget_filter.projects = ["projects/<project_number>"]`), with:

- `display_name` — `"techscreen / project-wide $50"` and `"techscreen / vertex-only $20"`.
- `budget_filter.services` — omitted for the project-wide budget (covers all services); set to `["services/aiplatform.googleapis.com"]` for the Vertex-only budget.
- `amount.specified_amount.currency_code = "USD"`, `units = "50"` / `"20"`.
- `threshold_rules` — three per budget at `0.5`, `0.9`, `1.0` of `CURRENT_SPEND` (the spend-based threshold, not forecasted).
- `all_updates_rule.monitoring_notification_channels` — one channel reference, described in R4.

Provider constraint: `hashicorp/google` **`~> 6.0`** (set by PR #2's `versions.tf`). Terraform `>= 1.5`. `google_billing_budget` is GA in 5.x and 6.x; T01a HCL was validated under provider 6.50.0 (the version pinned in `.terraform.lock.hcl` after rebase).

**Rationale.** Two `google_billing_budget` resources is the minimum footprint that expresses the two-budget decision from Clarifications Q5. Using `budget_filter.services` rather than a label-based filter matches GCP's documented rate-limit-by-service pattern for Vertex spend. Current-spend thresholds (not forecast) avoid early false positives while still firing well before the hard cap.

**Alternatives considered.**

- **One budget with two notification tiers**, using credits to simulate a Vertex-only carve-out. Rejected — GCP billing budgets don't support conditional thresholds by service within a single resource; the expressible shape is two resources.
- **`google_billing_budget.forecasted_spend` thresholds.** Rejected for T01a — forecasted thresholds are valuable but noisier on low-volume projects (our expected $4–$10/mo Vertex spend is below the forecaster's confidence floor). Can be added later without an ADR.
- **Project-level label filter.** Rejected — the project is the scope already; labels add ceremony without changing behaviour.

---

## R4 — `google_monitoring_notification_channel` for email

**Decision.** A single `google_monitoring_notification_channel` resource of `type = "email"` with `labels.email_address` pointing at Ihor's N-iX mailbox (value supplied via `var.ops_email` from `infra/terraform/terraform.tfvars` — root tfvars after rebase, see POST-REBASE NOTE). Both budgets reference this single channel via `all_updates_rule.monitoring_notification_channels`. GCP email channels are created declaratively with no verification handshake for Google-hosted addresses (Workspace-delegated N-iX mailboxes qualify) — the channel is immediately usable after apply.

**Rationale.** Terraform-managed email channels are supported as first-class resources by the `google` provider and require no manual step. One channel, two budgets is the minimum deduplication. Using a Terraform variable for the email value means rotating the recipient (e.g. later swap to `techscreen-alerts@n-ix.com`) is a one-line tfvars change, which is exactly the follow-up the clarifications call for.

**Alternatives considered.**

- **Pub/Sub channel → Cloud Function → Slack.** Rejected — adds infra (a function, a topic, an IAM binding) that T01a is explicitly supposed to stay out of. Revisit when on-call moves to Slack.
- **Console-created channel referenced by Terraform.** Rejected — split ownership (Console vs Terraform) for one of the simplest GCP resources is the exact footgun constitution §16 guards against.

---

## R5 — Smoke-test path

**Decision.** A ~30-line Bash script at `infra/scripts/vertex-smoke.sh` that:

1. Resolves the runtime SA email from `TF var ops_email`-adjacent conventions (hard-coded default `techscreen-backend@<project>`).
2. Obtains an access token via `gcloud auth print-access-token --impersonate-service-account=${SA}`.
3. Issues a minimal `POST https://europe-west1-aiplatform.googleapis.com/v1/projects/${PROJECT}/locations/europe-west1/publishers/google/models/gemini-2.5-flash:generateContent` with a trivial payload (`{"contents":[{"role":"user","parts":[{"text":"ok"}]}],"generationConfig":{"maxOutputTokens":8,"temperature":0}}`) using `curl --max-time 15`.
4. Captures wall-clock latency via `date +%s%3N` bracket measurement and prints, on stdout, **exactly one line conforming to contract §5** — comma-separated key=value pairs in the order `runner=local-adc-impersonation, model=gemini-2.5-flash, region=europe-west1, latency_ms=<N>, status=<pass|fail>` (with an optional trailing `, notes=<short-token>` on failure). The format is the contract verbatim so the operator can copy-paste the line into the log without re-formatting.
5. Exits non-zero on HTTP error, timeout, or latency ≥ 10 000 ms; the operator then appends the stdout line into the quota log's Smoke-test records section.

The operator executes it once from their laptop after `terraform apply` lands and the quota grant is confirmed. At T11 checkpoint time the same script runs from a deployed Cloud Run revision (same script, different runtime identity — Cloud Run's own SA is `techscreen-backend@`).

**Rationale.** Bash + `curl` + `gcloud auth print-access-token` is the shortest path to a smoke-test record that exercises IAM + region + quota without pulling any SDK dependency into the repo (which would violate FR-010 "no runtime feature code"). Impersonation via `gcloud` is the documented way to assume a runtime identity from a developer laptop without a JSON key (satisfies §6).

The 8-token output cap keeps the call below $0.0001, so the script is safe to re-run during reviews.

**Alternatives considered.**

- **Python + `google-cloud-aiplatform` SDK.** Rejected — adds a Python dependency to the repo before T04 (the Vertex wrapper task) ships. Would either couple T01a to the `uv` lock changes or require a parallel venv, neither of which is the right factoring.
- **`gcloud ai models generate-content` one-liner.** Rejected — the subcommand exists but its availability across gcloud versions is inconsistent, and its output format makes latency measurement awkward. A raw `curl` with explicit timing is the more reliable artefact.

---

## R6 — Terraform root layout (T01a-seeded, T06-extended)

**Decision (post-rebase).** The flat root module at `infra/terraform/` was seeded by **PR #2** with: `provider.tf` (provider config only — no `terraform{}` block), `versions.tf` (terraform-version + provider-version pin, `~> 6.0`), `backend.tf` (hardcoded GCS bucket `tech-screen-493720-tf-state`, prefix `terraform/state` — no `-backend-config=` indirection), `variables.tf` (with `project_id`, `region`), `terraform.tfvars` (root, with real values for the same), `.gitignore`, `.terraform.lock.hcl`. **T01a layered on top**: extra variables in `variables.tf` (`project_number`, `billing_account`, `ops_email`), placeholder values in root `terraform.tfvars`, plus two new resource files: `billing.tf` (notification channel + 2 budgets) and a minimal `iam.tf` (runtime SA + 2 IAM bindings). T06 will later add `sql.tf`, `cloud_run.tf`, `artifact_registry.tf`, `secrets.tf`, `monitoring.tf`, `network.tf` as new files, **and extend `iam.tf` additively** (more role bindings on the same `techscreen-backend@` SA — Cloud SQL client, Secret Manager accessor, logging writer, monitoring writer), reusing `provider.tf` / `versions.tf` / `variables.tf` / `backend.tf` unchanged.

The reason `iam.tf` is in T01a's slice (and not deferred to T06) is the FR-006 smoke test: it impersonates `techscreen-backend@<project>` via `gcloud auth print-access-token --impersonate-service-account=…`, which requires (a) the SA to exist, (b) `roles/aiplatform.user` to be bound to it, and (c) `roles/iam.serviceAccountTokenCreator` on that SA for the human Owner identity that runs the smoke. The spec's Assumption explicitly permits T01a to own this slice ("the runtime SA has `roles/aiplatform.user` either by T01a time or by T06 time"); Clarifications Q4 closed the choice to "T01a time" (T01a does not block on T06). T01a's `iam.tf` is strictly these three resources — anything else is T06's.

**Rationale.** PR #2 chose a simpler convention than the original R6 proposal: no `envs/prod/` split, hardcoded backend bucket, separate `provider.tf` + `versions.tf`. Since constitution §8 forbids long-lived non-prod environments anyway, the `envs/prod/` indirection had no concrete near-term consumer. Adopting PR #2's flatter shape removed two files (`envs/prod/backend.hcl`, `envs/prod/terraform.tfvars`) and one indirection (`-backend-config=`) without changing what T01a delivers. T06 still slots in by adding files (Cloud SQL, Cloud Run, Secret Manager, monitoring, network) and *extending* `iam.tf` additively, never by renaming or splitting an existing file.

**Alternatives considered.**

- **Single `main.tf` consolidating provider + backend + resources.** Rejected — T06's delta would force a rewrite of `main.tf` to split concerns, creating a noisy diff. One-file-per-concern is cheap up front and pays off at T06.
- **Terraform modules under `modules/billing/`.** Rejected as premature — we have one caller (prod), two resources, and no reuse pressure. Modules are the right answer when the same shape repeats across environments, which our `envs:` policy (§8 prod-only) forbids.

---

## R7 — Model availability verification

**Decision.** The authoritative source is the Vertex Model Garden Console page for `europe-west1`, filtered to "Google" publishers, viewed on the grant date. The verification line in the quota log records: the verification date, the filter used (region + publisher), and a short human-readable statement (e.g. `Gemini 2.5 Flash (gemini-2.5-flash) — GA in europe-west1, verified via Model Garden on 2026-04-24`). A screenshot is **not** committed — screenshots rot and the commit diff should stay text-only (FR-010 discipline). The operator signs the verification by initials or GCP account.

On a future model-version change (Gemini 2.6 GA, Gemini 2.5 deprecation, etc.) the re-evaluation is a new dated bullet, not an edit to the original. This is the same append-only discipline as the Quota requests table.

**Rationale.** Model availability is a moving target; freezing it in the spec is wrong (the ADR-015 decision is about *region*, not about any particular model staying in that region forever). What we *can* freeze is "these two models were available in this region on this date, verified by this operator". That's the artefact downstream consumers actually need.

**Alternatives considered.**

- **Committed screenshot.** Rejected — screenshots become stale; reviewing a 2-year-old screenshot is worse than reviewing a dated line of Markdown.
- **Automated daily availability probe.** Rejected as out of scope — T01a doesn't own observability wiring (T38 does). Can be reconsidered there.
- **A single "always availability in europe-west1" assertion.** Rejected — nonsense; GCP retires models on a rolling cadence. Dated verification is the right shape.

---

## Open items / explicit deferrals

- **A shared group alias** (`techscreen-alerts@n-ix.com` or equivalent) replacing Ihor's personal mailbox. **Deferred** — tracked as a follow-up bullet inside the quota log's preamble, rotated in via a one-line `tfvars` edit when N-iX IT provisions the alias.
- **Automated availability probe.** Deferred to T38 observability wiring.
- **Forecasted-spend budget threshold.** Deferred — can be added later as a new `threshold_rule` without an ADR.
- **`T01a-v2`** for a Phase 2 scale-up above 20 concurrent sessions. Not filed now; the re-evaluation trigger in the quota log names the exact condition under which it must be filed.
- **GitHub Actions-driven `terraform apply`.** Deferred to T10 (CI pipeline). T01a is applied from the Owner's laptop, matching the `bootstrap.sh` pattern.
