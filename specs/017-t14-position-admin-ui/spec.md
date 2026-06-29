# Feature Specification: Position Template admin UI (T14)

**Feature Branch**: `017-t14-position-admin-ui`
**Created**: 2026-06-24
**Status**: Draft
**Input**: User description: "T14 — Recruiter-facing UI to manage Position Templates: a list view and a create/edit form, built on the committed openapi.yaml (/position-templates CRUD + /rubric/active). Generated TS client + React Query; Ukrainian labels; visual-discipline-compliant. Screen spec docs/design/screens/16-recruiter-positions/spec.md; routes /positions, /positions/new, /positions/:id."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A recruiter browses existing position templates (Priority: P1)

A recruiter opens the Positions area and sees the templates that have been defined — their title, target level, and how many stacks/competencies each covers — so they can find one to reuse or edit. Archived templates are hidden by default but can be shown on demand.

**Why this priority**: The list is the entry point to the whole feature and the lowest-risk slice; it proves the data layer (read) and the screen scaffolding end to end, and it is what a recruiter sees first.

**Independent Test**: With templates present, open the list and confirm only active ones show by default, that the include-archived control reveals archived ones, and that an empty dataset shows a clear empty state rather than an error.

**Acceptance Scenarios**:

1. **Given** active and archived templates exist, **When** the recruiter opens the list, **Then** only active templates are shown, each with title, level, and stack/competency counts.
2. **Given** the same data, **When** the recruiter enables "include archived", **Then** archived templates also appear, visibly marked as archived.
3. **Given** no templates exist, **When** the list loads, **Then** an empty state with a "create" affordance is shown.
4. **Given** the data is loading or the request fails, **When** the list renders, **Then** a loading state and (on failure) a clear error state are shown.

---

### User Story 2 - A recruiter creates a position template (Priority: P1)

A recruiter defines a new role: a title, a target level, an optional job description, the technology stacks it covers, and the competencies to assess — marking which competencies are mandatory. The stacks and competencies come from the current rubric, so the recruiter chooses from real options rather than typing identifiers. Invalid input is caught before and after submit, with clear messages.

**Why this priority**: Creating a template is the core purpose of the feature; everything else (browse, edit, archive) orbits it. Equal priority to US1 because a list with nothing to create is not useful.

**Independent Test**: Open the create form, confirm the level choices and the stack/competency options are populated from the current rubric, that competencies are limited to the chosen stacks, that a must-have flag can be set per competency, and that submitting a valid template succeeds while invalid input (e.g. no competency, a must-have not among the selected) is rejected with an inline message.

**Acceptance Scenarios**:

