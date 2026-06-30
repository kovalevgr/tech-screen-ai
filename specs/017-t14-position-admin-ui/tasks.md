---
description: "Task list for T14 — Position Template admin UI"
---

# Tasks: Position Template admin UI (T14)

**Input**: Design documents from `specs/017-t14-position-admin-ui/`
**Prerequisites**: spec.md, plan.md, research.md, data-model.md, contracts/notes.md, quickstart.md, docs/design/screens/16-recruiter-positions/spec.md

**Tests**: jest + `@testing-library/react` + `user-event` + MSW (jsdom), run in the Docker `frontend` service. Plus `eslint --max-warnings=0`, `tsc --noEmit`, `tokens:check`, `lint:visual-discipline`.

**Agent / parallelism**: every task is `agent: frontend-engineer`, sequential in one PR (§18 — `parallel: false`). `[P]` marks different-file tasks. No backend change. All pnpm/test runs are in Docker (§7). Stacked on `016-rubric-read-endpoint`.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup

- [ ] T001 In the Docker `frontend` service: `pnpm add @tanstack/react-query openapi-fetch` + `pnpm add -D openapi-typescript msw`; add a `gen:api` script to `app/frontend/package.json` (`openapi-typescript ../backend/openapi.yaml -o src/api/schema.d.ts`); commit the updated `package.json` + `pnpm-lock.yaml`. (research §1/§8)
- [ ] T002 Add the shadcn primitives via the documented flow (`pnpm tokens:generate` first → `pnpm dlx shadcn-ui@2 add select checkbox textarea` → verify the `globals.css` marker block is unchanged → `pnpm tokens:check` + `pnpm lint:visual-discipline`). Files land at `app/frontend/src/components/ui/{select,checkbox,textarea}.tsx`. (research §2; design §7)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: the data layer + provider + test infra that every screen needs.

- [ ] T003 Generate `app/frontend/src/api/schema.d.ts` (`pnpm gen:api` from `openapi.yaml`; committed) and create `app/frontend/src/api/client.ts` — an `openapi-fetch` client typed by the schema, base `NEXT_PUBLIC_API_BASE_URL`, `credentials: "include"`. (research §1/§6; FR-011)
- [ ] T004 Create `app/frontend/src/app/providers.tsx` (`'use client'`) exporting a `Providers` wrapper with a `QueryClient`; wrap `{children}` in it inside `app/frontend/src/app/layout.tsx` (under `<Shell>`). (research §5)
- [ ] T005 [P] Create React Query hooks: `app/frontend/src/api/position-templates.ts` (`usePositionTemplates(includeArchived)`, `usePositionTemplate(id)`, `useCreatePositionTemplate`, `useUpdatePositionTemplate`, `useArchivePositionTemplate` — mutations invalidate the list/item) and `app/frontend/src/api/rubric.ts` (`useActiveRubric`). (data-model.md §hooks)
- [ ] T006 [P] Add the feature's Ukrainian labels as a local module (e.g. `app/frontend/src/messages/positions.uk.ts` or a section of `uk.json`) — no i18n runtime (deferred to T20). Strings per the screen spec's Ukrainian copy table. (research §3; FR-009)
- [ ] T007 [P] Create MSW test infrastructure: `app/frontend/src/__tests__/_msw/handlers.ts` (mock `GET/POST/PATCH/DELETE /position-templates`, `GET /rubric/active`, with 200/422/404/401/403 fixtures) + jest setup wiring (server start/stop). (research §4)

**Checkpoint**: deps, client, hooks, labels, provider, and test mocking exist.

---

## Phase 3: User Story 1 — Browse position templates (Priority: P1) 🎯 MVP

**Goal**: the list at `/positions` (active-by-default, include-archived, states).

**Independent Test**: list renders active templates by default; the include-archived toggle reveals archived; empty/loading/error (incl 404/401/403) states render.

### Implementation for User Story 1

- [ ] T008 [US1] Create `app/frontend/src/components/positions/position-table.tsx` (Table of title/level/stack-count/competency-count/status pill + row actions Редагувати/Архівувати; archive confirm `Dialog`) and the list page `app/frontend/src/app/positions/page.tsx` (heading + count, `+ Нова позиція` CTA, `Показати архівовані` toggle, loading skeleton, empty state, error/unavailable states). Tokens-only styling per the screen spec + Baseline Check. (spec US1; FR-001/007/008/010)
- [ ] T009 [US1] Create `app/frontend/src/__tests__/positions-list.test.tsx` (MSW): active-by-default; include-archived reveals archived; empty state; error + 404/401/403 states. (SC-002/004)

**Checkpoint**: the list works across all states.

---

## Phase 4: User Story 2 — Create a position template (Priority: P1)

