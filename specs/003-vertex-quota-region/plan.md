# Implementation Plan: Vertex AI quota + region request (T01a)

**Branch**: `003-vertex-quota-region` | **Date**: 2026-04-24 (post-rebase amendment 2026-04-26) | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/003-vertex-quota-region/spec.md`

> **POST-REBASE NOTE (2026-04-26).** Between `/speckit-plan` and `/speckit-implement`, **PR #2 (`002-terraform-backend-bootstrap`, commit `a4ed063`)** landed on main. PR #2 seeded `infra/terraform/` first — with `provider.tf` (singular) + `versions.tf` (separate, provider `~> 6.0`) + `backend.tf` (hardcoded GCS bucket `tech-screen-493720-tf-state`) + `terraform.tfvars` in repo root (no `envs/prod/`) + `.gitignore` + lockfile. T01a was rebased onto that baseline. The Project Structure tree below and the Structure Decision were corrected to reflect the rebased reality; the rest of the plan (Constitution Check, Phase outlines) is unchanged. See `research.md` POST-REBASE NOTE and §R6 for the same amendment from a research-doc angle.

## Summary

T01a is the ops-and-docs PR that turns "Vertex quota" from an implicit assumption in the constitution (§12) and ADR-002/003/015 into a concrete, committed, auditable state: the `techscreen` GCP project has two budget alerts (project-wide $50/mo, Vertex-only $20/mo), a granted quota for `aiplatform.googleapis.com` metric `GenerateContentRequestsPerMinutePerProjectPerModel` on both Gemini 2.5 Flash and Pro at or above the per-model workload floors (Flash ≥ 30 rpm, Pro ≥ 5 rpm), a dated verification that both models are available in `europe-west1`, and a smoke-test record proving a real `GenerateContent` call from the runtime service account identity completes in under 10 seconds. All of this is recorded in a single Markdown file — `docs/engineering/vertex-quota.md` — which becomes the canonical read for every downstream LLM-touching task (T04 Vertex wrapper, T17/T18/T20/T21 agents, T42 calibration, T48a concurrency smoke). T01a also seeds the very first HCL under `infra/terraform/` (minimal Terraform root + `billing.tf` for the budgets + a minimal `iam.tf` that creates the `techscreen-backend@` runtime service account so the smoke test can impersonate it via local ADC) so T06 later extends an existing baseline rather than inventing one, and updates `docs/engineering/cloud-setup.md` and `docs/engineering/directory-map.md` so the new artefacts are discoverable.

Five decisions were locked in during `/speckit-clarify` (Session 2026-04-24):

1. **Notification channel**: Ihor's personal N-iX mailbox wired as a Cloud Monitoring email channel, with an explicit follow-up to swap for a shared group alias once provisioned.
2. **Partial-grant policy**: T01a merges on per-model workload floors — **Flash ≥ 30 rpm**, **Pro ≥ 5 rpm** — and is blocked below either floor until a re-raise lands.
3. **Quota log format**: single Markdown doc with a fixed structure (preamble → append-only table → dated bullets for verification and smoke). No YAML frontmatter, no parallel machine-readable file.
4. **Smoke-test runner**: local ADC with service-account impersonation of `techscreen-backend@<project>` is sufficient to merge T01a; the deployed-Cloud-Run re-run is gated at the T11 Tier-1 checkpoint.
5. **Budget scope**: two budgets — project-wide $50/mo (the §12 hard cap) **plus** Vertex-only $20/mo (LLM-spike early-warning). Both at 50/90/100 %.

## Technical Context

**Language/Version**: HCL (Terraform ≥ 1.5, `hashicorp/google` provider ≥ 5.x) · Bash (POSIX, for the one-shot smoke-test runner) · Markdown (docs + quota log). No application language — T01a ships zero runtime code.
**Primary Dependencies**:

- Terraform root under `infra/terraform/` with the GCS backend already bootstrapped by `infra/bootstrap.sh` (state bucket `<project>-tfstate`, Terraform SA `terraform@<project>`, WIF pool `github-actions`).
- Google provider resources: `google_billing_budget` (×2), `google_monitoring_notification_channel` (×1), `google_service_account` (×1 — the `techscreen-backend@` runtime SA), `google_project_iam_member` (×1 — `roles/aiplatform.user` on that SA), `google_service_account_iam_member` (×1 — `roles/iam.serviceAccountTokenCreator` on that SA, granted to the Owner identity that runs the smoke), plus provider/backend wiring (`google`, `google-beta` if needed for budget attributes).
- `gcloud` CLI on the operator machine for (a) submitting the quota-request case via Console or `gcloud alpha services quota update`, (b) ADC-based impersonation of the runtime SA for the smoke test, (c) local `terraform apply` via the operator's Owner identity (matches `bootstrap.sh` step 2 pattern — GitHub Actions-driven apply is T10).

**Storage**: Terraform state in the existing GCS bucket `<project>-tfstate` (created by `bootstrap.sh`). Quota-request records live in Markdown (`docs/engineering/vertex-quota.md`), not in a database — T01a does not touch Postgres.
**Testing**:

- `terraform fmt -check` and `terraform validate` are the static checks and run under the T01 `pre-commit` guardrails (wired into the hooks).
- `terraform plan` against prod is the rehearsal; it is reviewed in the PR description the same way `docs/engineering/cloud-setup.md` already describes for any infra change.
- The **smoke test** is the runtime evidence: a short Bash script calls Gemini 2.5 Flash via the Vertex `GenerateContent` REST endpoint using `gcloud auth print-access-token --impersonate-service-account=techscreen-backend@<project>`. Output (runner, latency, pass/fail, date) is appended to the "Smoke-test records" section of the quota log. The script is committed under `infra/scripts/` so it is re-runnable at the T11 Tier-1 checkpoint from a deployed Cloud Run revision (FR-006a).
- No unit tests are authored by T01a (no runtime code). Constitution §7 does not require tests of the request process itself; the smoke is the minimum executable evidence.

**Target Platform**: GCP project `techscreen` (project number `463244185014`, per [`docs/engineering/cloud-setup.md`](../../docs/engineering/cloud-setup.md)); region `europe-west1`. Operator machine is macOS (primary) or Linux (CI later); Windows is out of scope for MVP (matches T01).
**Project Type**: Infrastructure + documentation. No backend, no frontend, no migrations, no prompts, no agent code.
**Performance Goals**:

- Smoke-call latency **< 10 s wall-clock** end-to-end (FR-006, SC-004).
- `terraform apply` for the T01a delta completes in under 60 s on a warm cache (two budget resources + one notification channel — all lightweight).
- A sub-agent can answer "what is the current Vertex rate budget and who owns a raise?" in under 5 minutes using only the committed quota log (SC-001).

**Constraints**:

- **No runtime feature code** (FR-010): no API endpoints, no UI, no migrations, no agent prompts.
- **No secrets, no JSON SA keys, no PII** (FR-008, SC-006): enforced by the T01 guardrails (`gitleaks`, `detect-secrets`) running on this PR.
- **PoC cost envelope** (FR-011): quota requests capped at ~60 rpm per model and budgets capped at $50/mo project-wide + $20/mo Vertex-only; any increase needs a new ADR.
- **Per-model workload floors** (FR-002a): Flash ≥ 30 rpm, Pro ≥ 5 rpm are the merge gates, not the 60 rpm target.
- **Region lock** (FR-003/FR-004): silently switching region or model is forbidden — ADR-015/ADR-003 amendment is the required path.
- **§14 contract-first**: the contract for downstream consumers is the quota-log format committed in this same PR at [`contracts/vertex-quota-log-format.md`](./contracts/vertex-quota-log-format.md).
- **§8 prod-only topology**: T01a touches only the `prod` project; the smoke test runs locally with impersonation of the prod runtime SA (no data written), and the deployed-Cloud-Run re-run at T11 uses a 0 %-traffic revision path.
- **Append-only discipline** (§3 analogue): every subsequent quota re-raise or denial is a new row in the "Quota requests" table, never an edit to an earlier row.

**Scale/Scope**: Single PR, ~6–10 new files (Terraform HCL × 4–5, smoke script × 1, quota log × 1, plus edits to `cloud-setup.md` and `directory-map.md`), ~400 LOC including HCL + Markdown. Two committers acting sequentially: the human (Ihor or nominated delegate) submits the GCP quota-request case and runs `terraform apply`; the `infra-engineer` sub-agent authors the HCL, the smoke script, and the quota-log scaffolding before the human acts.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

T01a is ops-and-docs: no code, no data, no interactive flow. Four principles engage substantively (§5, §8, §12, §14); two have light indirect exposure (§16, §17, §18, §19). Full pass table:

| § | Principle | Applies to T01a? | Status |
|---|-----------|-----------------|--------|
| 1 | Candidates first | Indirectly — a quota exhaustion mid-interview would degrade the candidate experience; T01a is what prevents that. | Pass |
| 2 | Deterministic orchestration | No (no LLM calls in the PR's own behaviour) | N/A |
| 3 | Append-only audit trail | No application DB writes; the quota log itself follows an append-only convention (FR-001, Key Entities) as a discipline analogue, not a hard §3 requirement. | N/A at DB level |
| 4 | Immutable rubric snapshots | No | N/A |
| 5 | No plaintext secrets | **Yes.** Budget-alert notification uses an email address (not a secret) but the PR must not leak the billing-account ID or support-case payloads. FR-008 + SC-006 enforce; T01's `gitleaks` + `detect-secrets` hooks run on this PR. | Pass |
| 6 | Workload Identity Federation only | **Yes.** T01a creates the `techscreen-backend@` runtime SA in `iam.tf` and grants the Owner identity `roles/iam.serviceAccountTokenCreator` so the smoke can impersonate it via ADC — **no JSON SA key is created, downloaded, or referenced anywhere**. `bootstrap.sh`'s WIF pool is pre-existing and unchanged. | Pass |
| 7 | Docker parity dev → CI → prod | No (no container image built). | N/A |
| 8 | Production-only topology | **Yes.** T01a's two budgets and the notification channel target the sole prod project. The smoke test runs locally with impersonation of the prod runtime SA and writes nothing. No "dev" project is created. | Pass |
| 9 | Dark launch by default | No (no user-visible feature). | N/A |
| 10 | Migration approval | No (no Alembic migration). | N/A |
| 11 | Hybrid language | No (no prompts). | N/A |
| 12 | LLM cost and latency caps | **Yes — T01a is the physical enforcement of §12.** Budget alerts at 50/90/100 % of $50 (project-wide) and $20 (Vertex-only) and the quota floors that keep session cost tractable. | Pass (T01a strengthens §12) |
| 13 | Calibration never blocks merge | No (no calibration). | N/A |
| 14 | Contract-first for parallel work | T01a declares `parallel: false` (human + infra-engineer sequential; no sub-agent fan-out), so the rule does not hard-engage. The implementation plan still names a contract — `docs/engineering/vertex-quota.md` — which T01a commits in this PR at the format pinned by [`contracts/vertex-quota-log-format.md`](./contracts/vertex-quota-log-format.md). | Pass |
| 15 | PII containment | No (no candidate data). | N/A |
| 16 | Configs as code | **Yes.** The two budgets, the notification channel, and the runtime SA (+ its `roles/aiplatform.user` and `roles/iam.serviceAccountTokenCreator` bindings) are all declared in Terraform HCL under `infra/terraform/billing.tf` and `infra/terraform/iam.tf`; the quota state lives in `docs/engineering/vertex-quota.md`. Console-only steps (the support-case submission itself) are recorded as a reproducible checklist in the quota log (FR-010). | Pass |
| 17 | Specifications precede implementation | `/speckit-specify` and `/speckit-clarify` ran before this plan; 5 clarifications integrated. | Pass |
| 18 | Multi-agent orchestration is explicit | `agent: human + infra-engineer`, `parallel: false`. No automatic fan-out. The `infra-engineer` sub-agent produces HCL + script + doc scaffolding; the human executes the GCP Console step and the `terraform apply`. | Pass |
| 19 | Rollback is a first-class operation | T01a is trivially reversible: a PR revert removes the budgets and the docs; the quota grant on the GCP side is a one-click "cancel" in the support case (and a denied/rolled-back grant changes nothing runtime-observable because no code consumes it yet — T04 is downstream). | Pass |
| 20 | Floor, not ceiling | Pass | Pass |

**Gate result**: **PASS**. No violations, no justifications required in Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/003-vertex-quota-region/
├── spec.md                           # Feature spec (+ Clarifications section, v1 after 5 answers)
├── plan.md                           # This file
├── research.md                       # Phase 0 — Terraform + quota + smoke-test choices
├── data-model.md                     # Phase 1 — entity map (quota request, log entry, budget, channel, re-eval trigger, smoke record)
├── contracts/
│   └── vertex-quota-log-format.md    # Phase 1 — the quota-log file contract (schema + template)
├── quickstart.md                     # Phase 1 — reviewer-facing validation walkthrough
├── checklists/
│   └── requirements.md               # From /speckit-specify (all green)
└── tasks.md                          # Created by /speckit-tasks (NOT this command)
```

