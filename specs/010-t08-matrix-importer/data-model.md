# Phase 1 Data Model: T08 — Matrix importer

T08 introduces no new tables. It modifies one existing column-set (adds `payload_hash` to `rubric_tree_version`) and ships two new content artefacts (the YAML schema + the matrix-format contract). This document enumerates the design-altitude entities involved.

---

## 1. `rubric_tree_version.payload_hash`  *(NEW column; additive migration 0003)*

| Column | Type | Notes |
| ------ | ---- | ----- |
| `payload_hash` | `TEXT NOT NULL DEFAULT ''` | SHA-256 hex (64 chars) of the canonical concatenated YAML payload that materialised this version. The DEFAULT covers transitional pre-T08 rows (research §10) — at T08-time the table is empty in prod, but the default is defensive. |

**Constraints**:
- `UNIQUE (payload_hash)` — two YAML payloads with the same hash cannot produce two distinct versions. Combined with the advisory lock (data-model §4), this gives the idempotency guarantee from FR-007 / SC-003.

**Lifecycle**:
- Populated only by the importer's seed path. Never updated. Old rows keep their original hash forever.
- The hash recipe (research §3) is documented in `docs/contracts/matrix-format.md` so future loaders / replay tools can verify the relationship without reading code.

**Cross-reference**: T05's `rubric_tree_version` had `label`, `is_active`, `created_at`. T08 keeps all of those; the `label` continues to carry a human-readable name (e.g. `"tree:abc12345"` where `abc12345` is the first 8 chars of the hash, chosen for readability), and `is_active` continues to mean "this is the version current sessions are snapshotted against". The hash is purely structural — for idempotency, not display.

---

## 2. YAML entry shape  *(file: `configs/rubric/<stack-id>.yaml`)*

Validated by `docs/contracts/rubric.schema.json` (JSON Schema draft 2020-12).

```yaml
# Top-level
version: int            # bumped on content change; documentation-only for the human, not used by the importer
retired: bool           # default false; flip to retire the whole stack
nodes:                  # array
  - id: snake_case.with.dots   # stable identifier; never renamed, never reused after retire
    label_uk: "..."             # candidate-facing; required when retired=false
    label_en: "..."             # internal; always required
    retired: bool               # default false
    parent: <other-node-id>     # optional; null for top-level (== competency_block)
    levels:                     # optional; present only on competency-leaf nodes
      - level: int 1..5
        label_uk: "..."
        descriptor_en: "..."     # required when the parent node is not retired
        evidence_examples_en: [str]
```

**Field-level rules** enforced by the schema:
- `id` matches `^[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)*$` — snake_case segments separated by dots. Lower-cased, ASCII, no spaces. Stable for the lifetime of the project.
- `label_uk` required when `retired=false` (§11 — candidate-facing UK).
- `label_en` always required (§11 — internal EN).
- `levels[*].descriptor_en` required on every level of an active competency.
- `levels[*].level` is unique within a node and must be in 1..5.

**Tree mapping to T05's DB tables**:
- Top-level nodes (`parent: null`) → `competency_block` rows.
- Nested non-leaf nodes → `competency` rows.
- Children of competency nodes (deeper nesting) → `topic` rows.
- `levels` arrays on competency-leaf nodes → `level` rows (linked to the competency).

The file's name (sans extension) maps to `stack.name`. One YAML file per stack.

---

## 3. `audit_log` row for `action='rubric.versioned'`  *(NEW write target; existing table)*

Every seed run that creates a new `rubric_tree_version` writes exactly one row:

| Column | Value | Notes |
| ------ | ----- | ----- |
| `id` | generated UUID | server default `gen_random_uuid()` |
| `actor_id` | `NULL` | system action (importer); no human actor |
| `action` | `'rubric.versioned'` | discriminator |
| `subject_hash` | the new `payload_hash` (64-char hex) | §15 — never PII; the hash is opaque |
| `ts` | `now()` | server default |

Per the §3 carve-out from T05a: `audit_log` is INSERT-only from the importer. The §3 append-only invariant remains intact — the importer never UPDATEs or DELETEs this table.

---

## 4. Advisory lock id

| Lock id | Held by | Released by |
| ------- | ------- | ----------- |
| `987654321` (int8) | `pg_advisory_xact_lock(987654321)` at the start of every seed transaction | implicit on COMMIT or ROLLBACK |

A single fixed constant means every seed run targets the same lock; two concurrent seeds serialise. The lock id is documented in `app/backend/services/rubric_importer.py` and in `docs/contracts/matrix-format.md` so future programmatic callers (T16 GHA workflow) can take the same lock if they bypass the service module.

---

## 5. Untouched tables

By design, T08 does not modify the following T05 / T05a schemas (other than the one additive column above):

- `stack`, `competency_block`, `competency`, `topic`, `level` — gain new rows per version; existing rows from prior versions are NEVER updated or deleted (§4 / ADR-018; SC-004).
- `user`, `position_template`, `interview_session`, `interview_plan` — untouched.
- The six §3 append-only audit tables (`turn_trace`, `assessment`, `assessment_correction`, `turn_annotation`, `audit_log`, `session_decision`) — only `audit_log` receives a new INSERT per new version; the other five are untouched.
- `feature_flag` — untouched (T05a domain).

---

## 6. Cross-reference to T05 / T05a / §3

- T05's data-model.md established the rubric-tree tables and the six §3 append-only tables.
- T05a's data-model.md established `feature_flag` as an explicit §3 carve-out.
- T08's design: the rubric-tree tables (`stack` / `competency_block` / `competency` / `topic` / `level`) are NOT in the §3 set; mutation **across versions** is the model. Immutability is achieved by versioning + the FR-008 invariant that prior-version rows are never touched. `audit_log` is in the §3 set and the importer respects it (INSERT-only).
