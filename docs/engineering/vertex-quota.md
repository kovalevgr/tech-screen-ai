# TechScreen — Vertex AI Quota Log

**Status:** initial commit · **Region:** europe-west1 · **Source of truth:** this file

This is the single source of truth for TechScreen's Vertex AI quota state: what was requested, what GCP granted, when, and what must happen next. Every LLM-touching task downstream of T01a reads this file before provisioning a new workload.

The file conforms to the contract pinned at [`specs/003-vertex-quota-region/contracts/vertex-quota-log-format.md`](../../specs/003-vertex-quota-region/contracts/vertex-quota-log-format.md). Sections appear in the fixed order required by §2 of that contract; column and bullet schemas follow §3–§6. Append-only by convention — re-raises, denials, and scale-ups are new rows or bullets, never edits to earlier ones.

## Re-evaluation trigger

If projected or realised concurrent interview sessions exceed **20** — the Phase 2 threshold in [`docs/engineering/implementation-plan.md`](./implementation-plan.md) T01a — the `infra-engineer` (with the project owner) MUST raise a new Spec Kit feature named `T01a-v2` to request higher quota **before** that rollout, not after. Triggers sourced from constitution §12 and the original T01a description.

## Quota observed defaults

| date | model | metric | scope | observed_default | floor | floor_met | source |
| ---- | ----- | ------ | ----- | ---------------- | ----- | --------- | ------ |
| 2026-04-26 | gemini-2.5-flash-ga | aiplatform.googleapis.com/global_generate_content_input_tokens_per_minute_per_base_model | global | 10000000000 TPM | 1000000 TPM | yes | `gcloud alpha services quota list --service=aiplatform.googleapis.com --consumer=projects/tech-screen-493720 --filter="metric=aiplatform.googleapis.com/global_generate_content_input_tokens_per_minute_per_base_model"` |
| 2026-04-26 | gemini-2.5-pro-ga | aiplatform.googleapis.com/global_generate_content_input_tokens_per_minute_per_base_model | global | 1000000000 TPM | 100000 TPM | yes | (same command as above) |

## Quota requests

| date | model | metric | default | requested | granted | case_id | requester | status | notes |
| ---- | ----- | ------ | ------- | --------- | ------- | ------- | --------- | ------ | ----- |

_(empty — per Clarifications 2026-04-26, no quota request was filed for 2.5 GA models because their TPM defaults exceed PoC need by ~5 orders of magnitude. See "Quota observed defaults" above. This table re-engages if any future model returns to RPM quotas or a TPM raise becomes necessary.)_

## Region verification

- 2026-04-26 — gemini-2.5-flash, gemini-2.5-pro, region=europe-west1 — verified via REST functional probe `POST https://europe-west1-aiplatform.googleapis.com/v1/projects/tech-screen-493720/locations/europe-west1/publishers/google/models/{model}:generateContent` (both returned HTTP 200 with valid `generateContent` payloads, `finishReason: MAX_TOKENS`, `promptTokenCount: 1`). Verified by project-owner (Ihor) via Owner-impersonation ADC token. Cost: ~$0.0000003.

## Smoke-test records

_(none yet — first bullet appended in Phase 6 once `infra/scripts/vertex-smoke.sh` executes against the granted quota. The contract requires this section be present and ordered, but its contents are deferred until evidence exists.)_

## Follow-ups

- Swap the MVP budget-alert recipient (Ihor's personal N-iX mailbox) for a shared group alias once N-iX IT provisions one. One-line `infra/terraform/terraform.tfvars` edit (`ops_email = "techscreen-alerts@n-ix.com"` or whatever the alias becomes) + `terraform apply`. No `iam.tf` change required.
