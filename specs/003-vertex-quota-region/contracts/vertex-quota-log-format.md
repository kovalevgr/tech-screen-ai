# Contract: `docs/engineering/vertex-quota.md` format

**Branch**: `003-vertex-quota-region` · **Date**: 2026-04-24 · **Status**: normative for T01a and for every downstream task that reads or appends to the quota log

This file **pins the shape** of `docs/engineering/vertex-quota.md`. It is the cross-task contract named in [`docs/engineering/implementation-plan.md`](../../../docs/engineering/implementation-plan.md) T01a ("contract: `docs/engineering/vertex-quota.md` one-pager") and referenced by downstream LLM-touching tasks. It is append-only in spirit: the `reviewer` sub-agent validates that every change to `vertex-quota.md` conforms to the layout and the field schemas below.

The contract is Markdown-only. There is no parallel machine-readable file (Clarifications 2026-04-24 Q3).

---

## 1. File location

- **Path**: `docs/engineering/vertex-quota.md`
- **Encoding**: UTF-8, LF line endings.
- **Owner task of this file**: T01a (creation) · every future quota-related task (append-only edits).

## 2. Fixed section order

The file MUST contain exactly the following top-level sections, in this order, with no other top-level headings:

```text
# TechScreen — Vertex AI Quota Log
<preamble paragraphs>
## Re-evaluation trigger
<one paragraph naming condition + action + owner>
## Quota requests
<Markdown table; see §3>
## Region verification
<dated bullets; see §4>
## Smoke-test records
<dated bullets; see §5>
## Follow-ups
<Markdown bullet list; see §6>
```

Additional second-level headings are forbidden. Third-level headings are permitted only inside "Follow-ups" for grouping long-lived items.

## 3. "Quota requests" table — schema

The "Quota requests" section MUST contain exactly one Markdown table with the following columns in the following order:

```markdown
| date | model | metric | default | requested | granted | case_id | requester | status | notes |
| ---- | ----- | ------ | ------- | --------- | ------- | ------- | --------- | ------ | ----- |
```

Column rules:

- **`date`** — ISO 8601 (`YYYY-MM-DD`). The date the support case was submitted. Required.
- **`model`** — Vertex publisher model ID, lowercase, kebab-case. Allowed values while ADR-003 holds: `gemini-2.5-flash`, `gemini-2.5-pro`. A different value requires an ADR amendment.
- **`metric`** — GCP quota metric. For T01a: `GenerateContentRequestsPerMinutePerProjectPerModel`. Different metrics need different rows.
- **`default`** — integer requests-per-minute as observed on the target project **at request time**. Not a hard-coded value from documentation.
- **`requested`** — integer rpm; the target raise.
- **`granted`** — integer rpm. Empty string `""` while `status = pending`. Must be filled for any non-`pending` status.
- **`case_id`** — the GCP support-case ID (numeric). Empty string only while the case is in flight; must be filled before any non-`pending` row is committed.
- **`requester`** — team or role alias. Permitted: `project-owner (<name>)`, `infra-engineer (<alias>)`. Forbidden: personal phone numbers, home addresses, or any credential-shaped string (FR-008).
- **`status`** — enum, one of exactly: `pending` · `granted` · `partial` · `denied` · `rolled-back`.
- **`notes`** — free text, single line, ≤ 160 characters. No multi-line cells. Empty is allowed.

**Append-only discipline.** A row is added for every event that changes GCP-side state:

- The initial submission (one row per model).
- Any terminal response from GCP (one row per model: `granted`, `partial`, or `denied`).
- Any later re-raise, scale-up, or roll-back.

Rows are never edited in place after the row's state has been committed to main. Typos and wording fixes are permitted in the same commit that introduced the row; once on main the row is frozen and any correction is a new row with `notes` explaining the supersession.

## 4. "Region verification" section — bullet schema

Each bullet MUST take the form:

```markdown
- YYYY-MM-DD — <models covered>, region=<region> — verified via <source>. Verified by <alias>.
```

- `<models covered>` — comma-separated `gemini-2.5-flash, gemini-2.5-pro` (or more if new models are added under an ADR).
- `<region>` — the single target region. For T01a: `europe-west1`.
- `<source>` — a short human-readable reference (e.g. `Vertex Model Garden Console, Google publisher filter`). Screenshots are not committed (FR-010 discipline — see research R7).
- `<alias>` — role or alias, not a personal contact.

One bullet per verification event. Re-verifications append; earlier bullets remain.

If any verification bullet's `<region>` does not match the ADR-015 region for models mandated by ADR-003, the file MUST NOT pass `reviewer` gate and T01a MUST NOT merge (FR-004).

## 5. "Smoke-test records" section — bullet schema

Each bullet MUST take the form:

