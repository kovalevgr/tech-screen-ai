# Coding Conventions

How we write code in TechScreen. These are not style preferences; they are conventions we rely on in review, tooling, and automated checks. When a convention here conflicts with an example in the existing codebase, the convention wins and the example is wrong.

If you disagree with something here, open a PR that changes this document — do not silently deviate.

---

## Languages and runtimes

- **Backend:** Python 3.12 (pinned). No 3.11 syntax, no 3.13 features.
- **Frontend:** TypeScript 5.x with `strict: true`. No plain `.js` files in `app/frontend/src`.
- **Shell:** `bash` only, `#!/usr/bin/env bash` + `set -euo pipefail` at the top of every script.
- **IaC:** HCL (Terraform 1.7+).

---

## Python

### Layout

```
app/backend/
  api/            FastAPI routers only. No business logic, no DB access.
  services/       Business logic. Stateless functions or classes.
  repositories/   DB access. SQLAlchemy models + query functions. Nothing else.
  llm/            Vertex adapter, prompt assembly, response parsing.
  orchestrator/   The deterministic state machine (ADR-005).
  domain/         Pure-Python entities and value objects.
  config/         Pydantic settings loaded from env and configs/ YAML.
  utils/          Small helpers. Keep this thin; prefer adding to the right layer.
  tests/          Mirrors the above structure.
```

### The layering rule

Each layer may import from layers **below** it in this order:

```
api → services → repositories / llm / orchestrator → domain / config / utils
```

`domain`, `config`, and `utils` do not import from any other layer. `api` must not import `repositories` directly (go through `services`). Violations are caught by an `import-linter` config in CI.

### Style

- `ruff` + `ruff format` are the source of truth for linting and formatting. Run pre-commit; CI enforces.
- `mypy --strict` on everything under `app/backend/`. No `# type: ignore` without an attached comment explaining why.
- Function parameters and return types are always annotated. No bare `dict`, `list`, `tuple` — use concrete types or `TypedDict` / `Pydantic`.
- Never `from x import *`. Never re-export unless in an `__init__.py` that is itself a public surface.
- String formatting: f-strings. Never `%` formatting. Never `.format()` except in logging where it is required.
- Logging: the `logging` module with structured fields (`logger.info("assessment_complete", extra={"session_id": id})`). Never `print()`.

### Errors

- Raise specific exception classes defined in `app/backend/exceptions.py`. Never raise bare `Exception`.
- Exceptions bubble up to the API layer where a FastAPI exception handler maps them to HTTP responses. Middle layers do not catch-and-swallow.
- Never `except:` (bare). Never `except Exception:` unless the next line re-raises or logs with full stack and exits.

### Async

- FastAPI routes are `async def`. Repositories use SQLAlchemy's async session.
- Never `time.sleep` in async code. Use `asyncio.sleep`.
- Never block the event loop. If a sync library is required, run it under `asyncio.to_thread`.

### Database

- Every DB change is an Alembic migration. No inline DDL in code.
- Migrations are named by convention: `<ordinal>_<imperative-sentence>.py`, e.g. `0042_add_rubric_snapshot_column.py`.
- Migrations are forward-only. A column drop is a three-migration sequence: add replacement column → dual-write → backfill → remove reads → drop old column.
- Model classes live in `repositories/models.py` grouped by domain aggregate.
- Query functions are defined as module-level functions in `repositories/<aggregate>.py` and accept an `AsyncSession` as their first parameter.
- No ORM lazy-loading. Either explicit `selectinload` or a repository function that returns exactly what's needed.

### Tests

- `pytest` with `pytest-asyncio`.
- Test files mirror source tree: `tests/services/test_assessor_service.py` tests `services/assessor_service.py`.
- No mocking the database. Integration tests hit a real Postgres in Docker (see constitution §7). Unit tests mock only the LLM boundary (`llm/*` module).
- Fixtures live in `tests/conftest.py` (top level) and sub-`conftest.py` per area.
- Each test class owns its setup/teardown. No "global" cross-test state.
- Arrange / Act / Assert comments are not required but welcome in long tests.

---

## TypeScript / React

### Layout

```
app/frontend/src/
  app/            Next.js App Router routes.
  components/     Reusable UI components. Grouped by feature, not by shape.
  lib/            Hooks, clients, utilities. Framework-agnostic when possible.
  design/         Tokens, theme, icons. Imports from `docs/design/tokens/`.
  api/            Generated OpenAPI client + thin wrappers.
  tests/          Component and integration tests.
```

