# Research: Rubric snapshot (deep-copy on session start) (T15)

Phase 0 decisions.

## §1 — `rubric_snapshot` is NOT NULL with a transitional `'{}'::jsonb` default

- **Decision**: `ALTER TABLE interview_session ADD COLUMN rubric_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb` in `0005`. The ORM column is `Mapped[dict[str, Any]]` (`JSONB`, `nullable=False`, `server_default=text("'{}'::jsonb")`).
- **Rationale**: §4 mandates NOT NULL. `interview_session` already exists (T05) and is inserted without a snapshot by the T05 seed; real session creation (which calls the capture path) is T28. The transitional default keeps existing/placeholder inserts working and is zero-downtime — exactly the T12 precedent (`title`/`level`). Only placeholder/test rows ever see `'{}'`; every real session gets a real snapshot via `freeze_session_rubric`.
- **Alternatives considered**: (a) nullable until T28 — rejected (weakens §4 now, and the user confirmed the transitional-default approach at the spec gate); (b) NOT NULL with no default + backfill — rejected (breaks the seed's `INSERT INTO interview_session (position_template_id)`).

## §2 — Snapshot shape: self-contained values + source ids for correlation

- **Decision**: `RubricSnapshot` mirrors the T08 tree, copying display values **and** the source node ids as plain values (not FKs):
  - `RubricSnapshot{ rubric_tree_version_id, label, stacks[] }`
  - `SnapshotStack{ id, name, competency_blocks[] }`
  - `SnapshotCompetencyBlock{ id, name, position, competencies[] }`
  - `SnapshotCompetency{ id, name, topics[], levels[] }`
  - `SnapshotTopic{ id, name }`
  - `SnapshotLevel{ id, rank, descriptor }`
- **Rationale**: The snapshot must be interpretable without joining the live tables (FR-002), so all display values are copied. The source ids are kept **as values** (not foreign keys) for provenance and so the Assessor (Tier 3) can correlate a score back to a `competency` — `assessment.competency_id` references the live `competency`, which is stable under rubric versioning (new versions are added, nodes are not edited in place, §4/ADR-018). Storing an id as a value does not make the snapshot depend on the live row to be *read*.
- **Alternatives considered**: (a) drop all ids, keep only names — rejected (the Assessor needs the competency id to write `assessment` rows); (b) keep live FKs — rejected (violates self-containment / §4).

## §3 — Deep copy via AsyncConnection + Core SQL; deterministic ordering

- **Decision**: `snapshot_rubric(conn: AsyncConnection, rubric_tree_version_id)` issues a small set of `SELECT`s (one per level, filtered by `rubric_tree_version_id`, ordered deterministically) and assembles the nested model in Python. Ordering: stacks by `name`, competency_blocks by `position` then `name`, competencies by `name`, topics by `name`, levels by `rank`. Raise `RubricSnapshotError` if the version has no `rubric_tree_version` row (FR-005).
- **Rationale**: Matches the rubric read style in `tests/db` and the T12 validator (Core SQL over `AsyncConnection`), and keeps the producer ORM-independent. Deterministic ordering makes the stored JSON stable (so the §4 "unchanged" assertion is exact and diffs are meaningful).
- **Alternatives considered**: (a) one big join — rejected (awkward to assemble the nested shape; per-level selects are clearer); (b) ORM relationship loading — rejected (no relationships defined on the rubric models; async lazy-load friction).

## §4 — `freeze_session_rubric` writes the snapshot as JSONB

- **Decision**: `freeze_session_rubric(conn, interview_session_id, rubric_tree_version_id)` calls `snapshot_rubric`, then `UPDATE interview_session SET rubric_snapshot = :snap WHERE id = :sid` with `snap = snapshot.model_dump(mode="json")` (JSON-mode so uuids/enums serialize to JSON scalars). Returns the `RubricSnapshot`. T28 will call this at real session start; T15 exercises it directly.
- **Rationale**: One write, in the caller's transaction. `model_dump(mode="json")` produces a dict asyncpg/SQLAlchemy stores into JSONB cleanly and that round-trips to the committed contract.
- **Alternatives considered**: setting the column at INSERT time — that path is T28's; T15's helper updates an existing session so it is independently testable now.

## §5 — The §4 immutability test

- **Decision**: Seed rubric version V (stack/block/competency/topic/level); `freeze_session_rubric` into a session; capture the stored JSON; then mutate the live tree three ways — rename a stack, insert a new competency, and create a newer `rubric_tree_version` — and re-read the session's `rubric_snapshot`; assert it equals the captured JSON exactly.
- **Rationale**: This is the observable heart of §4 (SC-002). Because the snapshot is copied values in a JSONB blob with no live FK, it is structurally immune; the test makes that guarantee explicit and regression-proof.

## Open follow-ups (out of T15 scope)

- The real "session start" that calls `freeze_session_rubric` — **T28** (Tier 5).
- The Assessor reading the snapshot at runtime — **Tier 3**.
