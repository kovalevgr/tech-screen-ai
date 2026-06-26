# Data Model: Rubric snapshot (T15)

Migration `0005_rubric_snapshot` (down_revision `0004_position_template`).
Additive: one `ADD COLUMN`. No change to the rubric tables.

## Column: `interview_session.rubric_snapshot` (NEW)

| Column | Type | Null | Default | Notes |
| --- | --- | --- | --- | --- |
| `rubric_snapshot` | `JSONB` | NOT NULL | `'{}'::jsonb` (transitional) | The frozen rubric for the session (§4). Real sessions overwrite the default via `freeze_session_rubric`. ORM: `Mapped[dict[str, Any]]`. |

Existing `interview_session` columns unchanged: `id`, `created_at`,
`position_template_id` (nullable FK → `position_template`).

## Frozen shape — `RubricSnapshot` (Pydantic → JSONB → §14 contract)

Mirrors the T08 tree; copies display values + source ids (as plain values, not
FKs). `extra="forbid"` on every model.

```
RubricSnapshot
  rubric_tree_version_id : uuid        # provenance (the source version)
  label                  : str         # the version label, copied
  stacks                 : [SnapshotStack]

SnapshotStack            { id: uuid, name: str, competency_blocks: [SnapshotCompetencyBlock] }
SnapshotCompetencyBlock  { id: uuid, name: str, position: int, competencies: [SnapshotCompetency] }
SnapshotCompetency       { id: uuid, name: str, topics: [SnapshotTopic], levels: [SnapshotLevel] }
SnapshotTopic            { id: uuid, name: str }
SnapshotLevel            { id: uuid, rank: int, descriptor: str }
```

Source columns (T08): `stack(name)`, `competency_block(name, position)`,
`competency(name)`, `topic(name)`, `level(rank, descriptor)`. Empty child
collections are valid (a stack with no competencies, etc.).

## Functions (service layer)

| Function | Signature | Behaviour |
| --- | --- | --- |
| `snapshot_rubric` | `(conn, rubric_tree_version_id) -> RubricSnapshot` | Deep-copy the whole tree for the version into the frozen shape (deterministic ordering). Raise `RubricSnapshotError` if the version row does not exist (FR-005). Reads only; no live FK retained in the output. |
| `freeze_session_rubric` | `(conn, interview_session_id, rubric_tree_version_id) -> RubricSnapshot` | Call `snapshot_rubric`, then `UPDATE interview_session SET rubric_snapshot = :snap WHERE id = :sid` with `snapshot.model_dump(mode="json")`. Returns the snapshot. |

Deterministic order: stacks by `name`; blocks by `position, name`;
competencies by `name`; topics by `name`; levels by `rank`.

## Invariant → FR / SC map

| Invariant | Layer | FR / SC |
| --- | --- | --- |
| Snapshot reproduces the full tree | snapshot_rubric + test | FR-001, SC-001 |
| Self-contained (copied values, no live FK) | shape (values + id-as-value) | FR-002, SC-003 |
| Every session carries a snapshot | NOT NULL + default | FR-003 |
| Rubric edit never changes a stored snapshot | JSONB blob + §4 test | FR-004, SC-002 |
| Unknown version → error | snapshot_rubric guard | FR-005 |
| Shape described by a committed contract | rubric-snapshot.schema.json | FR-006, SC-005 |
| Additive, clean migration | 0005 | FR-007, SC-004 |

## Migration downgrade

Symmetric dev-only downgrade (`DROP COLUMN IF EXISTS rubric_snapshot`).
Production is forward-only (§10). The `DROP` trips T10's whole-file
destructive-DDL detector → expected `needs-adr` false-positive (the **upgrade**
is additive); documented in the migration docstring, as in `0004`.