### Source Code (repository root)

After T01a merges, the repo delta looks like this. Bold entries are created or edited by T01a; everything else is pre-existing and untouched.

```text
.                                          # repo root
├── docs/
│   └── engineering/
│       ├── cloud-setup.md                # EDITED — "ops inbox" → Ihor's N-iX mailbox (with swap-to-alias follow-up); row mentioning the new quota log
│       ├── directory-map.md              # EDITED — new row pointing at docs/engineering/vertex-quota.md; T06 row annotated that billing.tf and the iam.tf seed (runtime SA + roles/aiplatform.user only) were seeded by T01a
│       └── vertex-quota.md               # NEW — the canonical quota log (preamble + Quota requests table + Region verification + Smoke-test records)
├── infra/
│   ├── bootstrap.sh                      # pre-existing, unchanged
│   ├── scripts/                          # NEW folder (T01a — first inhabitant; .gitkeep not needed since vertex-smoke.sh is inside)
│   │   └── vertex-smoke.sh               # NEW — minimal Bash smoke-test runner (ADC impersonation → Gemini 2.5 Flash in europe-west1 → latency report)
│   └── terraform/                        # PR #2 seeded the root module; T01a layered billing + iam on top
│       ├── backend.tf                    # PR #2 (unchanged) — hardcoded GCS bucket "tech-screen-493720-tf-state"
│       ├── provider.tf                   # PR #2 (unchanged) — google provider config
│       ├── versions.tf                   # PR #2 (unchanged) — terraform>=1.5, provider hashicorp/google ~> 6.0
│       ├── variables.tf                  # MERGED — PR #2's project_id + region; T01a added project_number, billing_account, ops_email
│       ├── terraform.tfvars              # MERGED — PR #2's project_id + region (real values); T01a added project_number value + billing_account/ops_email placeholders (Ihor fills before apply)
│       ├── .gitignore                    # PR #2 (unchanged) — terraform state + plan ignores
│       ├── .terraform.lock.hcl           # PR #2 (unchanged) — provider 6.50.0
│       ├── billing.tf                    # T01a NEW — google_monitoring_notification_channel + 2× google_billing_budget
│       └── iam.tf                        # T01a NEW — google_service_account techscreen_backend + roles/aiplatform.user + roles/iam.serviceAccountTokenCreator on the Owner principal (smoke-impersonation grant). T06 extends with Cloud SQL/Secret Manager/logging/monitoring bindings.
```

