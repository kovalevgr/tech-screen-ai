---
description: "Task list for T01a — Vertex AI quota + region request"
---

# Tasks: Vertex AI quota + region request (T01a)

**Input**: Design documents from [`specs/003-vertex-quota-region/`](./)
**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/vertex-quota-log-format.md](./contracts/vertex-quota-log-format.md), [quickstart.md](./quickstart.md)

**Tests**: Not generated. T01a ships zero runtime code, and constitution §7 does not require tests of the request process itself. Acceptance evidence is (a) the quota-log rows and bullets, (b) the `terraform plan` output pasted into the PR description, and (c) the smoke-test record. The quickstart walkthrough is the operational test for the full PR.

**Agent ownership**: Per `docs/engineering/implementation-plan.md` T01a, ownership is `agent: human + infra-engineer`, `parallel: false`. The `infra-engineer` sub-agent (or the main orchestrator acting in that role) authors the HCL, the smoke script, and the doc scaffolding. **Ihor** (or a nominated delegate with Owner on the GCP project) submits the GCP quota-request case, runs the local `terraform apply`, and executes the smoke script. Task descriptions below name the actor explicitly when it must be a human.

**Organization**: Tasks are grouped by user story. Story order reflects both spec priority (P1/P2) and the natural dependency chain: region verification (US3) must precede case submission (US1), the quota grant from US1 is a multi-day external wait so Terraform work (US2, plus the IAM slice that US4 needs) proceeds in parallel, and the smoke (US4) is the last-to-land because it requires both a granted quota and the runtime SA to exist.

## Note on the T01a IAM seed

T01a commits **two** new resource files under `infra/terraform/`: `billing.tf` (the budgets + notification channel — see Phase 5) and `iam.tf` (the seed runtime-SA slice — see Phase 6). Both are described in [`plan.md`](./plan.md) §Project Structure and §"Structure Decision", and the rationale for why `iam.tf` is part of T01a (FR-006 smoke test impersonation requirement; spec Assumption + Clarifications Q4) is in [`research.md`](./research.md) §R6. The `iam.tf` content T01a commits is strictly three resources: the `techscreen-backend@` SA, its `roles/aiplatform.user` binding, and a `roles/iam.serviceAccountTokenCreator` binding on that SA for the Owner principal that runs the smoke. T06 will later **extend the same file** with additional role bindings (Cloud SQL, Secret Manager, logging, monitoring) — additive, no rewrite.

## Post-rebase note (2026-04-26)

Between `/speckit-tasks` and `/speckit-implement`, **PR #2 (`002-terraform-backend-bootstrap`)** landed on main and seeded `infra/terraform/` with `provider.tf` + `versions.tf` + `backend.tf` (hardcoded bucket) + root `terraform.tfvars` + `.gitignore` + `.terraform.lock.hcl` (provider `~> 6.0`). On rebase, T01a's tasks **T002–T005** were marked **superseded by PR #2** — Ihor does not re-do them. **T006** was reframed from "create `envs/prod/terraform.tfvars` with placeholder values" to "extend root `terraform.tfvars` with three additional values" — a smaller edit on top of PR #2's baseline. **T015 / T016 / T020** had their `terraform plan` invocations simplified (no `-backend-config=`, no `-var-file=`; `terraform.tfvars` is auto-loaded from the working directory). The merged result was committed as `feat(T01a): seed Terraform billing + IAM, smoke script, quota log skeleton` after rebase (commit `c76476c`).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Different files, no intra-phase dependency — may be authored in any order.
- **[Story]**: Which user story the task serves (`US1`, `US2`, `US3`, `US4`). Setup, Foundational, and Polish tasks carry no story label.
- Paths are repo-root relative (`/Users/kovalevgr/project_new/TechScreen/.claude/worktrees/hungry-davinci-098253/`).

## Path Conventions

