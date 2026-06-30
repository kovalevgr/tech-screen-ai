# Research: Position Template admin UI (T14)

Phase 0 decisions, grounded in the frontend conventions map + design principles.

## §1 — Data layer: openapi-typescript + openapi-fetch + React Query

- **Decision**: Generate `src/api/schema.d.ts` from `app/backend/openapi.yaml` with `openapi-typescript` (a `gen:api` package script; the file is committed). A single `openapi-fetch` client (`src/api/client.ts`) typed by that schema. Thin React Query hooks per resource (`src/api/position-templates.ts`, `src/api/rubric.ts`) for list/get/create/update/archive + active-rubric, with cache invalidation on mutations.
- **Rationale**: `.claude/agents/frontend-engineer.md` mandates a generated OpenAPI client + React Query, no hand-written fetch. `openapi-fetch` is the lightweight typed companion to `openapi-typescript`. Generated types keep the UI in lock-step with the committed contract (§14).
- **Alternatives**: hand-written fetch/types (rejected — drift, violates the convention); `openapi-react-query` (heavier; the thin hand-rolled hooks over openapi-fetch are clearer and already the documented pattern).

## §2 — shadcn primitives to add; multi-select strategy

- **Decision**: Add **select**, **checkbox**, **textarea** via the documented flow (`pnpm tokens:generate` first → `shadcn add` → verify `globals.css` marker block unchanged → run `tokens-drift` + `visual-discipline`). `level` → Select. JD → Textarea. **Stacks** and **competencies** are rendered as **checkbox groups** (Checkbox), not a custom multi-select combobox: a grouped, labelled checkbox list is accessible, simple, and avoids forking a primitive (design §7). Must-have is a Checkbox per selected competency.
- **Rationale**: The form needs select/checkbox/textarea, none present. A combobox multi-select has no shadcn primitive and would be a custom component + design review; checkbox groups satisfy the requirement with vendored primitives and clean a11y.
- **Alternatives**: a custom MultiSelect (rejected for MVP — more surface, design review); native `<select multiple>` (poor UX/a11y).

## §3 — i18n: Ukrainian labels now, runtime deferred to T20

- **Decision**: All user-facing labels are Ukrainian, kept in a small feature-local module (`src/messages/uk.ts` positions section or a typed constants object). Do **not** wire a full i18n runtime (next-intl/react-intl) — the frontend README defers that choice to T20.
- **Rationale**: §11 needs Ukrainian labels, satisfied by literals/constants. Wiring an i18n runtime now is scope creep and pre-empts T20's decision. When T20 lands the runtime, these strings move into its message catalogue.
- **Alternatives**: wire next-intl now (rejected — out of scope, T20 owns it).

## §4 — Tests: jest + RTL + MSW

- **Decision**: Component/integration tests with `@testing-library/react` + `user-event`, rendering pages/components inside a `QueryClientProvider`, with **MSW** mocking `/position-templates` + `/rubric/active`. Cover: list active-by-default + include-archived + empty/loading/error; form populates from `/rubric/active`, validates, submits (create + edit), surfaces a 422 inline; archive confirm flow.
- **Rationale**: frontend-engineer.md: "MSW handlers for tests; never real HTTP." MSW exercises the real client + hooks against mocked HTTP — high-fidelity without a backend.
- **Alternatives**: mocking the hooks/client directly (rejected — skips the client/query wiring the tests should cover).

## §5 — QueryClient provider placement

- **Decision**: `src/app/providers.tsx` (`'use client'`) exporting a `Providers` wrapper with a `QueryClient`; `layout.tsx` wraps `{children}` in it (inside `<Shell>`). 
- **Rationale**: The conventions map notes providers are added to `layout.tsx` by later tasks; React Query requires a client-component provider above any hook consumer. Keeps pages as server or client components as needed.

## §6 — Auth + feature-flag handling in the UI

- **Decision**: The client sends credentials (cookie session, `credentials: "include"`). The UI maps API failures to states: **404** (feature off) → "feature unavailable"; **401** → "sign-in required"; **403** → "not permitted". Real SSO/session is **T07**; until then the running app can't authenticate for real, so end-to-end manual use waits for T07 — but automated tests use MSW (mocked auth) and exercise all states.
- **Rationale**: The API is gated (T13 seam + §9 flag). The UI must degrade gracefully (design §10). T14 owns the UI handling, not the auth itself.

## §7 — Edit form mirrors the API's wholesale-replace PATCH

- **Decision**: The edit form loads the template (GET), maps it to form state, and on save sends the full desired `stack_ids` / `competency_ids` / `must_have_competency_ids` (PATCH replaces selection sets wholesale — T13 semantics). Create uses POST.
- **Rationale**: Matches the committed contract's PATCH behaviour; avoids partial-merge ambiguity.

## §8 — Dependency + lockfile + generated-types hygiene (Docker)

- **Decision**: Add deps and regenerate `pnpm-lock.yaml` inside the Docker `frontend` service (`pnpm add ...`); commit the lockfile (CI uses `--frozen-lockfile`). Commit the generated `schema.d.ts`; regenerate it via `pnpm gen:api` whenever `openapi.yaml` changes.
- **Rationale**: §7 Docker parity — all pnpm runs happen in the image. The committed lockfile + committed generated types keep CI deterministic and network-free.

## Open follow-ups (out of scope)

- Real SSO/session (sign-in) — **T07** (screen 10).
- The full i18n runtime + message catalogue — **T20**.
- The read-only Rubric Browser — **screen 15** (consumes the same `/rubric` family).
- A reusable MultiSelect combobox, search/pagination on the list — future, if volume warrants.