**Structure Decision (post-rebase)**: PR #2 (`002-terraform-backend-bootstrap`) was the first task to place HCL under `infra/terraform/` and chose a flat root layout (no `envs/prod/` split, hardcoded backend bucket, separate `provider.tf` + `versions.tf`). T01a was rebased onto that baseline and adopted PR #2's conventions wholesale, adding only what T01a uniquely needs: extra variables in `variables.tf` (`project_number`, `billing_account`, `ops_email`), placeholder values in `terraform.tfvars`, and two new resource files — `billing.tf` (the *billing alerts* slice) and `iam.tf` (the *runtime-SA seed* slice — only the `techscreen-backend@` SA, its `roles/aiplatform.user` binding, and the `serviceAccountTokenCreator` binding for the Owner that runs the smoke). The runtime-SA slice is the minimum required for the FR-006 smoke test to impersonate the intended runtime identity from a developer laptop without a JSON key, and is sanctioned by the spec's Assumption that the SA "has `roles/aiplatform.user` either by T01a time or by T06 time" combined with Clarifications Q4 (T01a does not block on T06). T06 will later extend `iam.tf` additively (more bindings on the same SA) and add `sql.tf`, `cloud_run.tf`, `artifact_registry.tf`, `secrets.tf`, `monitoring.tf`, `network.tf`. The directory-map row for `infra/terraform/` is updated to reflect this layered ownership (PR #2 baseline + T01a additions + T06 extensions). No `envs/dev/` is introduced — per constitution §8.

