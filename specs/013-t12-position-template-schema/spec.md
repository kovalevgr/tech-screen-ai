# Feature Specification: Position Template schema + contract (T12)

**Feature Branch**: `013-t12-position-template-schema`
**Created**: 2026-06-24
**Status**: Draft
**Input**: User description: "T12 — Position Template schema + contract (Tier 2). SQLAlchemy model `PositionTemplate` + migration, Pydantic request/response schemas, validation rules (stacks must exist, level enum, must-have ⊆ optional), JSON-schema contract + regenerated OpenAPI. Schema + contract ONLY; CRUD (T13), admin UI (T14), rubric snapshot (T15) are downstream."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A role definition is captured with integrity guarantees (Priority: P1)

A recruiter needs to describe the role they want to interview for: a title, the seniority level, the technology stack(s) involved, and the specific competencies the interview must cover — flagging which competencies are mandatory ("must-have") versus desirable. The system must hold this definition as a first-class, validated record so that everything built on top of it (interview planning, assessment, reporting) starts from trustworthy data.

**Why this priority**: This is the foundational data model for all of Tier 2. Nothing downstream (CRUD endpoints, admin UI, rubric snapshotting, the planner) can exist without a validated Position Template record. It is the MVP slice — a correct, constrained schema.

**Independent Test**: Construct a Position Template with valid data through the model + request schema and confirm it persists and round-trips. Then attempt each invalid combination (unknown level, a stack that does not exist, a must-have competency that is not among the selected competencies) and confirm each is rejected with a clear, specific error. No HTTP endpoint is needed for this test — the model, schema, and validation rules are exercisable directly.

**Acceptance Scenarios**:

1. **Given** an existing rubric tree with at least one stack and competencies, **When** a Position Template is created with a valid title, a level of `Middle`, one existing stack, three selected competencies of which one is flagged must-have, **Then** the record is accepted and persisted with all fields intact.
2. **Given** a create request whose `level` is `Architect`, **When** the template is validated, **Then** it is rejected because `level` must be one of {Junior, Middle, Senior, Tech Leader}.
3. **Given** a create request that references a stack id that is not present in the rubric, **When** the template is validated, **Then** it is rejected with an error identifying the unknown stack.
4. **Given** a create request whose must-have competency set contains a competency that is not in the selected/optional competency set, **When** the template is validated, **Then** it is rejected because must-have competencies must be a subset of the selected competencies.

---

### User Story 2 - Downstream layers build against a committed contract (Priority: P1)

The CRUD endpoints (T13) and the admin UI (T14) are separate, parallelisable tasks. They must be able to start work against a frozen, committed contract for the Position Template — its field names, types, allowed values, and request/response shapes — without reading the backend implementation, and without the contract drifting from the code.

**Why this priority**: Constitution §14 forbids parallel cross-layer work without a committed contract. T12 exists precisely to publish that contract so T13 and T14 can fan out. Equal priority to US1 because the schema is only useful to the rest of Tier 2 once its contract is published.

**Independent Test**: Confirm the JSON-schema contract file and the regenerated OpenAPI document both exist, are valid, and describe the same Position Template shape that the backend schemas enforce (the OpenAPI regeneration check passes byte-for-byte; the JSON schema validates a known-good example and rejects a known-bad one).

**Acceptance Scenarios**:

1. **Given** the finished schema, **When** the OpenAPI document is regenerated, **Then** the diff is clean and committed in the same change as the model/schema (no uncommitted drift).
2. **Given** the contract files, **When** a reviewer inspects the change, **Then** the JSON-schema contract file and the OpenAPI document appear changed together with the model.
3. **Given** the published JSON schema, **When** a valid Position Template example is validated against it, **Then** it passes; **When** an example with an invalid level is validated, **Then** it fails.

---

### User Story 3 - The schema change is forward-only and auditable (Priority: P2)

The Position Template table already exists as a minimal placeholder. T12 extends it. The change must be a forward-only, additive, zero-downtime migration with no destructive DDL, and deletion of a template must be a soft archive (never a row removal), so the historical record and any future references stay intact.

**Why this priority**: Constitution §10 (forward-only, zero-downtime migrations) and the project's append-only / no-data-loss posture are non-negotiable, but they constrain *how* US1/US2 land rather than adding new user-visible capability — hence P2.

**Independent Test**: Apply the migration on a clean test database and confirm it succeeds; inspect the rendered DDL and confirm it only adds columns/tables (no DROP/ALTER TYPE); confirm a soft-delete marker (`archived_at`) exists and that "deletion" is expressed as setting it rather than removing the row.

**Acceptance Scenarios**:

1. **Given** a database at the current head revision, **When** the T12 migration is applied, **Then** it upgrades cleanly and the new columns/association tables are present.
2. **Given** the migration, **When** its SQL is rendered, **Then** it contains only additive DDL (no `DROP COLUMN`, `DROP TABLE`, or `ALTER COLUMN ... TYPE`), so it needs no destructive-DDL ADR.
3. **Given** a persisted template, **When** it is archived, **Then** the row remains and `archived_at` is set.

### Edge Cases

