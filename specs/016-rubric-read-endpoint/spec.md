# Feature Specification: Rubric read endpoint

**Feature Branch**: `016-rubric-read-endpoint`
**Created**: 2026-06-24
**Status**: Draft
**Input**: User description: "A read-only HTTP endpoint that returns the active rubric version's full tree (stack → competency_block → competency → {topic, level}). Prerequisite for T14's form pickers; reuses T15's snapshot_rubric; matches the committed rubric-snapshot contract. recruiter/admin auth; 404 when no active version."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Staff tooling can read the current rubric (Priority: P1)

A recruiter (through the admin tooling) needs to see the rubric that is currently in force — its stacks, competency blocks, competencies, topics, and proficiency levels — so they can choose from it when defining a Position Template, and so it can be browsed read-only. The rubric is authored in Git and imported into the system; this gives the UI a way to read the active version over the network.

**Why this priority**: It is the unblocking dependency for the Position Template admin UI (T14): without a way to read the available stacks and competencies, the create/edit form cannot present meaningful choices. It is the whole feature.

**Independent Test**: With an active rubric version seeded, request the active rubric and confirm the response reproduces its full tree (every stack/block/competency/topic/level with names and ids). With no active version, confirm a clear "not found" response. With a non-privileged or unauthenticated caller, confirm the request is refused.

**Acceptance Scenarios**:

1. **Given** an active rubric version with a populated tree, **When** an authorized recruiter requests the active rubric, **Then** the full tree is returned in the same shape as a session's rubric snapshot.
2. **Given** no rubric version is marked active, **When** the active rubric is requested, **Then** the response is "not found".
3. **Given** a caller without the recruiter/admin role, **When** the active rubric is requested, **Then** it is refused (forbidden); an unauthenticated caller is refused as unauthenticated.

### Edge Cases

- **Empty active version**: An active version that has stacks but no competencies (or competencies without topics/levels) returns a structurally valid tree with empty child collections, not an error.
- **No active version**: Returns "not found" (never an empty/ambiguous body).
- **At most one active version**: The app maintains a single active version; the endpoint returns that one. (If more than one were somehow active, it returns a single deterministic result rather than erroring — but this is not an expected state.)
- **Read-only**: This endpoint never edits the rubric; rubric changes happen through the Git/YAML import path, never the API.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST expose a read-only way to retrieve the **active** rubric version's full tree (stack → competency block → competency → {topic, level}) with each node's id and display values.
- **FR-002**: The response MUST use the same committed shape as a session's rubric snapshot, so existing consumers and contracts are reused.
- **FR-003**: The system MUST return "not found" when no rubric version is active, rather than an empty or partial body.
- **FR-004**: The endpoint MUST be restricted to the `recruiter` or `admin` role; non-privileged callers are refused (forbidden) and unauthenticated callers are refused (unauthenticated).
- **FR-005**: The endpoint MUST be read-only — it never creates, edits, or deletes rubric data.
- **FR-006**: The committed API contract MUST include this endpoint so the admin UI (T14) can generate its client from it, and the committed contract MUST stay in sync with the implementation (no drift).

### Key Entities *(include if feature involves data)*

- **Active rubric version** *(existing — T08 rubric tree)*: the `rubric_tree_version` currently marked active, and its descendant stacks/blocks/competencies/topics/levels. Read-only here.
- **Rubric tree response** *(existing shape — T15)*: the self-contained tree structure, identical to the rubric snapshot shape (the same committed contract).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Requesting the active rubric returns 100% of the active version's stacks, competency blocks, competencies, topics, and levels, verified in an automated test.
- **SC-002**: With no active version, the request returns "not found" (verified); with a non-privileged caller it is forbidden and unauthenticated it is unauthorized (verified).
- **SC-003**: The committed API contract contains the endpoint and matches the implementation — verified automatically (zero drift) — and the existing test baseline stays green.
- **SC-004**: A downstream client (T14) can be generated from the committed contract and obtain the rubric tree without reading backend source.

## Assumptions

- **Response shape reuses the rubric-snapshot contract**: The active-rubric tree is identical in shape to a session's frozen snapshot (T15), so the response reuses that committed contract rather than introducing a new one. (Naming/aliasing is a plan-level detail.)
- **"Active" = the single `is_active` version**: The rubric tree carries an `is_active` flag; the app maintains at most one active version. The endpoint returns that version's tree.
- **No feature flag**: This is a read-only view of internal config (low risk), so it is not placed behind a §9 dark-launch flag — to be confirmed at the plan gate.
- **Authorization reuses the existing seam**: The recruiter/admin gate reuses the dependency seam from T13; real SSO is still T07 (the seam is overridable in tests).
- **No schema change**: Reuses the existing rubric tables and the T15 snapshot function; no migration.
- **Endpoint shape leaves room to grow**: A future per-version browse endpoint (for the Rubric Browser screen) can be added later; this task ships only the active-version read.

## Dependencies

- **T08** (rubric tree — merged): the data being read.
- **T15** (rubric snapshot — merged): provides the deep-copy function and the committed tree contract this endpoint reuses.
- **T13** (auth seam — merged): the recruiter/admin authorization gate.

## Out of Scope

- The Position Template admin UI itself — **T14** (this task unblocks it).
- Any rubric **editing** over the API — rubric changes are Git/YAML + PR (T08/T16).
- A per-version browse endpoint (`/rubric/{version_id}`) for the Rubric Browser — a future task.
- Pagination / filtering.