The `infra/scripts/` folder is new; the smoke-test runner is its first inhabitant. This is a deliberately small addition (one file) — placing the script under `infra/` keeps it near the Terraform that provisions the thing it exercises, and `bash` is the only sensible runtime (no Python packaging required). The script is self-documenting with a usage comment, matches the `bootstrap.sh` style, and re-runs at T11 against a deployed Cloud Run revision (FR-006a).

**Single active committer per step, no parallel fan-out**: `agent: human + infra-engineer`, `parallel: false`. The `infra-engineer` sub-agent authors the HCL, the script, and the docs scaffolding in a draft PR; the human (Ihor or a nominated delegate) then (a) submits the GCP quota-request support case, (b) records the case ID and granted values in the log, (c) runs `terraform apply` locally against prod, (d) executes the smoke script and appends its output, (e) requests review. The `reviewer` sub-agent validates constitution adherence before merge.

## Phase 0 — Outline & Research

Research output: [research.md](./research.md) (generated as part of this plan run).

The spec has no `[NEEDS CLARIFICATION]` markers after the five clarifications. Phase 0 resolves implementation-detail questions that are below the spec's altitude but above `/speckit-tasks` altitude:

1. **Vertex quota mechanics** — which metric name is actually `aiplatform.googleapis.com`'s per-model-per-minute counter today, and what is the default value for a new project so the "default → requested" column in the log is accurate.
2. **Quota-request channel** — GCP Console vs `gcloud alpha services quota update-quota-override` vs the support-case portal; evidence handling for each.
3. **`google_billing_budget` Terraform shape** — required provider version, whether `all_updates_rule` is needed for notification channels, scope filters (`projects/<id>`) vs service filters (`services/aiplatform.googleapis.com`).
4. **`google_monitoring_notification_channel` for email** — can the channel be created declaratively with a plain email address today, or does GCP still require a "verify" ping outside Terraform?
5. **Smoke-test path** — Gemini 2.5 Flash REST payload shape (`v1:generateContent`), the exact scope an ADC-impersonated access token needs, and how to record latency accurately in Bash.
6. **Terraform root layout** — given that T06 will later add Cloud Run, Cloud SQL, Secret Manager, and IAM resources, how should T01a's root module be organised so T06 extends without renaming files or rewriting provider configuration.
7. **Model availability verification** — what is the authoritative source for "Gemini 2.5 Flash / Pro available in europe-west1" that can be cited in the log, and does that source survive model-version updates (i.e. will a future Gemini 2.6 invalidate the citation).