- Terraform HCL: `infra/terraform/*.tf` (flat root module — PR #2 baseline + T01a additions; no `envs/prod/` split per the post-rebase note above).
- Smoke script: `infra/scripts/vertex-smoke.sh` (first inhabitant of a new `infra/scripts/` folder).
- Quota log: `docs/engineering/vertex-quota.md` (new file, conforms to [contracts/vertex-quota-log-format.md](./contracts/vertex-quota-log-format.md)).
- Doc edits: `docs/engineering/cloud-setup.md`, `docs/engineering/directory-map.md`.

---

## Phase 1: Setup (Preflight)

**Purpose**: Confirm the working tree is clean and on the right branch before any HCL or docs land.

- [X] T001 Verify the current branch is `003-vertex-quota-region` with a clean working tree, `.specify/feature.json` points at `specs/003-vertex-quota-region`, and T01's baseline tooling passes (run `git rev-parse --abbrev-ref HEAD`, `git status --short`, `cat .specify/feature.json`, `pre-commit run --all-files`). If `pre-commit` finds untracked issues unrelated to T01a, stop and flag them — T01a must not carry fixes from other work. **Done 2026-04-26.** Branch + feature.json correct. Pre-commit `eslint (frontend)` hook fails because frontend `pnpm install` was not run in this worktree (pre-existing T01 tooling-env state, unrelated to T01a — T01a does not touch frontend). All T01a-relevant hooks (ruff, terraform-validate, gitleaks/detect-secrets analogues, forbid-*) pass. Flagged for Ihor: confirm OK to proceed; T023 will re-run pre-commit at end and may surface the same eslint issue — expected, treat as out-of-scope for T01a.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Seed the Terraform root module and the quota-log skeleton so every later phase writes into a consistent scaffold. Every later task assumes these files exist.

**⚠️ CRITICAL**: Phases 3–6 cannot begin until this phase is complete.

- [X] ~~T002 [P] Create `infra/terraform/providers.tf`...~~ **Superseded by PR #2 (`002-terraform-backend-bootstrap`).** PR #2 ships `provider.tf` (singular) + `versions.tf` (separate, provider `~> 6.0`). T01a takes that as baseline.
- [X] ~~T003 [P] Create `infra/terraform/variables.tf` declaring 5 vars...~~ **Superseded + extended.** PR #2's `variables.tf` declares `project_id` + `region`. T01a appends `project_number`, `billing_account`, `ops_email` to the same file. **Done 2026-04-26 (post-rebase).**
- [X] ~~T004 [P] Create `infra/terraform/backend.tf` — empty `terraform { backend "gcs" {} }` block...~~ **Superseded by PR #2.** PR #2's `backend.tf` has hardcoded `bucket = "tech-screen-493720-tf-state"`, `prefix = "terraform/state"` — no `-backend-config=` indirection. T01a takes that as-is.
- [X] ~~T005 [P] Create `infra/terraform/envs/prod/backend.hcl`...~~ **Removed by rebase.** PR #2's flat layout has no `envs/prod/`; backend bucket is hardcoded inline.
- [X] T006 [P] **Reframed by rebase.** PR #2 ships `infra/terraform/terraform.tfvars` (in repo root, not `envs/prod/`) with `project_id = "tech-screen-493720"` + `region = "europe-west1"` (real values). T01a appends three more values to the same file: `project_number = "463244185014"` (canonical, committed), `billing_account = "<FILL-IN: N-iX billing account ID>"`, `ops_email = "<FILL-IN: Ihor's N-iX mailbox>"`. **Done 2026-04-26 (post-rebase).** Ihor MUST replace the two `<FILL-IN: …>` placeholders before Phase 5 `terraform plan` — apply will fail with "variables not set" until done. `project_id`, `region`, `project_number` carry their canonical committed values.
- [X] T007 [P] Create `docs/engineering/vertex-quota.md` using the exact starter template from [contracts/vertex-quota-log-format.md](./contracts/vertex-quota-log-format.md) §8. The file MUST contain the six fixed top-level sections in order (`# TechScreen — Vertex AI Quota Log`, `## Re-evaluation trigger`, `## Quota requests`, `## Region verification`, `## Smoke-test records`, `## Follow-ups`). Section contents at T007 commit time:
    - **Re-evaluation trigger**: filled in (the canonical "> 20 concurrent sessions → raise T01a-v2" paragraph).
    - **Quota requests**: header row + two `status = pending` rows (one per model). The `default`, `case_id`, and `granted` columns carry placeholders — `<observed>` / empty — to be filled by T012, T013, T014.
    - **Region verification**: empty content per contract §8 — italic deferred-placeholder line `_(none yet — first bullet appended in Phase 3 …)_`. **No evidence bullet at T007 time.** The first real bullet is appended by T011 after T010 actually verifies availability.
    - **Smoke-test records**: empty content per contract §8 — italic deferred-placeholder line `_(none yet — first bullet appended in Phase 6 …)_`. **No smoke bullet at T007 time.** The first real bullet is appended by T021 after the smoke script actually runs.
    - **Follow-ups**: filled in (the MVP-mailbox-swap bullet from contract §6).
  Auditability rule: T007 commits a file shape, **never** evidence-claims. Evidence-claims (Region verification bullets, Smoke-test bullets, terminal Quota rows) are committed by the task whose execution actually produced the evidence. **Done 2026-04-26.** File created at `docs/engineering/vertex-quota.md`; Region verification and Smoke-test records sections carry the deferred-placeholder italic lines per contract §8.
- [X] T008 [P] Edit `docs/engineering/directory-map.md`. Three changes, all in this same edit:
    1. **Add a new row in the "Canonical folders" table** for `infra/scripts/` (a brand-new canonical folder that T019 creates as part of T01a — `infra/scripts/vertex-smoke.sh` is its first inhabitant). Per directory-map rule 1 ("Adding a new canonical folder: add a row in the same PR that creates the folder"), this row is mandatory. Columns: `Path = infra/scripts/`, `Owner task = T01a`, `Purpose = "One-shot operational scripts (smoke tests, ad-hoc infra probes). Bash-first, no language runtime required beyond gcloud + curl."`, `Populated by = T01a (vertex-smoke.sh, the FR-006 smoke runner). Future ad-hoc operational scripts append here without further directory-map edits."`.
    2. **Add a new row in the "Repo-root canonical files (non-folders)" section** pointing at `docs/engineering/vertex-quota.md` with `Owner task = T01a`, `Purpose = "Canonical Vertex AI quota log (region, granted quotas, verification, smoke-test records, follow-ups)"`.
    3. **Update the `infra/terraform/` row's `Populated by` column** to note that `billing.tf` + `iam.tf` (runtime SA + aiplatform.user binding only) + provider/backend scaffolding are seeded by T01a and extended by T06.
  Do not reshape any other row (FR-008 discipline). **Done 2026-04-26.** All three changes applied to `docs/engineering/directory-map.md`.
- [X] T009 [P] Edit `docs/engineering/cloud-setup.md`: replace the line "Alerts at 50 / 90 / 100 % of budget fire to the ops inbox" (around line 52) with a concrete pointer — "Alerts at 50 / 90 / 100 % of budget fire to Ihor's N-iX mailbox (MVP recipient; swap for a shared `techscreen-alerts@…` group alias once N-iX IT provisions one — tracked as a follow-up in [`docs/engineering/vertex-quota.md`](./vertex-quota.md))". In the same edit, cross-link the "Vertex AI" row in the Resource inventory table and the `$4 – $10` Vertex cost row to `docs/engineering/vertex-quota.md`. No other edits to this file. **Done 2026-04-26.** Two edits: (1) Vertex AI inventory row cross-linked to `vertex-quota.md`; (2) the budget paragraph rewritten to describe **two** budgets (project-wide $50 + Vertex-only $20), both targeting Ihor's mailbox per Clarifications Q1+Q5, with cost-table cross-link to `vertex-quota.md`.

**Checkpoint**: Terraform root is declared but has no resources yet; quota log is in place with the expected skeleton; both engineering-doc cross-references point at the new log.

---

## Phase 3: User Story 3 — Region verification (Priority: P2)

**Goal**: Record a dated evidence line in the quota log proving both Gemini 2.5 Flash and Gemini 2.5 Pro are available in `europe-west1`, **before** the quota request is submitted, so any mismatch forces an ADR conversation instead of a silent region switch.

**Independent Test**: Open the committed `docs/engineering/vertex-quota.md` "Region verification" section and confirm it contains a 2026-04-24 bullet naming both models, `region=europe-west1`, and a cited evidence source (FR-003 / FR-004 / spec Acceptance Scenarios US3).

### Implementation for User Story 3

- [ ] T010 [US3] (Human — Ihor or nominated delegate) Open the GCP Console → **Vertex AI → Model Garden**, filter by publisher `Google` and region `europe-west1`, confirm both `gemini-2.5-flash` and `gemini-2.5-pro` appear as GA. If either is missing, STOP: do not proceed to Phase 4. File an ADR-015 (region) or ADR-003 (model) amendment first (FR-004) and link the proposal PR in this task's PR before unblocking. Reference: [research.md](./research.md) §R7.
- [ ] T011 [US3] After T010 confirms availability, **append** the first bullet to the "Region verification" section of `docs/engineering/vertex-quota.md` and **remove** the deferred-placeholder italic line that T007 committed. New bullet must match the schema from [contracts/vertex-quota-log-format.md](./contracts/vertex-quota-log-format.md) §4 exactly: `- YYYY-MM-DD — gemini-2.5-flash, gemini-2.5-pro, region=europe-west1 — verified via Vertex Model Garden Console (Google publisher filter). Verified by project-owner (Ihor).` Use today's ISO date (the date T010 actually ran). Do not attach a screenshot (research §R7). The git commit for T011 is the first one to record verification evidence — the placeholder removal and the bullet append happen in the same commit.

**Checkpoint**: Region verification bullet is committed and dated; spec FR-003 is satisfied; the PR is cleared to move to Phase 4.

---

## Phase 4: User Story 1 — Quota request (Priority: P1)

**Goal**: The quota log's "Quota requests" table contains one terminal row per covered model (`status` ∈ {`granted`, `partial`}), each meeting the per-model workload floor (Flash ≥ 30 rpm, Pro ≥ 5 rpm, per Clarifications Q2 / FR-002a). This is the deliverable a downstream sub-agent reads in under five minutes (SC-001).

**Independent Test**: Inspect the "Quota requests" table in `docs/engineering/vertex-quota.md`. Confirm both `gemini-2.5-flash` and `gemini-2.5-pro` have non-pending terminal rows whose `granted` values meet the FR-002a floors, `case_id` is filled in, and `requester` carries a role/alias (no PII).

### Implementation for User Story 1

- [ ] T012 [US1] (Human — Ihor) Capture the current default quota on the target project by running `gcloud alpha services quota list --service=aiplatform.googleapis.com --consumer=projects/$(gcloud config get-value project) --filter="metric=GenerateContentRequestsPerMinutePerProjectPerModel" --format="table(metric, unit, quota_buckets.effective_limit, quota_buckets.dimensions)"` (reference: [research.md](./research.md) §R1). Record the observed integer value for Flash and Pro in the `default` column of the two pending rows in `docs/engineering/vertex-quota.md` — overwrite the `<observed>` placeholders from the Phase 2 starter template. Commit.
- [ ] T013 [US1] (Human — Ihor) Submit the GCP quota-request case via **Console → IAM & Admin → Quotas**: filter to `aiplatform.googleapis.com`, metric `GenerateContentRequestsPerMinutePerProjectPerModel`, region `europe-west1`, model dimension `gemini-2.5-flash` → click *Edit quotas* → request `60`. Repeat for model dimension `gemini-2.5-pro` → request `60`. Capture the support-case ID(s) that GCP issues. In `docs/engineering/vertex-quota.md` populate the `case_id` column for both pending rows; keep `status = pending`. Commit. Reference: [research.md](./research.md) §R2.
- [ ] T014 [US1] Wait for GCP terminal response on the case(s) (typical 24–72 h per cloud-setup.md). When each case closes, **append new rows** (do not edit the pending rows) to the "Quota requests" table with the terminal state for that model — `status` ∈ {`granted`, `partial`, `denied`} and the `granted` integer rpm. Rules:
    - If Flash `granted < 30` **OR** Pro `granted < 5`: STOP, re-raise via a follow-up support case (log the escalation in the "Follow-ups" section per contract §6), and do not proceed to Phase 5 or merge the PR.
    - If both floors are met (even below the 60 rpm target): proceed.
    - If the support case is still `pending` after seven calendar days without response: append a Follow-ups bullet documenting the re-contact action and do not merge (FR-012).
  Reference: [contracts/vertex-quota-log-format.md](./contracts/vertex-quota-log-format.md) §3, spec Clarifications Q2.

**Checkpoint**: Both models have terminal rows meeting the workload floors. Quota discovery, request, and grant are captured. Merge is still blocked on Phase 5 and Phase 6.

---

## Phase 5: User Story 2 — Budget alerts (Priority: P1)

**Goal**: Two `google_billing_budget` resources (project-wide $50/mo and Vertex-only $20/mo) with 50/90/100 % thresholds, both routing to a single `google_monitoring_notification_channel` pointed at Ihor's N-iX mailbox. Configured in Terraform so future rotations are diff-reviewable.

**Independent Test**: Run `terraform -chdir=infra/terraform plan` (after PR #2's `terraform init` is in state — `terraform.tfvars` auto-loads from the working dir) and confirm exactly three resources to add, zero to change, zero to destroy. After `terraform apply`, trigger a test notification in GCP Console → Billing → Budgets & Alerts and confirm it arrives in the mailbox.

### Implementation for User Story 2

- [X] T015 [US2] **Done 2026-04-26.** Create `infra/terraform/billing.tf` with:
    - One `google_monitoring_notification_channel "ops_email"`: `display_name = "TechScreen budget alerts (MVP recipient)"`, `type = "email"`, `labels = { email_address = var.ops_email }`, `enabled = true`.
    - One `google_billing_budget "project_wide"`: `billing_account = var.billing_account`, `display_name = "techscreen / project-wide $50"`, `budget_filter = { projects = ["projects/${var.project_number}"] }` (no `services` filter), `amount.specified_amount = { currency_code = "USD", units = "50" }`, three `threshold_rules` at `threshold_percent` `0.5`, `0.9`, `1.0` (all `spend_basis = "CURRENT_SPEND"`), `all_updates_rule = { monitoring_notification_channels = [google_monitoring_notification_channel.ops_email.id], disable_default_iam_recipients = true }`.
    - One `google_billing_budget "vertex_only"`: identical to `project_wide` except `display_name = "techscreen / vertex-only $20"`, `budget_filter.services = ["services/aiplatform.googleapis.com"]`, `amount.specified_amount.units = "20"`.
  Reference: [research.md](./research.md) §R3, §R4; [data-model.md](./data-model.md) §2, §3.
- [ ] T016 [US2] (Human — Ihor, from a machine authenticated as Owner on the prod project) Initialise the Terraform root and run a plan:
    ```bash
    cd infra/terraform
    gcloud auth application-default login   # if not already
    terraform init                          # backend bucket is hardcoded in backend.tf (PR #2)
    terraform plan -out=tfplan-phase5       # terraform.tfvars auto-loads from the working dir
    ```
  Expected summary: **3 to add**, 0 to change, 0 to destroy (channel + 2 budgets). Paste the summary into the PR description per [`docs/engineering/cloud-setup.md`](../../docs/engineering/cloud-setup.md) §"How to apply a change". If the plan shows any other resource, STOP — investigate drift before applying.
- [ ] T017 [US2] (Human — Ihor) Apply the Phase-5 plan: `terraform apply tfplan-phase5`. On success, in GCP Console → Billing → Budgets & Alerts, open each of the two budgets and trigger the email test notification at the 50 % threshold. Confirm both test emails arrive in the mailbox within the same minute. If either does not arrive within 5 minutes, investigate (common cause: mailbox forwarding rules) and do not merge until resolved.

**Checkpoint**: Two live budgets exist on the project; the single notification channel is email-tested. Spec FR-005 and SC-003 pre-conditions are satisfied.

---

## Phase 6: User Story 4 — Smoke test (Priority: P2)

**Goal**: Prove the full IAM → region → quota chain works end-to-end from a runner impersonating the intended runtime service account, with a recorded wall-clock latency under 10 seconds.

**Independent Test**: Execute `bash infra/scripts/vertex-smoke.sh` from a developer workstation authenticated as an Owner. Confirm the script prints one line matching the contract schema, exits 0, and the latency is below 10 000 ms. Append the printed line to the "Smoke-test records" section of `docs/engineering/vertex-quota.md`.

### Implementation for User Story 4

- [X] T018 [P] [US4] **Done 2026-04-26.** Create `infra/terraform/iam.tf` with the minimum T01a IAM shape (scope-limited per the **Note on the T01a IAM seed** above; full rationale in [plan.md](./plan.md) §"Structure Decision" and [research.md](./research.md) §R6):
    - `google_service_account "techscreen_backend"`: `account_id = "techscreen-backend"`, `display_name = "TechScreen backend runtime"`, `description = "Runtime identity for the Cloud Run backend (seeded by T01a; T06 extends)"`.
    - `google_project_iam_member "techscreen_backend_aiplatform_user"`: `project = var.project_id`, `role = "roles/aiplatform.user"`, `member = "serviceAccount:${google_service_account.techscreen_backend.email}"`.
    - `google_service_account_iam_member "techscreen_backend_tokens_for_owner"`: `service_account_id = google_service_account.techscreen_backend.name`, `role = "roles/iam.serviceAccountTokenCreator"`, `member = "user:<Ihor's N-iX identity>"` (the same human-owner principal that runs `terraform apply`). This binding is what makes `gcloud auth print-access-token --impersonate-service-account=techscreen-backend@…` work from the operator's laptop for the smoke.
    No other bindings. T06 extends this file with Cloud SQL / Secret Manager / logging / monitoring roles.
- [X] T019 [P] [US4] **Done 2026-04-26.** Script created at `infra/scripts/vertex-smoke.sh`, +x bit set. Create `infra/scripts/vertex-smoke.sh`. Required shape (reference [research.md](./research.md) §R5):
    - Shebang `#!/usr/bin/env bash`, `set -euo pipefail`, identical preamble comment style to `infra/bootstrap.sh`.
    - Inputs via env vars: `PROJECT_ID` (required), `RUNTIME_SA` (default `techscreen-backend@${PROJECT_ID}.iam.gserviceaccount.com`), `REGION` (default `europe-west1`), `MODEL` (default `gemini-2.5-flash`).
    - Obtain access token: `TOKEN="$(gcloud auth print-access-token --impersonate-service-account="${RUNTIME_SA}")"`.
    - Bracket-measure wall-clock latency around a single `curl --max-time 15 -sS -w "\n%{http_code}" -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" -X POST "https://${REGION}-aiplatform.googleapis.com/v1/projects/${PROJECT_ID}/locations/${REGION}/publishers/google/models/${MODEL}:generateContent" -d '{"contents":[{"role":"user","parts":[{"text":"ok"}]}],"generationConfig":{"maxOutputTokens":8,"temperature":0}}'`.
    - On HTTP 200 **and** latency < 10 000 ms: print one line exactly matching the contract schema from [contracts/vertex-quota-log-format.md](./contracts/vertex-quota-log-format.md) §5 — **comma-separated key=value pairs**: `runner=local-adc-impersonation, model=${MODEL}, region=${REGION}, latency_ms=<N>, status=pass`. Exit 0.
    - On any non-200 response or timeout: print the same comma-separated line with `status=fail` and an optional trailing `, notes=<short-token>` (e.g. `, notes=http429`), exit 1. `notes` value MUST NOT contain a comma (commas terminate parsing per contract §5).
    - Keep the script under ~50 lines. No jq dependency.
- [ ] T020 [US4] (Human — Ihor, from an Owner-authenticated machine) Apply the Phase-6 delta: `cd infra/terraform && terraform plan -out=tfplan-phase6 && terraform apply tfplan-phase6`. Expected new resources: 1 service account + 1 project-level IAM binding + 1 SA-level IAM binding. Budget resources from Phase 5 remain unchanged.
- [ ] T021 [US4] (Human — Ihor) Execute the smoke script against prod: `PROJECT_ID=<prod-project-id> bash infra/scripts/vertex-smoke.sh`. Expect exit 0 and a single stdout line containing `status=pass` and `latency_ms < 10000`, in the comma-separated format defined by contract §5. **Append** the first real bullet to the "Smoke-test records" section of `docs/engineering/vertex-quota.md` of the form `- YYYY-MM-DD — <stdout line>` (prepend today's ISO date and the em-dash separator; copy the script's stdout line **verbatim** — no re-formatting, since the script already emits commas) **and remove** the deferred-placeholder italic line that T007 committed. The git commit for T021 is the first one to record smoke evidence — the placeholder removal and the bullet append happen in the same commit. If the script exits non-zero, debug using [quickstart.md](./quickstart.md) §Troubleshooting; append a `status=fail` bullet *as well as* the eventual `status=pass` bullet (append-only discipline, contract §5 — both bullets remain in the log permanently).

**Checkpoint**: Smoke-test record with `status=pass, latency_ms < 10000, runner=local-adc-impersonation` is committed. Spec FR-006 and SC-004 are satisfied for T01a merge. T11 will later append the `runner=cloud-run-revision-<id>` bullet (FR-006a) — out of scope here.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: End-to-end validation against the success criteria. No net-new artefacts; this phase produces the reviewer-facing evidence.

- [ ] T022 [P] Run the [quickstart.md](./quickstart.md) Steps 1–7 walkthrough end-to-end against the T01a branch. Expect every checklist box to be markable `[x]`. Any failure is a merge-blocker; fix the underlying artefact (quota log, HCL, script, or doc) rather than relaxing the quickstart. **Partially done 2026-04-26 by infra-engineer (the parts that don't require GCP):** Step 1 — quota-log structure: ✅ all 6 fixed top-level headings present in correct order. Step 5 — cross-references: ✅ both `cloud-setup.md` and `directory-map.md` link to `vertex-quota.md`. File existence audit: ✅ all 5 Terraform files + smoke script + log present. **Pending Ihor's human-side actions:** Step 1 (granted values meeting floors — needs T014), Step 2 (region verification bullet — needs T011), Step 3a/3b (`terraform plan` outputs — need T016/T020), Step 4 (smoke record — needs T021).
- [X] T023 [P] Run `pre-commit run --all-files` on the full T01a branch. Expect zero findings from `gitleaks` and `detect-secrets` across every new/edited file (FR-008, SC-006). If any hook fires, fix the file; do not suppress the hook. **Done 2026-04-26.** All T01a-relevant hooks pass: `Detect hardcoded secrets`, `Terraform validate`, `forbid JSON service-account keys`, `forbid credential-shaped values in .env.example`, ruff. **Side-finding fixed during T023:** Initial run flagged `envs/prod/backend.tf` as malformed Terraform (raw `bucket=` / `prefix=` at file level — valid for `-backend-config=…`, invalid as standalone module). Renamed to `envs/prod/backend.hcl` (canonical extension for backend-config files); updated all references in `quickstart.md`, `tasks.md`, `infra/terraform/backend.tf` comment. Only failing hook is `eslint (frontend)` — pre-existing T01 tooling-env issue (no `pnpm install` in worktree), unrelated to T01a (confirmed by T001 preflight).
- [X] T024 [P] Confirm FR-008 discipline: `git diff origin/main -- CLAUDE.md README.md .pre-commit-config.yaml .env.example .gitignore .dockerignore docker-compose.yml docker-compose.test.yml Dockerfile Dockerfile.frontend Dockerfile.vertex-mock prompts/ adr/ configs/ alembic/` should return zero changes. Only expected modifications across the PR are under `infra/terraform/`, `infra/scripts/`, `docs/engineering/cloud-setup.md`, `docs/engineering/directory-map.md`, `docs/engineering/vertex-quota.md`, and `specs/003-vertex-quota-region/`. Any unexpected modification is a merge-blocker. **Done 2026-04-26.** `git diff` against protected paths returned **empty** (zero changes). All 21 modified/new files are in allowed paths. One auto-generated artefact: `infra/terraform/.terraform.lock.hcl` (provider-pin lock file, generated by pre-commit terraform_validate's `terraform init` step) — canonical to commit for reproducibility, same pattern as `pnpm-lock.yaml`.
- [ ] T025 Hand off to the `reviewer` sub-agent for the final constitution-adherence + secrets-scan + migration-safety gate (no Alembic migration exists; reviewer still runs the gate for completeness per `docs/engineering/multi-agent-workflow.md`). Record any blocking comments and re-run the quickstart after fixes.

**Checkpoint**: All success criteria from [spec.md](./spec.md) §Measurable Outcomes are satisfied. The PR is ready for merge.

---

## Dependencies & Execution Order

### Phase dependencies

- **Phase 1 Setup** (T001): no dependencies.
- **Phase 2 Foundational** (T002–T009): depends on Setup.
- **Phase 3 US3 Region verification** (T010–T011): depends on Foundational (needs the quota-log file to exist so the bullet can be appended).
- **Phase 4 US1 Quota request** (T012–T014): depends on US3 completion (FR-004 — region verified before request). External wait on GCP support may extend this phase by 1–3 days.
- **Phase 5 US2 Budget alerts** (T015–T017): depends on Foundational only. **Can run in parallel with Phase 4** — it does not need quota to be granted (the budgets cap spend regardless of the quota state).
- **Phase 6 US4 Smoke test** (T018–T021): depends on Foundational and **also** on Phase 4 terminal rows (quota must be granted so the smoke does not 429) and on its own IAM resource (T018). Cannot start until both are in place.
- **Phase 7 Polish** (T022–T025): depends on everything prior.

### User story dependencies

- **US3 (Region verification)** strictly precedes **US1 (Quota request)** — FR-004.
- **US1 (Quota request)** has an external GCP-side delay; during the wait, **US2 (Budget alerts)** is worked in parallel.
- **US4 (Smoke test)** depends on US1 terminal grant + the T01a IAM slice, both of which are in place after Phase 4 + T018+T020.

### Within each phase

- `[P]`-marked tasks within a phase may be authored in any order (they touch disjoint files).
- Non-`[P]` tasks within a phase are strictly sequential.
- T013 depends on T012 (default observed before request submitted).
- T014 depends on T013 (terminal rows after pending rows).
- T016 depends on T015 (plan needs HCL).
- T017 depends on T016 (apply needs plan).
- T020 depends on T018 + T019 (apply needs both files committed).
- T021 depends on T020 (smoke needs SA applied).

### Parallel opportunities within this task set

- **T002–T009** are all `[P]` — 8 disjoint files.
- **T015** (billing.tf) and **T018** (iam.tf) are both in `infra/terraform/` but different files — `[P]` across phases. They are NOT marked `[P]` inside a single phase because they belong to different stories; consolidating them inside one phase would break the story-independence discipline.
- **T019** (smoke script) is independent of **T018** (iam.tf) — `[P]`.
- **T022, T023, T024** in Polish are all `[P]` — independent audits.

**Constitution §18 reminder**: T01a declares `parallel: false` at the sub-agent level (`agent: human + infra-engineer`, sequential). The `[P]` markers above are intra-orchestrator hints only — they do not authorise sub-agent fan-out on this PR.

---

## Parallel Example: Phase 2 Foundational

After the rebase onto PR #2, Phase 2 shrunk from 8 disjoint authoring tasks to 4 (T002–T005 superseded by PR #2; T006 became a small append to PR #2's `terraform.tfvars`). The remaining four touch disjoint files and can be authored in any order:

```bash
# No dependency between these four files — any order works.
Task: "T006 — append three values to infra/terraform/terraform.tfvars (root, on top of PR #2)"
Task: "T007 — write docs/engineering/vertex-quota.md"
Task: "T008 — edit docs/engineering/directory-map.md"
Task: "T009 — edit docs/engineering/cloud-setup.md"
```

No Phase 3+ task may begin until all eight are committed (Foundational checkpoint).

---

## Implementation Strategy

### MVP slice

The T01a MVP is the **full spec**: there is no partial deliverable smaller than "quota granted, budgets live, smoke pass". A half-done T01a leaves T04 blocked, so there is no "ship earlier" option.

Operationally:

1. Phase 1 Setup (T001) — ~2 minutes.
2. Phase 2 Foundational (T002–T009) — ~30 minutes for HCL + docs authoring.
3. Phase 3 US3 (T010–T011) — ~5 minutes (Ihor's Model Garden check + bullet append).
4. **Branch-point**: Ihor files the quota case (T013) **and** the infra-engineer finishes Phase 5 HCL (T015) in the same sitting. The case sits with GCP support (external wait, 24–72 h).
5. When the grant lands, Ihor completes T014 (terminal rows), then runs T016–T017 (`terraform plan` / `apply`).
6. Ihor then runs T020 (second apply with iam.tf) and T021 (smoke). Appends the smoke bullet.
7. Phase 7 Polish (T022–T025) — ~20 minutes of audits and reviewer hand-off.

### Rollback posture

Every step is reversible:

- **Docs changes** (`vertex-quota.md`, `cloud-setup.md`, `directory-map.md`): `git revert`.
- **Terraform resources** (channel, budgets, SA, IAM bindings): `terraform destroy` or a PR-revert followed by `terraform apply` — completes in <2 minutes and produces no data loss (no user data exists in these resources).
- **GCP support case**: Ihor can request GCP to revert the grant; no on-box side effect.

Constitution §19 (rollback is a first-class operation) is satisfied trivially — T01a has no migration, no candidate data, no runtime behaviour to unwind.

---

## Notes

- File paths are absolute-ish relative to the repo root; no `cd` manoeuvres required during implementation.
- Commit cadence: one commit per phase is the suggested default; the `auto_commit: false` setting in `.specify/extensions/git/git-config.yml` means commits are manual. Group commits logically (e.g. one commit for T002–T009, one for T010–T011, one after the external wait with T012–T014, one for Phase 5, one for Phase 6, one for Polish).
- The external GCP-support delay is real; do not mark T014 complete until the support case reaches a terminal state.
- Any task whose acceptance fails in a way not covered by the spec: surface the ambiguity to the user (Ihor) before working around it — do not silently broaden T01a's scope.
- The `[P]` markers are intra-orchestrator hints; no sub-agent fan-out is authorised on this PR per `agent: human + infra-engineer, parallel: false`.
