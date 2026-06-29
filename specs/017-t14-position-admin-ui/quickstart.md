# Quickstart / Verification: Position Template admin UI (T14)

All runs happen in the Docker `frontend` service (§7 — no native pnpm).

## A. Dependencies + lockfile (one-time, in Docker)

```bash
# Add runtime + dev deps; regenerate + commit pnpm-lock.yaml.
docker compose -f docker-compose.test.yml run --rm frontend \
  pnpm add @tanstack/react-query openapi-fetch
docker compose -f docker-compose.test.yml run --rm frontend \
  pnpm add -D openapi-typescript msw
```

## B. Generate the typed client from the contract

```bash
# gen:api script runs openapi-typescript ../backend/openapi.yaml -> src/api/schema.d.ts
docker compose -f docker-compose.test.yml run --rm frontend pnpm gen:api
```

Commit `src/api/schema.d.ts` (and `pnpm-lock.yaml`).

## C. Add the shadcn primitives (documented flow)

```bash
docker compose -f docker-compose.test.yml run --rm frontend pnpm tokens:generate   # FIRST (alias layer)
docker compose -f docker-compose.test.yml run --rm frontend pnpm dlx shadcn-ui@2 add select checkbox textarea
# verify globals.css marker block unchanged; then:
docker compose -f docker-compose.test.yml run --rm frontend pnpm tokens:check
docker compose -f docker-compose.test.yml run --rm frontend pnpm lint:visual-discipline
```

## D. Tests + lint + types

```bash
docker compose -f docker-compose.test.yml run --rm frontend pnpm test     # jest + RTL + MSW
docker compose -f docker-compose.test.yml run --rm frontend pnpm lint      # eslint --max-warnings=0 && tsc --noEmit
docker compose -f docker-compose.test.yml run --rm frontend pnpm tokens:check
docker compose -f docker-compose.test.yml run --rm frontend pnpm lint:visual-discipline
```

Test coverage (jest, MSW-mocked API):

| Scenario | Spec ref |
| --- | --- |
| list shows active by default; include-archived reveals archived | US1, FR-001 |
| empty / loading / error (incl. 404/401/403) states render | US1, FR-008, design §10 |
| form options come from `/rubric/active`; competencies scoped to selected stacks | US2, FR-002/003 |
| valid create submits (POST); list reflects it | US2, FR-002/007 |
| invalid input → inline error; server 422 surfaced, input preserved | US2, FR-006 |
| edit prefills + saves (PATCH); archive confirm flow (soft-delete) | US3, FR-004/005 |

## Done when

- §A–C deps + `schema.d.ts` + primitives committed; `tokens:check` + `visual-discipline` clean.
- §D `pnpm test` green; `eslint --max-warnings=0` + `tsc --noEmit` clean.
- The screen spec `docs/design/screens/16-recruiter-positions/spec.md` matches the built components.
- PR body includes the **Baseline Check** block (per `.claude/agents/frontend-engineer.md`).
