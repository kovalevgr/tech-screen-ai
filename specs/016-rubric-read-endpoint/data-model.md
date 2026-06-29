# Data Model: Rubric read endpoint

**No schema change, no migration, no new persisted entity.** Reuses the T08
rubric tree and the T15 `RubricSnapshot` shape.

## Reused

- **`rubric_tree_version`** (T08): `is_active` selects the version to read.
- **`stack` / `competency_block` / `competency` / `topic` / `level`** (T08): the tree, read by `snapshot_rubric`.
- **`RubricSnapshot`** (T15, `schemas/rubric_snapshot.py`) + **`docs/contracts/rubric-snapshot.schema.json`**: the response shape + committed contract.
- **Auth seam** (T13, `api/deps.py`): `get_current_user` + `require_roles("recruiter","admin")`.

## New — service helper

| Function | Signature | Behaviour |
| --- | --- | --- |
| `get_active_rubric_snapshot` | `(conn) -> RubricSnapshot \| None` | `SELECT id FROM rubric_tree_version WHERE is_active = true LIMIT 1`; if none → `None`; else `snapshot_rubric(conn, id)`. |

## Endpoint flow

| Verb / path | Flow | Status |
| --- | --- | --- |
| `GET /rubric/active` | `require_roles` → `get_active_rubric_snapshot(await session.connection())` → 404 if `None`, else 200 `RubricSnapshot` | 200 / 404 / 401 / 403 |

## Invariant → FR / SC

| Rule | FR / SC |
| --- | --- |
| Returns active version's full tree | FR-001/002, SC-001 |
| 404 when no active version | FR-003, SC-002 |
| recruiter/admin only (401/403) | FR-004, SC-002 |
| read-only (no edits) | FR-005 |
| contract committed + no drift | FR-006, SC-003/004 |
