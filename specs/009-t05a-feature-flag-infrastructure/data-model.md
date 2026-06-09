# Phase 1 Data Model: T05a — Feature-flag infrastructure

Three structured entities ship in this PR: the runtime database table, the YAML entry, and the human-readable index document. None of them is in the constitution-§3 append-only set (FR-013) — the cross-reference to T05's data-model is at the bottom.

---

## `feature_flag` table  *(Lifecycle: **mutable** — explicit §3 carve-out, FR-013)*

| Column | Type | Notes |
| ------ | ---- | ----- |
| `name` | `TEXT PRIMARY KEY` | Snake-case identifier; conforms to `^[a-z][a-z0-9_]{2,63}$` (research §9). Same name appears verbatim in `configs/feature-flags.yaml` and at the `is_enabled("name")` call site. |
| `enabled` | `BOOLEAN NOT NULL DEFAULT false` | The runtime state. Default false satisfies §9 (dark-launch by default). |
| `owner` | `TEXT NOT NULL` | Free-form; conventionally a GitHub `@handle`. Carries accountability for the flag's lifecycle. |
| `default_value` | `JSONB` (nullable) | Reserved for future non-boolean payloads. Unused at MVP; the column exists so adding a payload later is a forward-only column addition, not a destructive change. |
| `updated_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | Updated by the trigger below on every mutation. |
| `updated_by` | `TEXT` (nullable) | Identifies the actor that last changed the row. Canonical values: `"configs-as-code"` (the sync workflow), or any human-set string for emergency SQL. The workflow uses `"configs-as-code"` so audit can distinguish PR-driven flips from direct-SQL emergency flips. |

**Constraints**:
- Primary key on `name` (uniqueness + index for the per-flag lookup).
- No foreign keys (the table is self-contained; consumers reference it by name only).
- No `reject_audit_mutation()` trigger and no `REVOKE UPDATE, DELETE` from `techscreen_app` — by intent (FR-013). The migration docstring and the `app/backend/db/models/feature_flag.py` docstring both call this carve-out out explicitly.

**Triggers**:
- A single `BEFORE UPDATE` trigger maintains `updated_at = now()` on every UPDATE (standard, harmless).
- An `AFTER INSERT OR UPDATE OR DELETE` trigger fires `pg_notify('feature_flag_changed', COALESCE(NEW.name, OLD.name))` — structural to FR-003 / SC-003 (the 1-second cache-invalidation SLO needs the DB itself to wake listeners; research §2).

**Grants**:
- `GRANT SELECT, INSERT, UPDATE, DELETE` to **both** `techscreen_app` and `techscreen_migrator`. The application role legitimately mutates this table on the emergency-disable path; distinct from the six audit tables where the app role is INSERT/SELECT only.

**Lifecycle**: rows are created and mutated by the sync workflow (`updated_by='configs-as-code'`) or by direct emergency SQL (`updated_by` set by the operator). Rows are **never auto-deleted** by the workflow (FR-009 — orphan detection emits a warning, not a delete). Manual DELETE is permitted but discouraged; a sunsetted flag's row is normally left in place forever, alongside its sunset YAML entry and its docs row, so the audit trail survives (FR-011).

---

## YAML entry  *(file: `configs/feature-flags.yaml`)*

The file is a list of entries under a top-level `flags:` key. The schema (research §9) is committed at `docs/contracts/feature-flag.schema.json` and enforced on every commit by `scripts/check-feature-flag-registration.py`.

| Field | Required | Type | Notes |
| ----- | -------- | ---- | ----- |
| `name` | always | string | Same regex as the DB column. The single source-of-truth identifier for the flag. |
| `owner` | always | string | Accountability handle, usually `@gh-username`. |
| `default` | always | boolean | The seed for `enabled` when the row is first created. After the first sync, the DB value diverges from this whenever an operator flips the runtime state; that's expected. |
| `description` | always | string | One short paragraph in English (§11) explaining what flipping the flag does. |
| `state` | always | enum | `"active"` (live flag, has at least one call site) or `"sunset"` (retired, no remaining call sites; documented for audit). |
| `default_value` | optional | any JSON | Mirrors the JSONB DB column; reserved. |
| `sunset_pr` | required when `state="sunset"` | string | GitHub PR back-reference (`#123`). |
| `sunset_date` | required when `state="sunset"` | string (date) | `YYYY-MM-DD`. |

**Lifecycle**:
- A flag enters the file with `state: active` and is added to the docs Active table.
- When the last in-code call site is removed, the same PR MUST flip the entry to `state: sunset`, fill `sunset_pr` + `sunset_date`, and add a Sunset row to the docs (FR-010b + FR-011, enforced by the hook).
- **A sunset entry stays in the file forever** (FR-011). Deleting it is a §1 audit violation and is rejected by the same hook.

---

## Human-readable index document  *(file: `docs/engineering/feature-flags.md`)*

Single document. Three sections in order:

### How-to

Four short procedural blocks: **Declare** (add to YAML + add call site), **Flip** (PR to YAML), **Sunset** (when removing the last call site), **Emergency disable** (direct SQL + post-hoc YAML/docs reconciliation). Together fit on one screen.

### Active flags

Markdown table with **at least** these columns: `name | owner | default | description`. One row per `state: active` YAML entry. The hook asserts a row exists for every active YAML entry.

### Sunset flags

Markdown table with **at least** these columns: `name | sunsetted in | date | description`. One row per `state: sunset` YAML entry. The hook asserts a row exists with non-empty `sunsetted in` (matching `sunset_pr`) and non-empty `date` (matching `sunset_date`). Rows persist forever (FR-011).

T05a ships the document skeleton with one demonstration sunset row (`name: example_demonstration`) so the format is concrete and the hook has a baseline to validate against. The matching YAML entry is also `state: sunset`.

---

## Cross-reference to T05's data-model

T05's `data-model.md` enumerates the constitution-§3 append-only set: `turn_trace`, `assessment`, `assessment_correction`, `turn_annotation`, `audit_log`, `session_decision`. **`feature_flag` is NOT in that set and is NOT a candidate to be added to it.** This is the FR-013 carve-out:

- The append-only set protects the audit history of a session's decisions. Flags are runtime knobs whose entire purpose is to be flipped; their history lives in (a) the `updated_at`/`updated_by` columns for the latest change, (b) git history of `configs/feature-flags.yaml` for the canonical PR-driven flips, and (c) the docs Sunset table for retired flags.
- A contributor reading this section in the future should NOT add the `reject_audit_mutation()` trigger or `REVOKE UPDATE, DELETE` on `feature_flag` "for consistency" with the audit tables — that would defeat the SC-007 emergency-disable path and break SC-009.

SC-009 (a positive test asserting `UPDATE feature_flag` from `techscreen_app` succeeds) is the runtime guard against this regression.
