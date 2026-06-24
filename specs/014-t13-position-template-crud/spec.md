# Feature Specification: Position Template CRUD endpoints (T13)

**Feature Branch**: `014-t13-position-template-crud`
**Created**: 2026-06-24
**Status**: Draft
**Input**: User description: "T13 — Position Template CRUD endpoints (Tier 2). POST/GET/PATCH/DELETE /position-templates building on T12's model/schemas/validator/contract. Soft-delete only; recruiter/admin authorization; archived excluded by default; regenerate openapi.yaml; integration tests on real Postgres."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A recruiter creates and retrieves a Position Template (Priority: P1)

A recruiter defines a role to interview for and saves it, then later opens it again to review or reuse it. The system persists the full definition (title, level, job description, selected stacks, selected competencies with their must-have flags) and returns it intact, rejecting invalid input before it is stored.

**Why this priority**: Create + read is the minimum viable slice — without it there is no way to author or reuse a template, and every other operation (edit, archive, the admin UI, the planner) depends on a template existing and being retrievable. It exercises the whole persistence + validation path end to end.

**Independent Test**: Issue a create request with a valid body and confirm it returns the stored template with an id; issue create requests with invalid bodies (bad level, unknown stack, must-have not in selected, competency not in a selected stack) and confirm each is rejected with a clear error and nothing is stored; fetch the created template by id and confirm a faithful round-trip.

**Acceptance Scenarios**:

1. **Given** an existing rubric with stacks and competencies, **When** a recruiter creates a template with a valid title, level, one stack and two competencies (one must-have), **Then** the template is stored and returned with a generated id and all fields intact.
2. **Given** a create request whose competency does not belong to any selected stack, **When** it is submitted, **Then** it is rejected with a specific error and no rows are written.
3. **Given** a stored template, **When** it is fetched by its id, **Then** the full template (stacks + competencies + must-have flags) is returned.
4. **Given** a non-existent id, **When** it is fetched, **Then** the response is "not found".

---

### User Story 2 - A recruiter lists, edits, and archives templates (Priority: P1)

A recruiter browses existing templates, edits one whose requirements changed, and archives ones no longer in use — without ever destroying the historical record (archived templates may still be referenced by past or in-flight sessions).

**Why this priority**: Equal to US1 — the list/edit/archive lifecycle is what makes templates usable day to day. Archiving (not deleting) is a hard data-integrity requirement carried over from T12 (FR-007) and the project's no-data-loss posture.

**Independent Test**: Create several templates; list them and confirm only active ones appear by default and archived ones appear only when explicitly requested; edit a template and confirm the change persists and re-validates; archive a template and confirm it disappears from the default list while the row (and its id) still exists.

**Acceptance Scenarios**:

1. **Given** active and archived templates, **When** the list is requested with no options, **Then** only active templates are returned.
2. **Given** the same data, **When** the list is requested including archived, **Then** both active and archived templates are returned.
3. **Given** a stored template, **When** a recruiter edits its title/level/selections, **Then** the change persists and the same validation rules apply (invalid edits are rejected).
4. **Given** a stored template, **When** a recruiter archives it, **Then** it is excluded from the default list but the row still exists and can be retrieved (including archived).
5. **Given** an already-archived or non-existent template, **When** archive is requested, **Then** the response is "not found" for a missing id (and archiving is safe/consistent for an already-archived one).

---

### User Story 3 - Only authorized staff manage templates (Priority: P2)

Position Templates are internal hiring configuration. Only staff with the `recruiter` or `admin` role may create, read, edit, or archive them; anyone else is refused.

**Why this priority**: Authorization protects hiring configuration, but the endpoints and their data behaviour (US1/US2) are the core deliverable; the role gate layers on top. P2 because the *enforcement seam* is built and tested here even though the real identity provider is wired later (T07).

**Independent Test**: With an injected `recruiter` or `admin` identity, every operation succeeds; with a non-privileged identity, every operation is refused with "forbidden"; with no identity, operations are refused as "unauthenticated".

**Acceptance Scenarios**:

1. **Given** a request authenticated as `recruiter` or `admin`, **When** any template operation is invoked, **Then** it is allowed (subject to validation).
2. **Given** a request authenticated as a non-privileged role, **When** any template operation is invoked, **Then** it is refused as forbidden.
3. **Given** an unauthenticated request, **When** any template operation is invoked, **Then** it is refused as unauthenticated.

### Edge Cases

