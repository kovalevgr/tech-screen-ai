# Feature Specification: Rubric snapshot (deep-copy on session start) (T15)

**Feature Branch**: `015-t15-rubric-snapshot`
**Created**: 2026-06-24
**Status**: Draft
**Input**: User description: "T15 — Rubric snapshot. Implement §4: freeze the active rubric tree into a self-contained JSON snapshot on the interview session, so the Assessor evaluates against the snapshot and rubric edits never change past sessions. Adds rubric_snapshot JSONB to interview_session (migration 0005), a snapshot_rubric() deep-copy function, a RubricSnapshot model + JSON-schema contract, and the §4 mutation test."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A session's assessment basis is frozen at start (Priority: P1)

When an interview begins, the system captures the entire rubric (the structure of stacks, competency blocks, competencies, topics, and proficiency levels) that is active at that moment and stores it as part of the session. From then on, everything that scores or reviews that session reads this captured copy — not the live, evolving rubric.

**Why this priority**: This is constitution §4 — the single most important guarantee for auditability and fair re-review. Without it, improving a rubric later would silently rewrite the meaning of past assessments, making historical decisions indefensible and calibration meaningless. It is the whole feature.

**Independent Test**: Capture a snapshot of a known rubric version into a session; read it back and confirm it faithfully reproduces the full rubric structure (every stack, block, competency, topic, and level) as self-contained data.

**Acceptance Scenarios**:

1. **Given** a rubric version with stacks, competency blocks, competencies, topics, and levels, **When** a session captures a snapshot of that version, **Then** the stored snapshot contains the complete structure with all names/descriptors/ranks copied in, and records which rubric version it came from.
2. **Given** a stored snapshot, **When** it is read back, **Then** it is fully self-contained — it does not depend on or point into the live rubric tables to be interpreted.

---

### User Story 2 - A later rubric edit never changes a running or past session (Priority: P1)

After a session has captured its snapshot, the rubric can keep evolving — names corrected, competencies added, a brand-new rubric version published. None of that may alter what an already-started session is assessed against.

**Why this priority**: This is the observable, testable heart of §4 ("rubric edits never retroactively change old sessions"). Equal priority to US1 — capturing the snapshot is only valuable if it is truly immutable against later edits.

**Independent Test**: Capture a snapshot into a session; then mutate the live rubric (rename a stack, add a competency, create a newer version); re-read the session's snapshot and confirm it is byte-for-byte unchanged.

**Acceptance Scenarios**:

1. **Given** a session with a captured snapshot of version V, **When** a stack in the live tree is renamed, **Then** the session's snapshot is unchanged.
2. **Given** the same session, **When** a new competency is added to the live tree (or a newer rubric version is created), **Then** the session's snapshot is unchanged.
3. **Given** the same session, **When** the snapshot is read after all those edits, **Then** it still reflects the rubric exactly as it was at capture time.

### Edge Cases