All resolved in `research.md` with rationale and rejected alternatives.

## Phase 1 — Design & Contracts

**Prerequisites**: `research.md` complete.

### Data model

See [data-model.md](./data-model.md). T01a has no application data. The spec's Key Entities (quota request, quota log entry, budget alert rule, re-evaluation trigger, smoke-test record) are re-expressed as a compact entity map with fields, allowed values, and lifecycle notes, so both the `reviewer` sub-agent and every downstream consumer share one canonical reading.

### Contracts

See [contracts/vertex-quota-log-format.md](./contracts/vertex-quota-log-format.md). The quota log is the cross-task contract named in the implementation plan. The contract file pins:

- The fixed section order (`# TechScreen — Vertex AI Quota Log` → Preamble → Quota requests table → Region verification → Smoke-test records → Re-evaluation trigger).
- The exact column set for the Quota requests table (`date | model | metric | default | requested | granted | case_id | requester | status | notes`) and the allowed enumerated values for `status` (`pending`, `granted`, `partial`, `denied`, `rolled-back`).
- The bullet schema for Region verification and Smoke-test records (date → outcome → evidence).
- Append-only discipline: re-raises and denials are new rows, not edits.

This file is authored in this PR and referenced by T04 (Vertex wrapper), T42 (calibration batch sizing), T48a (concurrency smoke), and the `reviewer` sub-agent.