- **Partial edit**: An edit that supplies only some fields updates those fields and leaves the rest unchanged; supplying a selection list replaces that selection set wholesale (it is not merged element-by-element).
- **Edit re-validation**: An edit that would make the template invalid (e.g., removes a stack a selected competency depended on, or a must-have left without its competency) is rejected, leaving the stored template unchanged.
- **Empty list**: Listing when no templates exist returns an empty collection, not an error.
- **Archived still referenced**: An archived template that an interview session points at remains retrievable; archiving never breaks that reference.
- **Double archive**: Archiving an already-archived template does not error and does not change the original archive time semantics in a surprising way.
- **Unknown id on read/edit/archive**: Returns "not found".

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST let an authorized user create a Position Template from a title, level, optional job description, a non-empty set of stacks, and a non-empty set of competencies with per-competency must-have flags, applying T12's stateless and stateful validation before storing it.
- **FR-002**: The system MUST return the created template, including its generated id and all selections, on successful creation.
- **FR-003**: The system MUST reject invalid create/edit input with a specific, field-identifying error and MUST NOT persist anything when validation fails (create is all-or-nothing).
- **FR-004**: The system MUST let an authorized user retrieve a single template by id, returning "not found" for an unknown id.
- **FR-005**: The system MUST let an authorized user list templates, **excluding archived templates by default** and including them only when explicitly requested.
- **FR-006**: The system MUST let an authorized user edit an existing template's fields and selections, re-applying the full validation rules; an invalid edit leaves the stored template unchanged.
- **FR-007**: The system MUST archive a template by setting its archive marker and MUST NEVER remove a template row (soft-delete only).
- **FR-008**: The system MUST restrict every template operation to users with the `recruiter` or `admin` role; non-privileged users are refused (forbidden) and unauthenticated requests are refused (unauthenticated).
- **FR-009**: The system MUST publish the template endpoints in the committed API contract document so downstream layers (the admin UI, T14) can generate a client from it, and the committed contract MUST stay in sync with the implemented endpoints (no drift).
- **FR-010**: Persisting a template and its selections MUST be atomic — a failure mid-write leaves no partial template.

### Key Entities *(include if feature involves data)*

- **Position Template** *(from T12)*: the role definition being created/read/edited/archived. Carries title, level, job description, archive marker, ownership, and timestamps.
- **Stack / Competency selections** *(from T12)*: the association rows linking a template to rubric stacks and competencies (with the must-have flag). Created/replaced as part of create/edit.
- **Acting user** *(role-bearing)*: the staff identity whose role (`recruiter`/`admin` vs other) determines whether an operation is permitted. The identity is established by the authentication seam; real identity-provider wiring is a separate task (T07).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All four operations (create, read, list, edit, archive) are covered by automated integration tests against a real database, all passing.
- **SC-002**: 100% of the validation rules reject their invalid inputs at the create and edit boundaries in tests, and valid inputs succeed.
- **SC-003**: Archived templates are absent from the default list and present in the include-archived list in tests — and no test (or operation) ever removes a template row.
- **SC-004**: Every operation is refused for a non-privileged identity and for an unauthenticated request, and allowed for `recruiter`/`admin`, verified in tests.
- **SC-005**: The committed API contract document contains the template endpoints and matches the implementation — verified automatically (zero drift).
- **SC-006**: A downstream client (T14) can be generated from the committed contract without reading backend source.

## Assumptions

- **Authentication seam, real SSO deferred (key design decision)**: T13 builds the authorization gate against a current-user dependency that resolves the acting staff identity and role. Because real SSO + role claims (T07) are blocked on a live GCP project and not yet available, this dependency is a seam: it is overridable so tests can inject a `recruiter`/`admin`/other/anonymous identity, and T07 later wires it to the real identity provider. T13 owns the *role-check enforcement*; T07 owns *who the user is*.
- **Authorization scope**: All template operations — including reads/list — require `recruiter` or `admin` (this is internal hiring configuration, not public data). If reads should be broader later, that is a separate change.
- **Edit semantics**: An edit replaces any selection set it provides wholesale (send the full desired set of stacks/competencies), and leaves omitted fields unchanged. This avoids ambiguous element-level merge semantics.
- **Archive semantics**: Archive sets the archive marker; it is idempotent in effect (an already-archived template stays archived). "Not found" is returned only for unknown ids.
- **Contract completion**: T13 adds the endpoint paths to the API contract document (the path-level contract T12 deferred under "Variant A"); the request/response shapes were already frozen by T12's schema.
- **No pagination at MVP**: The list returns all templates (optionally including archived). Pagination/filtering beyond `include_archived` is out of scope unless volume requires it later.
- **Persistence model**: Reuses T12's tables and validator; no schema change and no new migration in T13.

## Dependencies

- **T12** (Position Template schema + contract — merged): provides the ORM model + association tables, the request/response schemas, the stateful validator, and the JSON-schema contract this task exposes over HTTP. Satisfied.

## Out of Scope

- Position Template **admin UI** — T14 (consumes this API).
- Real **SSO / Identity Platform** wiring and role claims — T07 (blocked on a live GCP project). T13 builds only the overridable authorization seam.
- **Rubric snapshot** onto a session — T15.
- Pagination, full-text search, bulk operations, and template versioning/history.