```markdown
- YYYY-MM-DD — runner=<runner>, model=<model>, region=<region>, latency_ms=<int>, status=<pass|fail>[, notes=<short note>]
```

- `<runner>` — enum, one of:
  - `local-adc-impersonation` — operator laptop with `gcloud auth print-access-token --impersonate-service-account=techscreen-backend@…`. Sufficient for T01a merge (Clarifications 2026-04-24 Q4).
  - `cloud-run-revision-<revision-id>` — deployed Cloud Run revision. Required by T11 (FR-006a).
- `<latency_ms>` — integer wall-clock ms from the smoke script's own bracket measurement.
- `<status>` — `pass` if `latency_ms < 10000` AND the HTTP response was a successful `generateContent` payload; `fail` otherwise.
- `notes=` is optional and, when present, must be a single token or a short phrase (no commas — commas terminate the key=value parsing).

At least one `status=pass` bullet is required for T01a acceptance; at least one `status=pass` bullet with `runner=cloud-run-revision-*` is required for T11 sign-off.

## 6. "Follow-ups" section — bullet list

A Markdown bullet list of live follow-ups the log tracks until they close. Minimum initial content:

```markdown
- Swap the MVP budget-alert recipient (Ihor's personal N-iX mailbox) for a shared group alias once N-iX IT provisions one. One-line `envs/prod/terraform.tfvars` edit + `terraform apply`.
```

Additional bullets may be added (e.g. "probe Model Garden quarterly for Gemini 2.6 GA"). When a follow-up closes, strike it through and annotate with the resolution date rather than deleting it.

## 7. "Re-evaluation trigger" section — text schema

A single paragraph that MUST mention:

- a concrete numeric **condition** (e.g. `> 20 concurrent sessions` or `Vertex-only spend exceeding $20/mo for two consecutive months`),
- a concrete **action** (e.g. "raise a Spec Kit feature named `T01a-v2`"),
- a concrete **owner** (e.g. "`infra-engineer` + project owner").

Vague re-evaluation wording ("revisit if things scale") is a contract violation and must be rejected by the `reviewer` gate.

## 8. Starter template

This is the exact file T01a commits on day zero. Downstream tasks append to it; the preamble and trigger text can be refined but not substantially reshaped without updating this contract.

```markdown
# TechScreen — Vertex AI Quota Log

**Status:** initial commit · **Region:** europe-west1 · **Source of truth:** this file

This is the single source of truth for TechScreen's Vertex AI quota state: what was requested, what GCP granted, when, and what must happen next. Every LLM-touching task downstream of T01a reads this file before provisioning a new workload.

## Re-evaluation trigger

If projected or realised concurrent interview sessions exceed **20** — the Phase 2 threshold in the implementation plan — the `infra-engineer` (with the project owner) MUST raise a new Spec Kit feature named `T01a-v2` to request higher quota **before** that rollout. Triggers sourced from constitution §12 and `docs/engineering/implementation-plan.md` T01a.

## Quota requests

| date | model | metric | default | requested | granted | case_id | requester | status | notes |
| ---- | ----- | ------ | ------- | --------- | ------- | ------- | --------- | ------ | ----- |
| 2026-04-24 | gemini-2.5-flash | GenerateContentRequestsPerMinutePerProjectPerModel | <observed> | 60 | | | project-owner (Ihor) | pending | initial T01a request |
| 2026-04-24 | gemini-2.5-pro | GenerateContentRequestsPerMinutePerProjectPerModel | <observed> | 60 | | | project-owner (Ihor) | pending | initial T01a request |

## Region verification

_(none yet — first bullet appended in Phase 3 once Vertex Model Garden availability is verified for `europe-west1`. The contract requires this section be present and ordered, but its contents are deferred until evidence exists.)_

## Smoke-test records

_(none yet — first bullet appended in Phase 6 once `infra/scripts/vertex-smoke.sh` executes against the granted quota. The contract requires this section be present and ordered, but its contents are deferred until evidence exists.)_

## Follow-ups

- Swap the MVP budget-alert recipient (Ihor's personal N-iX mailbox) for a shared group alias once N-iX IT provisions one. One-line `envs/prod/terraform.tfvars` edit + `terraform apply`.
```

## 9. Consumers

The following tasks and agents rely on this contract. A breaking change to the schema above requires updating each of them in the same PR:

- **T04** Vertex client wrapper — reads `Quota requests` to size Interviewer + Assessor call patterns.
- **T21** Session cost ceiling — reads the `Quota requests` granted values to calibrate per-session throttles.
- **T42** Calibration batch sizing — reads both the granted rates and the smoke latency.
- **T48a** Concurrent-session smoke — reads the `Re-evaluation trigger` to decide whether to file `T01a-v2`.
- **`reviewer`** sub-agent — validates every PR that touches `docs/engineering/vertex-quota.md` against §§2–7.
