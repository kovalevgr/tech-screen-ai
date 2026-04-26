# TechScreen — Vertex AI Quota Log

**Status:** initial commit · **Region:** europe-west1 · **Source of truth:** this file

This is the single source of truth for TechScreen's Vertex AI quota state: what was requested, what GCP granted, when, and what must happen next. Every LLM-touching task downstream of T01a reads this file before provisioning a new workload.

The file conforms to the contract pinned at [`specs/003-vertex-quota-region/contracts/vertex-quota-log-format.md`](../../specs/003-vertex-quota-region/contracts/vertex-quota-log-format.md). Sections appear in the fixed order required by §2 of that contract; column and bullet schemas follow §3–§6. Append-only by convention — re-raises, denials, and scale-ups are new rows or bullets, never edits to earlier ones.

## Re-evaluation trigger

If projected or realised concurrent interview sessions exceed **20** — the Phase 2 threshold in [`docs/engineering/implementation-plan.md`](./implementation-plan.md) T01a — the `infra-engineer` (with the project owner) MUST raise a new Spec Kit feature named `T01a-v2` to request higher quota **before** that rollout, not after. Triggers sourced from constitution §12 and the original T01a description.

## Quota requests

| date | model | metric | default | requested | granted | case_id | requester | status | notes |
| ---- | ----- | ------ | ------- | --------- | ------- | ------- | --------- | ------ | ----- |
| <FILL-IN: YYYY-MM-DD> | gemini-2.5-flash | GenerateContentRequestsPerMinutePerProjectPerModel | <observed by T012> | 60 | | <filled by T013> | project-owner (Ihor) | pending | initial T01a request |
| <FILL-IN: YYYY-MM-DD> | gemini-2.5-pro | GenerateContentRequestsPerMinutePerProjectPerModel | <observed by T012> | 60 | | <filled by T013> | project-owner (Ihor) | pending | initial T01a request |

## Region verification

_(none yet — first bullet appended in Phase 3 once Vertex Model Garden availability is verified for `europe-west1`. The contract requires this section be present and ordered, but its contents are deferred until evidence exists.)_

## Smoke-test records

_(none yet — first bullet appended in Phase 6 once `infra/scripts/vertex-smoke.sh` executes against the granted quota. The contract requires this section be present and ordered, but its contents are deferred until evidence exists.)_

## Follow-ups

- Swap the MVP budget-alert recipient (Ihor's personal N-iX mailbox) for a shared group alias once N-iX IT provisions one. One-line `infra/terraform/terraform.tfvars` edit (`ops_email = "techscreen-alerts@n-ix.com"` or whatever the alias becomes) + `terraform apply`. No `iam.tf` change required.