### Style

- `eslint` with `@typescript-eslint` and `eslint-plugin-react`. `prettier` for formatting. CI enforces.
- Prefer functional components. No class components except where third-party libraries require them.
- Hooks order: `useState` → `useRef` → `useEffect` → custom hooks. No early returns before hooks.
- One component per file. File and component have the same PascalCase name.
- Named exports. Default export only for Next.js route files where required.

### State and data

- Server state: generated React Query hooks from the OpenAPI client. No hand-written `fetch` in components.
- Client state: `useState` for local, `Zustand` or React Context for cross-component — in that order.
- Do not use Redux.

### Styling

- Tailwind classes. No CSS files except `globals.css` for resets and `@tailwind` directives.
- shadcn/ui primitives instead of building from scratch. Customise via Tailwind, not by forking.
- Tokens (colour, spacing, typography) come from `docs/design/tokens/`. Do not hardcode hex values in components.
- Icons from `lucide-react`. Size via Tailwind classes.

### Tests

- `vitest` for unit. `@testing-library/react` for components. Playwright for E2E (lives in `app/frontend/e2e/`).
- Component tests assert behaviour, not implementation details. Avoid testing Tailwind classes.
- Network calls in tests go through `msw` handlers — never real HTTP.

---

## Bash scripts

- `#!/usr/bin/env bash`
- `set -euo pipefail` on line 2.
- Idempotent by default. Re-running a script should not fail if prior state exists.
- No `cd` in the middle of a script — use absolute paths or `pushd`/`popd`.
- Variables with spaces are always quoted: `"${VAR}"`.
- Log what you are doing: `echo "==> Creating bucket ${BUCKET}"`.

---

## Git

### Branches

- One feature per branch. Feature branches are named `feat/<short-slug>`, fixes `fix/<short-slug>`, chores `chore/<short-slug>`.
- Rebase onto `main` before merge. We keep a linear history.

### Commits

- Imperative mood, lower-case first word, no trailing period: `add assessor retry logic`.
- Subject ≤ 72 characters. Body wrapped at 80 columns.
- Reference the spec in the body: `Refs .specify/specs/0042-foo`.
- No AI-generated boilerplate in messages (`🤖 Generated with...`). The project does not attribute by tool.

### Pull requests

- Title = branch name, humanised.
- Body includes: what changes, why, spec link, screenshots for UI, test plan.
- Reviewer agent runs automatically and blocks merge on constitution violations, secrets hits, or missing tests.

---

## Naming

- **Python:** `snake_case` for modules, functions, variables. `PascalCase` for classes. `UPPER_SNAKE` for constants.
- **TypeScript:** `camelCase` for variables and functions, `PascalCase` for types and components, `UPPER_SNAKE` only for true constants.
- **DB:** `snake_case` for tables and columns. Plural tables (`candidates`, not `candidate`). Join tables `<a>_<b>`.
- **Files:** mirror the primary symbol they define. `candidate_service.py` exports `CandidateService`.
- **Feature flags:** `<area>.<feature>` in `snake_case`: `interviewer.streaming_response`.

---

## Documentation

- Every public function in `services/` has a docstring: one-line summary + `Args` + `Returns` + `Raises`. Google style.
- Every ADR follows Michael Nygard format (Context / Decision / Consequences).
- README at the repo root is for humans; `CLAUDE.md` is for AI. Keep both current.
- Diagrams: source `.dot` files in `docs/diagrams/`, rendered `.png` checked in next to them.

---

## Dependencies

- Add a dependency only when it saves significant work.
- Every new dependency is a PR with a one-line justification in the commit body.
- Pin Python deps exactly (`==`) in `pyproject.toml`. Pin npm deps exactly via lockfile (commit `pnpm-lock.yaml`).
- Upgrade dependencies in dedicated PRs, one ecosystem at a time.

---

## Things we do not do

- Do not check in generated code unless explicitly decided otherwise.
- Do not disable a test. If a test is wrong, delete it with a reason in the commit body.
- Do not add `TODO:` without an assigned owner and an issue link.
- Do not introduce a new architectural layer without an ADR.
- Do not copy code across layers. If two layers need the same logic, move it to the lowest layer that makes sense.