- **Empty competency selection**: A template with zero selected competencies — rejected (a template must assess at least one competency) or allowed as a draft? Default: at least one selected competency is required for a valid template.
- **Duplicate selections**: The same stack or the same competency listed twice in one request — de-duplicated / rejected as malformed input.
- **Cross-stack competency**: A selected competency that does not belong to any of the template's selected stacks — flagged as invalid (the competency must belong to a selected stack).
- **Stale rubric reference**: A selected competency/stack belongs to a rubric tree version that is later superseded — out of scope for T12 (immutable snapshotting is T15); the template references rubric nodes by id and validity is checked at authoring time.
- **Archived template referenced elsewhere**: An archived template that an interview session still points at — archiving must not break the existing foreign key (soft-delete preserves the row).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST extend the existing `position_template` record so it can hold: a human-readable title/name, an optional job-description text, a seniority level, one or more referenced technology stacks, and a set of selected competencies each marked as must-have or nice-to-have.
- **FR-002**: The system MUST constrain `level` to exactly one of {Junior, Middle, Senior, Tech Leader} and reject any other value.
- **FR-003**: The system MUST reject a Position Template that references a stack which does not exist in the rubric.
- **FR-004**: The system MUST reject a Position Template whose must-have competency set is not a subset of its selected (optional) competency set.
- **FR-005**: The system MUST require at least one selected competency for a template to be valid.
- **FR-006**: The system MUST reject a selected competency that does not belong to one of the template's selected stacks.
- **FR-007**: The system MUST express deletion as a soft archive (an `archived_at` timestamp) and MUST NOT remove template rows.
- **FR-008**: The system MUST provide request and response data shapes for a Position Template (create/read), with validation applied at the boundary so invalid input is rejected before persistence.
- **FR-009**: The system MUST publish a committed JSON-schema contract describing the Position Template shape, and MUST regenerate the API contract document (OpenAPI) describing the Position Template endpoints' shapes, both committed together with the model in the same change (§14).
- **FR-010**: The schema change MUST be a forward-only, additive migration with no destructive DDL, and MUST apply cleanly from the current head revision on the test database (§10).
- **FR-011**: Validation error messages MUST identify the specific rule violated (which field, which unknown id, which subset breach) so callers can correct input.
- **FR-012**: The Position Template MUST record authorship/ownership sufficient to later enforce that only `recruiter` or `admin` roles manage templates (the authorization enforcement itself is T13; T12 lands the column/relationship it needs).

### Key Entities *(include if feature involves data)*

- **Position Template**: The recruiter-authored definition of a role to interview for. Attributes: title/name, optional job-description text, seniority level (enum), soft-delete marker (`archived_at`), authorship/ownership reference, creation timestamp. Relationships: selects one or more Stacks; selects one or more Competencies (each flagged must-have / nice-to-have).
- **Stack** *(existing — rubric tree)*: A top-level technology area (e.g. "Backend Python"), version-scoped within a rubric tree version. Referenced by a Position Template; must exist.
- **Competency** *(existing — rubric tree)*: A scored competency within a stack's competency block, version-scoped. Selected by a Position Template; must belong to one of the template's selected stacks.
- **Position Template ↔ Stack selection**: The link expressing which stacks a template covers.
- **Position Template ↔ Competency selection**: The link expressing which competencies a template assesses, carrying the must-have / nice-to-have flag.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A recruiter's complete role definition (title, level, stacks, competencies, must-have flags) can be captured in a single Position Template record with zero data loss on round-trip.
- **SC-002**: 100% of the four validation rules (level enum, stack existence, must-have ⊆ selected, competency-belongs-to-stack) reject their respective invalid inputs in automated tests, and accept valid inputs.
- **SC-003**: The API contract document regenerates with a clean diff — a contributor can verify zero drift between the published contract and the implemented schema in one automated check.
- **SC-004**: A downstream team (T13/T14) can determine every field name, type, and allowed value of a Position Template from the committed contract files alone, without reading backend source.
- **SC-005**: The migration applies cleanly on a fresh database and renders only additive DDL — verified automatically — so it requires no destructive-DDL ADR and no downtime.

## Assumptions

- **Rubric reference model**: A Position Template references rubric `stack` and `competency` rows by id. Those rows are version-scoped (each belongs to a `rubric_tree_version`); T12 validates existence at authoring time only. Immutable per-session snapshotting of the rubric is explicitly T15 and out of scope here — editing a template later does not retroactively change any session (§4 is satisfied by T15's snapshot, not by T12).
- **Level is a fixed enum, not a rubric `level` row**: The Position Template `level` ({Junior, Middle, Senior, Tech Leader}) is the role's target seniority and is distinct from the rubric tree's per-competency `level` proficiency rows. They are not the same concept.
- **Edit semantics**: `position_template` is not an audit table, so normal updates to a template are allowed (recruiters revise role definitions). Append-only (§3) applies to audit tables, not to this configuration table.
- **Authorship column**: Ownership is stored as a reference to the existing `user` table (nullable for now); role-based authorization enforcement is deferred to T13.
- **Multiplicity**: A template may cover one or more stacks and selects one or more competencies; selections are modelled as association rows, not embedded blobs, so referential integrity (FR-003/FR-006) is enforceable at the database and validation layers.
- **No seed data / endpoints**: T12 lands the schema, validation, and contract only. No CRUD endpoints, no admin UI, no fixtures beyond what tests need.

## Dependencies

- **T08** (rubric matrix importer — merged): provides the `stack` and `competency` tables a template references. Satisfied.
- **T05** (DB schema v0 — merged): created the `position_template` placeholder table and the `interview_session.position_template_id` FK this task builds on. Satisfied.

## Out of Scope

- CRUD endpoints for Position Templates (`POST/GET/PATCH/DELETE`) — **T13**.
- Position Template admin UI — **T14**.
- Rubric snapshotting onto a session (`rubric_snapshot`) — **T15**.
- Role-based authorization enforcement (recruiter/admin) — **T13** (T12 only lands the ownership column).