### Quickstart

See [quickstart.md](./quickstart.md) — a 7-step walkthrough a reviewer (human or `reviewer` agent) can execute end-to-end in under 10 minutes. It mirrors the spec's Acceptance Scenarios: quota-log inspection → region-verification line → budget Terraform plan → smoke-test script run → per-model floor check → SC-006 secret-hygiene scan → sign-off. Each step names the exact file or command, so the quickstart doubles as the T11 Tier-1 checkpoint script for re-running the smoke from the deployed Cloud Run revision.

### Agent context update

`CLAUDE.md` does **not** carry `<!-- SPECKIT START -->` / `<!-- SPECKIT END -->` markers — T00 deliberately stripped them (see `docs/engineering/implementation-plan.md` T00 "Trim before commit"), and T01's plan confirmed this. The project's existing "How work happens here (Spec Kit)" section in CLAUDE.md already points sub-agents at the Spec Kit flow, so T01a does not re-introduce the auto-generated block. No CLAUDE.md edit from this step.

What T01a *does* edit in the agent-context surface:

- [`docs/engineering/directory-map.md`](../../docs/engineering/directory-map.md) — new row for `docs/engineering/vertex-quota.md`; the `infra/terraform/` row is annotated to note that `billing.tf` and the seed `iam.tf` (runtime SA + `roles/aiplatform.user` + Owner `serviceAccountTokenCreator` binding only) were seeded by T01a (with T06 extending the same files).
- [`docs/engineering/cloud-setup.md`](../../docs/engineering/cloud-setup.md) — line 52's "ops inbox" phrasing is replaced with a concrete pointer to Ihor's N-iX mailbox + a visible follow-up to swap for a shared alias; the Vertex AI row (line 34 and cost row line 49) is cross-linked to the new quota log.

### Re-evaluate Constitution Check (post-design)

Nothing in Phase 0/1 changes the Constitution Check result. Gate remains PASS. The contract file and the smoke script do not introduce secrets, LLM calls, or state-machine routing; they are ops artefacts and a one-shot test runner respectively.

## Complexity Tracking

Not applicable — no Constitution Check violations.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| *(none)* | — | — |
