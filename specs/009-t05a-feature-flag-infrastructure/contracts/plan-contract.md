# Plan-time Contract Pointer: T05a

This is a **pointer document**, not a contract. The actual contracts live at repo paths so they're discoverable by downstream tooling and consumers, not buried under `specs/`. Downstream tasks (any future consumer of `is_enabled`, plus T06 which fills the workflow's WIF binding) reference the runtime paths below.

## Runtime contracts

| Contract | Path | Owner | Notes |
| -------- | ---- | ----- | ----- |
| **YAML entry schema** | `docs/contracts/feature-flag.schema.json` | T05a | JSON Schema draft 2020-12 with conditional `if/then/else` for the sunset-required-fields rule (research §9). Validated on every commit by the registration hook and by the GHA sync workflow (defence in depth, FR-006). |
| **Database schema** | `alembic/versions/0002_feature_flags.py` | T05a | The runtime contract for the `feature_flag` table — column shape, the AFTER trigger emitting `pg_notify('feature_flag_changed', …)`, the GRANTs to both roles, and (by deliberate omission, FR-013) the absence of the `reject_audit_mutation()` trigger and the `REVOKE UPDATE, DELETE`. |
| **Consumer surface** | `app/backend/services/feature_flags.py` | T05a | The Python contract every consumer imports: `async def is_enabled(name: str, *, session_id: UUID \| None = None) -> bool` and `class UnknownFeatureFlag(Exception)`. The signature is forward-compatible — `session_id` exists for future per-session overrides but is unused at MVP. |
| **Source-of-truth YAML** | `configs/feature-flags.yaml` | T05a (ongoing — every flag-touching PR appends/edits) | The Git-tracked declaration of every flag the project has ever had. Sunset entries remain forever (FR-011). |
| **Human-readable index** | `docs/engineering/feature-flags.md` | T05a (ongoing) | One row per flag in either Active or Sunset table. Updated by every PR that adds, flips lifecycle, or sunsets a flag. |
| **Registration hook** | `scripts/check-feature-flag-registration.py` | T05a | The bidirectional consistency guard between the four files above. Exit-zero on clean tree; exit-non-zero with a precise message on any FR-010 / FR-011 violation. Runs locally via pre-commit and in CI via the test image (in-image since T05's `COPY scripts ./scripts`). |
| **Sync workflow** | `.github/workflows/sync-feature-flags.yml` | T05a (mechanism) / T06 (WIF live binding) | On `push` to `main` with a YAML change, upserts each entry into the DB with `updated_by='configs-as-code'` and emits warning annotations for orphan rows. T05a ships the structure; T06 fills `<TODO-T06: project/region/instance/service-account>` placeholders. |

## T06 boundary (called out explicitly)

`.github/workflows/sync-feature-flags.yml` contains explicit `<TODO-T06: …>` placeholders for:
- the WIF identity provider (`workload_identity_provider`),
- the Google service account to impersonate (`service_account`),
- the Cloud SQL instance connection (`project`, `region`, `instance`).

These cannot be filled in T05a because the Cloud SQL instance does not yet exist — provisioning it is T06's job. T05a's PR therefore ships the workflow file with the placeholders **and** an `if:` guard that prevents the upsert step from running when any placeholder is unresolved. The workflow file is itself valid YAML and passes `actionlint`; only the production-deploy path stays inert until T06 lands the bindings.

## Test contracts (referenced by `tasks.md`)

| Test | What it locks in | Spec ref |
| ---- | ---------------- | ------- |
| `test_feature_flag_table.py` | `feature_flag` table exists; **no** `reject_audit_mutation` trigger; **no** `REVOKE UPDATE/DELETE` from `techscreen_app`; `UPDATE feature_flag` from `techscreen_app` succeeds | SC-009 + FR-013 |
| `test_feature_flags.py` (service) | End-to-end on live Postgres: declare/load/read/flip-via-UPDATE; invalidation within 1 s; unknown name → `UnknownFeatureFlag`; listener reconnect after forced drop | SC-003 + FR-004 + research §7 |
| `test_feature_flag_registration.py` (hook) | Five fixture failure modes (undeclared name; removed-last-call without sunset; sunset entry deleted; schema-violating YAML; orphan docs row) each exit non-zero with the right error message | SC-006 + FR-010 + FR-011 |