- **Empty / partial tree**: Snapshotting a version that has stacks but no competencies (or competencies without topics/levels) produces a structurally valid snapshot with empty child collections, not an error.
- **Unknown version**: Requesting a snapshot of a rubric version id that does not exist is rejected with a clear error; no empty snapshot is silently produced.
- **Placeholder sessions before T28**: The session table predates real session creation (that is T28). Existing placeholder/test rows that do not go through the capture path must remain insertable (see Assumptions — the snapshot column's default).
- **Snapshot is read-only**: Nothing in this feature mutates a stored snapshot after capture; corrections live elsewhere (§3), not by editing the snapshot.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST be able to produce a snapshot of a given rubric version that deep-copies the full tree — stack → competency block → competency → {topic, level} — into a single self-contained structure.
- **FR-002**: The snapshot MUST carry copied values (names, descriptors, level ranks, ordering) and the source rubric-version identifier for provenance, and MUST NOT rely on references into the live rubric tables to be interpreted later.
- **FR-003**: Every interview session MUST carry a rubric snapshot (the session's assessment basis is never absent) — see Assumptions for how this is satisfied for pre-existing placeholder rows.
- **FR-004**: Once captured onto a session, the snapshot MUST be immutable with respect to subsequent rubric edits: renaming, adding, or removing live rubric nodes, or publishing a new rubric version, MUST NOT change any existing session's stored snapshot.
- **FR-005**: Requesting a snapshot of a non-existent rubric version MUST fail with a specific error rather than producing an empty or partial snapshot.
- **FR-006**: The snapshot's structure MUST be described by a committed contract so downstream consumers (the Assessor, reviewer tooling) can read it without inspecting producer internals.
- **FR-007**: Adding the snapshot storage MUST be a forward-only, additive change that applies cleanly and keeps existing data and inserts working (no destructive change, no downtime).

### Key Entities *(include if feature involves data)*

- **Rubric snapshot**: A frozen, self-contained copy of a rubric version's full tree, attached to a session. Holds the source rubric-version id plus the nested stacks → competency blocks → competencies → {topics, levels}, each with their copied display values and ordering. Read-only after capture.
- **Interview session** *(existing placeholder)*: Gains the stored rubric snapshot as the assessment basis for that session. (Other session columns — candidate, status, lifecycle — are owned by later tiers.)
- **Rubric tree** *(existing, T08 — stack / competency_block / competency / topic / level)*: The live source the snapshot is copied **from**; never referenced **by** the snapshot after capture.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A snapshot of a rubric version reproduces 100% of that version's stacks, competency blocks, competencies, topics, and levels, verified against the source in an automated test.
- **SC-002**: After a session's snapshot is captured, an automated test mutating the live rubric (rename + add + new version) shows zero change to the session's stored snapshot — the §4 invariant holds.
- **SC-003**: The snapshot is provably self-contained: reading it requires no access to the live rubric tables (verified by structure, not by a live join).
- **SC-004**: The storage change applies cleanly on a fresh database and renders only additive change — verified automatically — and the existing test baseline stays green.
- **SC-005**: A downstream consumer can determine the snapshot's full shape from the committed contract alone, which validates a good snapshot and rejects a malformed one.

## Assumptions

- **NOT-NULL via a transitional default (key decision)**: Constitution §4 requires `interview_session.rubric_snapshot` to be NOT NULL. Real sessions populate it through the capture path; but real session creation is T28 (Tier 5) and the table already exists as a placeholder with rows that are inserted without a snapshot (e.g. the T05 test seed). To satisfy NOT NULL additively and keep those inserts working, the column is added **NOT NULL with a transitional empty-object default** (the same pattern T12 used for `title`/`level`). The default is only ever seen by placeholder/test rows; every real session gets a real snapshot at capture time. If the team prefers a strictly nullable column until T28 instead, that is the alternative — flag at the gate.
- **Capture is a function, not an endpoint, in T15**: T15 lands the snapshot *mechanism* (the column, the deep-copy function, a small helper to freeze a snapshot onto a session, the contract) and proves §4 with tests. The session-creation flow that calls it on a real "session start" is T28; the Assessor that reads it is Tier 3.
- **Snapshot format is internal JSON**: The snapshot is stored as structured JSON on the session; its shape is the committed contract. It mirrors the rubric tree shape (T08) minus version-management fields.
- **No change to the rubric tables**: T15 reads the rubric tree; it does not alter stack/competency/etc. or create a new rubric version.
- **Active-version selection is upstream**: "the active rubric version" is chosen by the caller (the session-start flow, T28) and passed to the snapshot function; T15 snapshots whatever version id it is given.

## Dependencies

- **T08** (rubric tree — merged): provides the stack/competency_block/competency/topic/level tables the snapshot copies from.
- **T12** (position template — merged): completes Tier-2's session-adjacent schema; T15 is the other half of Tier 2 (snapshotting). Satisfied.

## Out of Scope

- The session-creation endpoint / magic-link / "session start" trigger — **T28** (Tier 5).
- The Assessor that consumes the snapshot at runtime — **Tier 3**.
- Any change to the rubric authoring/import path or rubric versioning — **T08 / T16**.
- Reviewer corrections (those are append-only rows, §3) — not edits to the snapshot.
