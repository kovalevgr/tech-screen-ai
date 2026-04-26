# Feature Specification: Vertex AI quota + region request (T01a)

**Feature Branch**: `003-vertex-quota-region`
**Created**: 2026-04-24
**Status**: Draft
**Input**: User description: "T01a — Vertex AI quota + region request." (from [`docs/engineering/implementation-plan.md`](../../docs/engineering/implementation-plan.md) T01a, Tier 1 / W1–W2)

## Clarifications

### Session 2026-04-24

- Q: Which notification channel does T01a configure for the $50/mo budget alert, and does `cloud-setup.md` get updated in the same PR? → A: Ihor's personal N-iX mailbox as the direct Cloud Monitoring email channel for now; `cloud-setup.md` is updated to name that mailbox as the MVP recipient and to flag a follow-up to swap it for a shared group alias once one exists.
- Q: What is the acceptance bar if GCP grants a partial quota (e.g. Flash at 60 rpm but Pro only at default)? → A: T01a merges if each model meets a per-model workload floor recorded in the quota log — **Flash ≥ 30 rpm** (covers 3 concurrent sessions at expected turn rate) and **Pro ≥ 5 rpm** (once-per-session Planner). Below either floor, T01a is blocked until a re-raise lands. Any grant above the floor but below 60 rpm is acceptable and does not require a `T01a-v2`.
- Q: What format does `docs/engineering/vertex-quota.md` use? → A: Single Markdown doc with a fixed structure — (1) preamble: region, source of truth, re-evaluation trigger; (2) append-only Markdown table "Quota requests" with one row per request (columns: date, model, metric, default, requested, granted, case ID, requester, status, notes); (3) dated bullet lists for "Region verification" and "Smoke-test records". No YAML frontmatter, no separate machine-readable file.
- Q: Which smoke-test runner is sufficient to merge T01a? → A: Local ADC with service-account impersonation of `techscreen-backend@<project>` is sufficient for T01a merge (T01a does **not** block on T06). The deployed-Cloud-Run smoke against the same runtime SA is re-executed at the T11 Tier-1 checkpoint and recorded as a second row in the Smoke-test records section. T11's gate semantics enforce that the runtime-path smoke actually happens before Tier-1 sign-off.
- Q: What is the scope of the budget alert(s) T01a configures? → A: **Two** budgets. (1) Project-wide budget at $50/mo covering all services — the constitution §12 hard cap. (2) Vertex-only budget at $20/mo scoped to `aiplatform.googleapis.com` — the early-warning that isolates LLM spikes from general infra drift. Both use the 50 / 90 / 100 % thresholds and both target the same notification channel (Ihor's N-iX mailbox, per the first clarification).

### Session 2026-04-26 (post-implementation discovery)

During T01a implementation, a `gcloud alpha services quota list` against `tech-screen-493720` revealed that **Gemini 2.5 GA models do not use a per-minute REQUEST rate quota at all**. They use a **global INPUT-TOKENS-per-minute** metric (`aiplatform.googleapis.com/global_generate_content_input_tokens_per_minute_per_base_model`) with default limits of **10,000,000,000 TPM for `gemini-2.5-flash-ga`** and **1,000,000,000 TPM for `gemini-2.5-pro-ga`** (model identifiers in the quota table carry a `-ga` suffix that does not appear in the public `models/gemini-2.5-flash` API path). The legacy per-region per-model RPM metric (`generate_content_requests_per_minute_per_project_per_base_model`) covers only Gemini 1.x and TTS variants — it has zero entries for our 2.5 targets. Consequence: **the planned 60 rpm raise is moot** because (a) no such RPM metric exists for 2.5, (b) the actual TPM defaults are ~5–6 orders of magnitude above the PoC need (3 concurrent sessions ≈ 30 k tokens/min for Flash, ≪ 5 k for Pro). The chain "request-quota → wait 24-72 h → record granted values" is therefore a no-op for 2.5.

- Q: Given Gemini 2.5 uses TPM-based global quotas with multi-billion defaults, do we still submit a quota request and wait on GCP support? → A: **No.** No quota request is submitted for 2.5 models in T01a. The quota log records the **observed default TPM values** as the canonical baseline (replacing the previously planned `pending → granted` request flow). Tasks T012–T014 are marked `[X] superseded by 2026-04-26 finding`. Phase 4 collapses to one observation step (T012-revised) — no GCP support case, no 24-72 h wait. T01a can complete in a single sitting.
- Q: With no per-RPM metric to floor on, does the per-model workload floor decision (Clarifications 2026-04-24 Q2 — Flash ≥ 30 rpm, Pro ≥ 5 rpm) still bind T01a's merge? → A: **No.** The Q2 floor was framed in RPM units that don't exist for 2.5. It is **superseded by a TPM-based reality check**: T01a merges if `gemini-2.5-flash-ga` TPM ≥ 1,000,000 (one million input tokens per minute — covers ≥ 30 concurrent Interviewer turns at 30 k tok/min) AND `gemini-2.5-pro-ga` TPM ≥ 100,000 (covers ≥ 20 Planner runs/min at 5 k tok/run). The actual observed defaults (10 G / 1 G) blow past both floors by 10,000× / 10,000×. Floors are recorded in the quota log for completeness, not as gates.
- Q: How is the "Quota requests" table reframed when there is no actual request to track? → A: The table stays present (contract §3 invariant) but starts empty after the spec amendment, and is **populated only when GCP introduces a future RPM/TPM raise mechanism we actually use**. The previously planned `pending` rows for 2026-04-24 are removed. A new section "**Quota observed defaults**" is added to the log, recording the TPM defaults per model + region + verification date. Re-evaluation trigger remains unchanged (>20 concurrent sessions → file `T01a-v2`).
- Q: Does the cost-protection story shift now that there is no rate-limit ceiling at the API layer? → A: **Yes — budget alerts become the primary runaway-cost guard.** With effectively unlimited request rate AND multi-billion TPM, a buggy assessor loop can in principle burn $hundreds/hour. The Vertex-only $20/mo budget at 50 % threshold (i.e., $10) becomes the first line of defence; the per-session cost ceiling (planned for T21 in the implementation plan) becomes the second. T01a does not change this — it only highlights that budget alerts are no longer "early-warning to a rate ceiling" but "the only ceiling".
- Q: GCP billing API rejected the budgets with `INVALID_ARGUMENT` even after ADC scopes were corrected. Why? → A: The N-iX billing account `01FD59-751466-B7F7A5` is **denominated in PLN** (Polish złoty), confirmed via `gcloud beta billing accounts describe`. GCP requires every `google_billing_budget.amount.specifiedAmount.currencyCode` to **match the billing account's currency** — sending `USD` against a PLN account returns a generic 400 with no `details` array (structural mismatch, not field-level). Fix: budgets are denominated in PLN. The constitution §12 cap (originally "$50") is interpreted as **"approximately $50"** at ~4 PLN/USD: project-wide = **PLN 200 (≈ $50)**, Vertex-only = **PLN 80 (≈ $20)**. PLN/USD floats — the actual USD value of these caps may shift ±10 % across a year, which is acceptable for the PoC scope. Switching the billing account to USD would be an N-iX-treasury-level decision (out of T01a scope). If the conversion ever drifts > ±20 % from constitution intent, raise a follow-up to re-denominate.

## User Scenarios & Testing *(mandatory)*

The "users" of this feature are the humans and AI sub-agents who will rely on Vertex AI capacity for every LLM-driven feature downstream of Tier 1: `backend-engineer` (T04 Vertex wrapper), `prompt-engineer` (calibration runs), `infra-engineer` (budget monitoring + Terraform wiring), `reviewer` (checking every LLM-touching PR doesn't blow the budget), and the humans running the pilot — Ihor, the recruiter team, and the budget-alert recipient (Ihor's N-iX mailbox at MVP, per Clarifications 2026-04-24). Until Vertex quota is requested, granted, and documented, every downstream task that calls Vertex risks either unprovisioned-default rate-limits (60 reqs per minute is **not** the default; defaults are much lower) or silent budget overruns.

### User Story 1 — A downstream task owner can verify Vertex has enough capacity for their feature (Priority: P1)

Before T04 (Vertex client wrapper) or any later LLM-calling task starts live traffic, the author needs a single authoritative page telling them: which models are approved for use, what per-minute rate is granted, how much monthly budget is left, and whom to contact if a request hits a 429 or a cost guardrail. Without this page, each sub-agent has to ask Ihor or dig through GCP Console to discover limits — or worse, assumes defaults and ships a feature that breaks under calibration load.

**Why this priority**: Without the quota log, T04 is effectively blocked (per `depends_on: [T02, T01a]` in the plan) and so is every task behind it. The quota page is the canonical input to design decisions in T21 (per-session cost ceiling), T42 (calibration batch sizing), and T48a (concurrency smoke). This is the single document all three agents and the human owner must trust.

**Independent Test**: A sub-agent opens `docs/engineering/vertex-quota.md`, reads the current granted limits and the re-evaluation trigger, and can answer without consulting anyone: "Can my feature fire N concurrent Vertex calls today without being throttled?" They can also locate the support-case reference if the grant needs to be raised.

**Acceptance Scenarios**:

1. **Given** the T01a PR has merged, **When** a reviewer opens the quota log, **Then** the log contains the region, the requested values, the granted values, the GCP support-case reference, the requester, and the grant date.
2. **Given** the Vertex wrapper (T04) is about to ship, **When** the backend-engineer reads the quota log, **Then** they can determine whether their intended Interviewer + Assessor call pattern fits under the granted per-minute budget without further inquiry.
3. **Given** a sub-agent reads the log and believes the quota is insufficient for a new feature, **When** they follow the re-evaluation trigger, **Then** they arrive at a clearly named follow-up task (e.g. `T01a-v2`) rather than an ad-hoc quota escalation.

---

### User Story 2 — The configured alert recipient is warned about unexpected Vertex spend before it becomes a surprise (Priority: P1)

Constitution §12 caps monthly LLM spend at $50. Vertex traffic is the single largest variable cost in the MVP and the one most likely to spike from a bug (runaway retry loop, stuck session, calibration misconfiguration). Without proactive budget alerts, the first signal of over-spend is a billing statement at the end of the month — by which point the money is gone and the constitution has been violated.

**Why this priority**: Co-equal P1 with User Story 1 because budget discipline is a non-negotiable invariant (§12). The guardrail exists in the constitution; this story is what makes it enforceable at the GCP billing layer rather than as a good intention.

**Independent Test**: An operator manually triggers a budget notification preview (GCP Console → Billing → Budgets & Alerts → "Test") for the 50 % threshold and confirms the alert arrives at the configured inbox. The same check validates the 90 % and 100 % thresholds.

**Acceptance Scenarios**:

1. **Given** TechScreen billing is attached to the N-iX billing account, **When** T01a completes, **Then** a budget alert rule is in place targeting the `techscreen` GCP project with thresholds at 50 %, 90 %, and 100 % of $50 USD per month.
2. **Given** the budget alerts are configured, **When** a test notification is triggered on either the project-wide or the Vertex-only budget, **Then** it is received at Ihor's N-iX mailbox (the MVP recipient recorded in `docs/engineering/cloud-setup.md` per Clarifications 2026-04-24).
3. **Given** month-to-date Vertex spend crosses 50 % of the Vertex-only $20 budget (or project spend crosses 50 % of the project-wide $50 budget), **When** GCP evaluates the alert, **Then** the recipient mailbox receives a notification within one billing-alert polling cycle (≤ 24 hours per GCP SLA).

---

### User Story 3 — The team catches a region/model availability mismatch before it silently changes architecture (Priority: P2)

ADR-015 fixes the region at `europe-west1` (Belgium) for cost, latency, and data-residency reasons. ADR-003 fixes the models at Gemini 2.5 Flash + Pro. These two decisions assume the models are in fact available in that region. If one is not, the options are (a) switch model (violates ADR-003), (b) switch region (violates ADR-015), or (c) raise an ADR amendment. T01a is the first moment this combination is verified against the live Vertex Model Garden; silently switching one decision to rescue another is the failure mode we want to prevent.

**Why this priority**: P2 because the common case is "both models are available and the story is a non-event". When it fails, though, it fails loudly at a single point (T01a) rather than surfacing weeks later as a confusing deploy error in T11 or Tier 2 — so the verification step is cheap insurance.

**Independent Test**: A reviewer reads the verification line in `docs/engineering/vertex-quota.md`, confirms both models are listed as available in `europe-west1` as of the grant date, and that no region or model substitution was made without an ADR reference.

**Acceptance Scenarios**:

1. **Given** the quota log is committed, **When** a reviewer reads the "Region verification" section, **Then** they can see both Gemini 2.5 Flash and Gemini 2.5 Pro listed as available in `europe-west1` on the grant date.
2. **Given** either model is not available in `europe-west1` at request time, **When** T01a encounters the mismatch, **Then** the task raises an ADR-015 (or ADR-003) amendment proposal **before** merging, rather than silently switching region or model.
3. **Given** the region is verified, **When** a future task relies on `europe-west1` for Vertex, **Then** they can cite the verification line as evidence that the assumption still held at the last point of record.

---

### User Story 4 — A smoke call proves the quota and region are reachable end-to-end (Priority: P2)

A granted quota number in a PDF from GCP support is not the same as a working path. Between "quota granted" and "actual call succeeds" there are several failure modes: runtime service account missing `roles/aiplatform.user`, Workload Identity Federation misconfigured, the wrong Vertex endpoint hostname, model ID typo, Vertex outage at request time. The smoke test is the minimum proof that the whole chain — IAM → region routing → quota accounting — works before T04 lands.

**Why this priority**: P2 because T04 itself will exercise this path too; but doing the smoke at T01a time surfaces IAM/region problems while the infra-engineer is still in-context, not a week later when the backend-engineer is debugging their adapter and has to triage whether the bug is in their code or in the cloud wiring.

**Independent Test**: A runner (deployed Cloud Run revision, or a developer workstation authenticated via ADC with the runtime service account) issues a minimal Vertex `GenerateContent` call against Gemini 2.5 Flash in `europe-west1`, receives a 200 response, and the call completes within 10 seconds wall-clock.

**Acceptance Scenarios**:

1. **Given** quota is granted and the runtime service account exists, **When** the smoke call is issued against Vertex Gemini 2.5 Flash in `europe-west1`, **Then** the call returns a successful response within 10 seconds.
2. **Given** the smoke call fails for any reason, **When** T01a is reviewed, **Then** the failure mode is documented in the quota log with a concrete next action, and T01a does not claim acceptance until either the smoke passes or the failure is explicitly deferred with an issue reference.

---

### Edge Cases

- **Pilot scale vs. PoC scope.** The implementation plan explicitly warns: "request standard quotas, not enterprise. Resist the urge to over-provision". T01a scope is 3× concurrent sessions + a nightly calibration batch, not the entire MVP pilot maximum. Anything beyond that threshold must be deferred to `T01a-v2`.
- **Partial grant.** *(Largely moot for 2.5 GA models per Clarifications 2026-04-26 — no RPM raise mechanism is engaged.)* If FR-002 is ever re-engaged (e.g., a future Vertex model returns to RPM-based quotas), partial grants are logged verbatim — the log does not round up. T01a would then accept partial grants that meet each model's workload floor (now **TPM-based**: Flash ≥ 1,000,000 TPM, Pro ≥ 100,000 TPM — see FR-002a); any grant below a floor blocks T01a until the request is re-raised.
- **Pending case beyond one week.** GCP support may take 24–72 hours to act. If a case has been pending more than seven calendar days without response, T01a triggers a follow-up support contact (documented in the log) rather than silently waiting.
- **Region availability regression.** A model may be in GA today but move to a different region or be deprecated between the verification date and a later rollout. The quota log's verification line always includes a date so stale verifications can be re-checked.
- **Budget alert channel mismatch.** For the MVP pilot window the notification channel is Ihor's personal N-iX mailbox (Clarifications 2026-04-24). This is a deliberate, time-boxed trade-off: one recipient is acceptable while Ihor is the de-facto on-call, but the channel is a single point of failure, so `cloud-setup.md` MUST carry a visible follow-up item to swap in a shared group alias the moment one is provisioned. A Slack webhook not owned by the team, or any alias nobody reads, is not acceptable even if it delivers messages — channels are about on-call coverage, not about whether a message arrives.
- **Smoke call vs. T06 sequencing.** Per Clarifications 2026-04-24, T01a does not block on T06. The T01a-merge smoke is executed from a developer workstation using ADC auth with `techscreen-backend@<project>` impersonation, and the deployed-Cloud-Run smoke is re-executed at the T11 Tier-1 checkpoint (FR-006a) and appended as a second row to the "Smoke-test records" section. If the T11 re-execution fails, T11 is blocked — not T01a.
- **Over-provisioning temptation.** Any request for more than 60 rpm per model or any budget increase above $50/mo requires an ADR or a reference to one — it is not a configuration decision the infra-engineer may make unilaterally.
- **Secret hygiene.** The GCP support case may contain account identifiers, project numbers, or internal contact details that are acceptable to log, and may also contain tokens, cookies, or API keys that are **not**. The quota log MUST include only the minimum identifiers needed to trace the case, never payloads.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: T01a MUST commit a single authoritative document at `docs/engineering/vertex-quota.md` with the following fixed structure (Clarifications 2026-04-24):
  - **Preamble**: target region (`europe-west1`), the statement that this file is the single source of truth for Vertex quota state, and the re-evaluation trigger (FR-007).
  - **Quota requests** section: an append-only Markdown table with one row per quota request. Required columns: `date`, `model`, `metric`, `default`, `requested`, `granted`, `case_id`, `requester`, `status`, `notes`. Subsequent re-raises or denials are added as new rows, not edits to the original row.
  - **Region verification** section: a dated bullet list recording, per verification event, whether Gemini 2.5 Flash and Gemini 2.5 Pro are both available in `europe-west1`, with the evidence source.
  - **Smoke-test records** section: a dated bullet list of smoke-test outcomes (runner, model, region, wall-clock latency, pass/fail). No YAML frontmatter, no sibling machine-readable file.
- **FR-002 (revised 2026-04-26)**: T01a MUST verify, via `gcloud alpha services quota list --service=aiplatform.googleapis.com --consumer=projects/<project>`, that **default TPM quotas** for both `gemini-2.5-flash-ga` and `gemini-2.5-pro-ga` exceed the per-model floors documented in FR-002a. **No quota-raise request is submitted** for 2.5 models because the relevant metric is the global TPM `aiplatform.googleapis.com/global_generate_content_input_tokens_per_minute_per_base_model`, not the legacy per-region RPM `…/generate_content_requests_per_minute_per_project_per_base_model` (which has no entries for 2.5). Defaults observed at request time (typically 10 G TPM Flash, 1 G TPM Pro) are recorded verbatim in the quota log's "Quota observed defaults" section. If a default ever falls below the floor, this FR re-engages and a quota request is filed via the appropriate channel; until then, T012-T014 are no-ops (Clarifications 2026-04-26).
- **FR-002a (revised 2026-04-26)**: The quota log MUST record, as explicit per-model floor values, **Flash ≥ 1,000,000 TPM** (one million input tokens per minute — covers ~30 concurrent Interviewer turns at 30 k tok/min sustained) AND **Pro ≥ 100,000 TPM** (covers ~20 Pre-Interview Planner runs/min at 5 k tok each). Floors are recorded for completeness and for future re-engagement of FR-002 if defaults ever drop. The 2026-04-24 RPM-framed floors (Flash ≥ 30 rpm, Pro ≥ 5 rpm) are **superseded** by these TPM-framed equivalents (Clarifications 2026-04-26 Q2). Observed default values at or above both floors satisfy T01a acceptance.
- **FR-003**: T01a MUST verify at request time that both Gemini 2.5 Flash and Gemini 2.5 Pro are available in `europe-west1`. The verification evidence (a dated source — Vertex Model Garden listing screenshot reference or support-case confirmation) MUST be recorded in the quota log.
- **FR-004**: If either Gemini 2.5 Flash or Gemini 2.5 Pro is unavailable in `europe-west1` at request time, T01a MUST NOT silently switch region or model. Instead T01a MUST raise a proposed amendment to ADR-015 (region) or ADR-003 (model) and pause until the amendment is resolved.
- **FR-005**: T01a MUST configure **two** monthly budget alerts on the `techscreen` GCP project (Clarifications 2026-04-24):
  1. A **project-wide** budget at **$50 USD/month** covering all services — this is the constitution §12 hard cap.
  2. A **Vertex-only** budget at **$20 USD/month** scoped to `aiplatform.googleapis.com` — this is the early-warning that isolates LLM-side spikes from general infra drift.
  Both budgets MUST use threshold notifications at 50 %, 90 %, and 100 %, and both MUST target the same notification channel: Ihor's personal N-iX mailbox, wired as a Cloud Monitoring email channel. T01a MUST also update `docs/engineering/cloud-setup.md` in the same PR to name that mailbox as the MVP recipient (replacing the current placeholder wording) and to flag an explicit follow-up to swap the mailbox for a shared group alias once one exists.
- **FR-006**: T01a MUST produce a smoke-test record in the quota log proving that a minimal Vertex Gemini 2.5 Flash `GenerateContent` call against `europe-west1` returns within 10 seconds from a runner authenticated as (or impersonating) the intended runtime service account `techscreen-backend@<project>`. For T01a merge, a developer workstation using Application Default Credentials with service-account impersonation of `techscreen-backend@<project>` is sufficient (Clarifications 2026-04-24); T01a MUST NOT block on T06 (Cloud Run bring-up). The runner path actually used MUST be recorded alongside the latency measurement in the "Smoke-test records" section of the quota log.
- **FR-006a**: T01a MUST add an explicit entry to the T11 Tier-1 checkpoint's smoke scope requiring that, once T06 is deployed, the same Vertex Gemini 2.5 Flash smoke call is re-executed from the deployed Cloud Run revision and appended as a second row to the "Smoke-test records" section of the quota log. T11 is the gate at which the runtime-path smoke is validated; T01a itself remains independent of T06.
- **FR-007**: T01a MUST record a re-evaluation trigger in the quota log stating explicitly that if downstream concurrency targets exceed 20 concurrent sessions (the Phase 2 threshold), a new task `T01a-v2` MUST be raised **before** that rollout, not after.
- **FR-008**: The quota log MUST NOT contain any plaintext credential, API key, service-account JSON, OAuth token, or personally identifying information beyond the requester's team-level attribution (a role or alias, not a personal mobile number or home address).
- **FR-009**: The quota log MUST be discoverable from the existing engineering documentation index — either added as a referenced document from [`docs/engineering/cloud-setup.md`](../../docs/engineering/cloud-setup.md) and [`docs/engineering/vertex-integration.md`](../../docs/engineering/vertex-integration.md), or linked from `docs/engineering/directory-map.md`, so that a downstream sub-agent can locate it without prior knowledge of its filename.
- **FR-010**: T01a MUST NOT introduce application runtime code (no API endpoints, no frontend, no migrations, no agent prompts). Budget alert configuration that is expressible as Terraform SHOULD be committed under `infra/terraform/` so subsequent changes go through the same review path as the rest of the infrastructure; anything that cannot be expressed declaratively (manual GCP Console actions) MUST be recorded as a commented checklist in the quota log so the action is reproducible.
- **FR-011**: The quota-increase request MUST NOT exceed the PoC ceiling (~60 rpm per model, $50/mo budget) without a linked ADR justifying the raise. An over-provisioning raise is itself an architectural decision under constitution §12 and must go through the ADR process.
- **FR-012**: If the GCP support case is still in a pending state seven or more calendar days after submission without a response, T01a MUST record the escalation follow-up (re-contacting support, involving an alternative channel, or raising an issue) in the quota log rather than leaving the status field ambiguous. *(Inactive in T01a's current scope per Clarifications 2026-04-26 — no support case is filed for 2.5 models. Re-engages if FR-002 ever re-engages.)*

### Key Entities

- **Quota request.** A single GCP-side case asking to raise a specific metric on a specific model. Attributes: metric name; model name; region; current default value; requested value; granted value; support-case reference; request date; grant date; status.
- **Quota log entry.** A single row in the "Quota requests" Markdown table in `docs/engineering/vertex-quota.md` with the columns defined in FR-001 (`date`, `model`, `metric`, `default`, `requested`, `granted`, `case_id`, `requester`, `status`, `notes`). Append-only by convention: re-raises, denials, and scale-ups are added as new rows, never as edits to an earlier row. Verification notes, smoke-test outcomes, and the re-evaluation trigger live in their own dedicated sections of the same doc, not inside the table.
- **Budget alert rule.** A GCP Billing resource scoped to the `techscreen` project with an amount, a currency, a scope (services covered), and one or more threshold notifications. T01a creates two of them: a project-wide rule at $50/mo (all services) and a Vertex-only rule at $20/mo (`aiplatform.googleapis.com`). Shared attributes: thresholds 50 / 90 / 100 %; notification channel = Ihor's N-iX mailbox.
- **Re-evaluation trigger.** A conditional note in the quota log specifying when a follow-up task (`T01a-v2`) must be raised. Attributes: condition (e.g. "> 20 concurrent sessions"); action (raise `T01a-v2`); owner (infra-engineer).
- **Smoke-test record.** A line in the quota log showing: runner (Cloud Run revision or local ADC); model; region; wall-clock latency; pass/fail; date.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A sub-agent picking up T04 (or any later LLM-touching task) can answer "what is the current Vertex rate budget and who owns a raise if we need one?" in under five minutes using only the committed quota log — without opening GCP Console, Slack, or email.
- **SC-002**: The granted quota is sufficient to run 3 concurrent interview sessions plus one overnight calibration batch with **zero Vertex-originated 429 responses** during the MVP pilot window (≤ 50 sessions/month).
- **SC-003**: 100 % of months during the MVP pilot window have at least one budget alert fire before the hard ceiling is reached — there is no month in which project-wide spend exceeds $50 or Vertex-only spend exceeds $20 without a prior 50 % or 90 % notification landing in the configured mailbox.
- **SC-004**: The very first LLM call made by the Vertex wrapper (T04) from its intended runtime environment to Gemini 2.5 Flash in `europe-west1` returns a valid response on the first attempt and completes in under 10 seconds wall-clock — i.e., no additional IAM or region configuration is required between T01a and T04 going live.
- **SC-005**: Any future change that would raise concurrency above 20 sessions, raise the per-model rate above 60 rpm, or raise the monthly budget above $50 is preceded by a new ADR or a `T01a-v2` task citing one — zero silent raises occur during the MVP pilot window.
- **SC-006**: Zero committed files in the T01a PR contain a secret, credential, JSON service-account key, OAuth token, or named PII; validated by the guardrail hooks introduced in T01 running green on the PR.

## Assumptions

- The `techscreen` GCP project exists, is attached to the N-iX billing account, and has the minimum APIs enabled by `infra/bootstrap.sh` (Vertex AI / aiplatform.googleapis.com included). Bootstrapping is a T00 concern and is not re-done here.
- The requester on the GCP support case is the project owner (Ihor at MVP, per [`docs/engineering/cloud-setup.md`](../../docs/engineering/cloud-setup.md)), or a delegate Ihor explicitly nominates for this request.
- The MVP notification channel for budget alerts is Ihor's personal N-iX mailbox (Clarifications 2026-04-24). T01a updates `docs/engineering/cloud-setup.md` to name that mailbox explicitly and records a follow-up to replace it with a shared group alias once one is provisioned. Routing alerts to any other destination (personal mailbox of a non-owner, unowned Slack webhook, unmonitored alias) is not acceptable.
- Default Vertex quotas on a fresh project are below the 60 rpm target for Gemini 2.5 Flash and Pro; therefore a quota-request case is actually needed (as opposed to the request being a formality). If the default already meets or exceeds the target, T01a still commits the quota log documenting the observed defaults and the decision not to raise.
- The runtime service account (`techscreen-backend@<project>`, per cloud-setup.md) has `roles/aiplatform.user` either by T01a time or by T06 time. The smoke test runner uses whichever service account will carry Vertex traffic in production — it does not use a developer's personal identity.
- Standard quotas are acceptable for the PoC and pilot. Enterprise-tier quotas are deferred until a new ADR reverses the PoC cost/scope envelope (constitution §12, ADR-006).
- GCP Console → Quotas UI is the request channel. Quota requests via `gcloud` or REST are equivalent; the channel is left to the operator's discretion as long as the support-case reference is recorded.
- Budget alerts configured via Terraform are preferable to Console-click-ops wherever GCP supports it. Where GCP does not allow an alert attribute to be set via Terraform (historically true for some notification channels), the Console step is recorded as a documented manual action in the quota log.
- Vertex pricing as reflected in `llm/pricing.yaml` (committed later in T04) is the authoritative input to the $50/mo budget estimate. At T01a time, the estimate from `docs/engineering/cloud-setup.md` ($4–$10/mo Vertex on pilot volume) is the source of truth and leaves headroom for the full $50 cap.
- Constitution §7 (test coverage) does not require tests of the quota-request process itself; the smoke call is the minimum executable evidence. The guardrail hooks from T01 remain the default test surface.

## Dependencies

- **Upstream**: T00 (Spec Kit scaffolding), T01 (monorepo + tooling baseline); GCP project bootstrap (`infra/bootstrap.sh`), billing account attachment, Workload Identity Federation pool. ADR-002 (provider), ADR-003 (models), ADR-006 (PoC cost envelope), ADR-013 (secrets), ADR-015 (region), constitution §12 (budget + caps).
- **Downstream (blocked or impacted)**: T04 (Vertex client wrapper) and every subsequent LLM-touching task (T17, T18, T20, T21, T40–T44); T06a (deploy/rollback — budget alerts must exist before first prod traffic); T11 (Tier-1 checkpoint — gate); T48a (concurrent-session smoke — validates the 60 rpm × 3 ≤ quota assumption).
- **External**: GCP support (typical turnaround 24–72 hours for standard quota increases); Vertex AI model availability and pricing in `europe-west1`; N-iX billing administration (to confirm the project is attached and the budget is correctly scoped).