1. **Given** the create form, **When** it loads, **Then** the level options are the four allowed levels and the stack/competency choices reflect the current rubric.
2. **Given** a recruiter selects stacks, **When** they pick competencies, **Then** only competencies belonging to the selected stacks are offered, each with a must-have toggle.
3. **Given** a valid template, **When** the recruiter saves, **Then** it is created and the recruiter is returned to the list (or the new template's view) with the template present.
4. **Given** input the server rejects (validation error), **When** the recruiter saves, **Then** the specific problem is shown inline and nothing is lost.

---

### User Story 3 - A recruiter edits and archives a template (Priority: P2)

A recruiter opens an existing template, changes its fields/selections, and saves; or archives a template that is no longer used. Archiving never destroys data — the template leaves the default list but is still retrievable.

**Why this priority**: Edit/archive complete the lifecycle but depend on create/list existing first; P2.

**Independent Test**: Edit a template's title/level/selections and confirm the change persists and re-validates; archive a template and confirm it disappears from the default list (and remains visible with include-archived); confirm archive asks for confirmation and is reversible only via data, never a hard delete.

**Acceptance Scenarios**:

1. **Given** an existing template, **When** the recruiter edits it and saves, **Then** the change persists and the same validation applies.
2. **Given** an existing template, **When** the recruiter archives it (confirming the prompt), **Then** it is removed from the default list but still appears under include-archived.
3. **Given** an archive action, **When** it is triggered, **Then** a confirmation is required before it takes effect.

### Edge Cases

- **No current rubric**: If the rubric cannot be read, the create/edit form shows a clear error and disables submission (you cannot build a template without rubric options) rather than presenting empty pickers.
- **Feature unavailable / not signed in**: If the API reports the feature is off, the caller is unauthenticated, or lacks the recruiter/admin role, the UI shows an appropriate "unavailable" / "sign-in required" / "not permitted" state rather than a broken page.
- **Stale list after a change**: After create/edit/archive, the list reflects the change without a manual refresh.
- **Validation parity**: The same rules the server enforces (level, at least one competency, must-have ⊆ selected, competency-belongs-to-stack) are surfaced to the recruiter; server errors are the source of truth and are shown inline.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The UI MUST present a list of position templates showing, per template, its title, level, and stack/competency counts, with archived templates excluded by default and shown via an explicit control.
- **FR-002**: The UI MUST let a recruiter create a template by entering a title, choosing a level from the allowed set, optionally entering a job description, selecting stacks, selecting competencies (limited to the selected stacks), and marking must-have competencies.
- **FR-003**: The stack and competency choices MUST be populated from the current rubric (read from the API), not entered as free text or identifiers.
- **FR-004**: The UI MUST let a recruiter edit an existing template and save the changes, applying the same validation as create.
- **FR-005**: The UI MUST let a recruiter archive a template behind a confirmation; archiving removes it from the default list without destroying it (it remains visible with include-archived).
- **FR-006**: The UI MUST surface validation errors — both client-side checks mirroring the contract and server-rejected (422) errors — inline, without losing the recruiter's input.
- **FR-007**: The list MUST reflect create/edit/archive changes without requiring a manual page reload.
- **FR-008**: The UI MUST handle unavailable/unauthorized states (feature off, unauthenticated, wrong role, rubric unreadable) with clear, non-broken states.
- **FR-009**: All user-facing text MUST be Ukrainian (technical terms may stay English), consistent with §11.
- **FR-010**: The UI MUST conform to the design system — using design tokens and the vendored component primitives, with no ad-hoc colour/spacing values (the visual-discipline checks pass).
- **FR-011**: The data layer MUST consume the committed API contract via a generated client (not a hand-written one), so the UI stays in sync with the backend.

### Key Entities *(include if feature involves data)*

- **Position template** *(from T12/T13)*: the role definition being listed/created/edited/archived — title, level, optional JD, selected stacks, selected competencies (with must-have), archived state.
- **Rubric (active)** *(from the rubric read endpoint)*: the source of selectable stacks and competencies (names + identifiers) shown in the form.
- **Recruiter** *(actor)*: the authenticated staff member (recruiter/admin) using the screens.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A recruiter can create a complete, valid position template from the form in a single pass, choosing stacks and competencies from the current rubric, with zero need to know any identifier.
- **SC-002**: The list shows active templates by default and archived ones only on demand, and reflects create/edit/archive within the same session without a manual reload — verified in automated component/integration tests.
- **SC-003**: 100% of the contract's validation rules are surfaced to the recruiter (inline) for invalid input, and valid input succeeds — verified in tests.
- **SC-004**: The screen behaves correctly in the unavailable/unauthorized and empty/loading/error states (no broken page) — verified in tests.
- **SC-005**: The screen specification `16-recruiter-positions` exists and matches the implemented components; the design-system (visual-discipline) checks and type/lint checks pass.
- **SC-006**: The API client is generated from the committed contract (no drift between UI types and the backend).

## Assumptions

- **Screen slot + routes**: The screen is `docs/design/screens/16-recruiter-positions/` (recruiter `1x` range — the implementation-plan's "02-positions" conflicts with the real taxonomy where `02` is the candidate session). Routes are `/positions`, `/positions/new`, `/positions/:id`, matching the established `/rubrics` convention (not `/admin/positions`). To confirm at the gate.
- **Authorization is assumed, not built here**: The screens assume an authenticated recruiter/admin session. Real SSO login (screen 10) is **T07**; until then the UI handles 401/403/404 gracefully and dev/test provides an authenticated context with the feature flag on.
- **No backend work**: The API and its contract are complete (T12 schema, T13 CRUD, the rubric read endpoint). T14 consumes them; it changes no backend code.
- **Generated client + server state**: A client is generated from the committed contract and server state is managed with a query/caching layer (fetch + mutations + invalidation) — standard for this frontend.
- **Edit selection semantics mirror the API**: Editing replaces selection sets wholesale (the API's PATCH semantics); the form sends the full desired sets.
- **Scope of the form**: Single create/edit form covering title, level, JD, stacks, competencies, must-have flags. No bulk operations, no template duplication, no search/pagination at MVP (the list is expected to be small).

## Dependencies

- **T12** (position_template schema — merged), **T13** (`/position-templates` CRUD — merged), **rubric read endpoint** (`GET /rubric/active` — in review, branch `016`): the data + contract the UI consumes.
- **T03** (Next.js skeleton — merged) + the design system (tokens, components): the frontend baseline.

## Out of Scope

- Any backend change (done in T12/T13/016).
- Candidate-facing screens, recruiter login/SSO (**T07**, screen 10), and the rubric browser (**screen 15**).
- Bulk actions, duplication, search/pagination, and rich JD editing.