**Goal**: the create form at `/positions/new` with rubric-driven pickers + validation.

**Independent Test**: options come from `/rubric/active`, competencies scoped to selected stacks, must-have per competency; valid submit creates; invalid + server 422 surfaced inline.

### Implementation for User Story 2

- [ ] T010 [US2] Create `app/frontend/src/components/positions/position-form.tsx` (mode create|edit: Назва input, Рівень `Select`, Опис вакансії `Textarea`, Стеки/Компетенції checkbox groups from `useActiveRubric` with competencies scoped to selected stacks, Обовʼязкова checkbox per selected competency; client validation mirroring the contract; rubric-unreadable → submit disabled) and the create page `app/frontend/src/app/positions/new/page.tsx` (uses the form in create mode → `useCreatePositionTemplate`; back-link; 422 inline). (spec US2; FR-002/003/006)
- [ ] T011 [US2] Create `app/frontend/src/__tests__/positions-form.test.tsx` (MSW): options from rubric; competency scoping; valid create POST → success; missing competency / must-have⊄selected → inline error; server 422 surfaced + input preserved. (SC-001/003)

**Checkpoint**: a recruiter can create a valid template; invalid input is caught.

---

## Phase 5: User Story 3 — Edit and archive (Priority: P2)

**Goal**: edit at `/positions/[id]` and archive (soft) from the list.

**Independent Test**: edit prefills + saves (PATCH); archive asks confirmation, soft-deletes, leaves the default list.

### Implementation for User Story 3

- [ ] T012 [US3] Create the edit page `app/frontend/src/app/positions/[id]/page.tsx` (prefill via `usePositionTemplate(id)`, save via `useUpdatePositionTemplate` — full desired sets, PATCH wholesale-replace; loading/404 states), reusing `position-form.tsx` in edit mode. Wire the archive confirm in `position-table.tsx` to `useArchivePositionTemplate`. (spec US3; FR-004/005)
- [ ] T013 [US3] Extend tests: edit prefill + save reflected in the list; archive confirm → row leaves the default list, still visible with include-archived. (SC-002)

**Checkpoint**: full lifecycle; archive is soft + confirmed.

---

## Phase 6: Polish & Verification

- [ ] T014 Confirm `docs/design/screens/16-recruiter-positions/spec.md` matches the built components; run the quickstart matrix in Docker: `pnpm test` green, `pnpm lint` (eslint --max-warnings=0 + tsc --noEmit) clean, `pnpm tokens:check` clean, `pnpm lint:visual-discipline` clean. Prepare the **Baseline Check** block for the PR body. (quickstart.md; SC-005)

---

## Dependencies & Execution Order

- **Setup**: T001 → T002 (both touch package.json/lock; sequential).
- **Foundational**: T003 (client, needs T001) → T004 (provider); T005 ∥ T006 ∥ T007 (different files, need T003's client/types).
- **US1**: T008 (needs hooks T005 + primitives T002 + provider T004) → T009 (MSW T007).
- **US2**: T010 (needs hooks + rubric + primitives) → T011.
- **US3**: T012 (reuses the form + hooks) → T013.
- **Polish**: T014 last.

### Parallel opportunities (file-level, single committer)
- T005 ∥ T006 ∥ T007 (api hooks / labels / MSW — distinct files).
- Never parallel: edits to `layout.tsx` (T004), `position-table.tsx` (T008→T012), `position-form.tsx` (T010→reused T012), the shared test files.

---

## Implementation Strategy

### MVP first (US1)
1. Setup + Foundational → US1 (the list).
2. **STOP and VALIDATE**: the list renders across states against MSW.

### Incremental delivery
1. Setup → deps + client + primitives.
2. Foundational → provider + hooks + labels + MSW.
3. US1 → browse (MVP).
4. US2 → create (the core form).
5. US3 → edit + archive.
6. Polish → screen-spec match + full verification + Baseline Check.

### Suggested commit grouping (manual commits, our norm)
- `feat(T14): deps + generated openapi client + shadcn primitives` (T001–T003)
- `feat(T14): QueryClient provider + React Query hooks + uk labels + MSW` (T004–T007)
- `feat(T14): positions list view + table + tests` (T008–T009)
- `feat(T14): position create form + validation + tests` (T010–T011)
- `feat(T14): edit page + archive flow + tests; verification` (T012–T014)

---

## Notes
- `[P]` = different files; NOT sub-agent fan-out (§18).
- No backend change — consumes the committed `openapi.yaml` (T12/T13/016).
- Visual discipline + WCAG AA are acceptance gates (design §5/§8); tokens-only.
- i18n runtime is T20; T14 uses Ukrainian label constants.
- Implementation will likely be delegated to the `frontend-engineer` sub-agent.
