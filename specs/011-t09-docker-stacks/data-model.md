# Phase 1 Data Model: T09 — Docker stacks

T09 has no database entities. This document enumerates the **operational entities** — the moving parts a reviewer can grep against the post-T09 tree to verify consolidation. These are the "shape contracts" the smoke script and the docs rely on.

---

## 1. Dev-stack profile set (`docker-compose.yml`)

After T09:

| Profile | Services included | Use case |
| ------- | ----------------- | -------- |
| *(default, no profile)* | `backend` | Bare backend with hot-reload; no DB, no frontend |
| `db` | `backend`, `postgres` | Backend + DB; for working on DB-backed features |
| `web` | `backend`, `frontend` | Backend + frontend; for working on UI |
| `full` | `backend`, `postgres`, `frontend` | Everything (T11 Tier-1 smoke target) |

**Removed by T09**: `llm` profile (was: `backend`, `vertex-mock`); `vertex-mock` service.

Grep verification: `docker compose config --profiles | sort` returns exactly `db full web` (one per line, alphabetised).

---

## 2. Test-stack profile set (`docker-compose.test.yml`)

After T09:

| Profile | Services included | Use case |
| ------- | ----------------- | -------- |
| *(default, no profile)* | `backend`, `frontend` | No-DB pytest run + frontend `pnpm test` |
| `db` | `backend`, `postgres`, `frontend` | Full integration suite (CI default) |
| `e2e` | `backend`, `postgres`, `frontend`, `e2e` | Playwright e2e tier (T03 ownership) |
| `full` | All of the above | Belt-and-suspenders combined run |

**Removed by T09**: `llm` profile; `vertex-mock` service.

Grep verification: `docker compose -f docker-compose.test.yml config --profiles | sort` returns exactly `db e2e full`.

---

## 3. Dockerfile-target matrix

| Target | What it builds | Used by |
| ------ | -------------- | ------- |
| `builder` (`Dockerfile`, stage 1) | One-time deps + `uv sync --frozen --no-dev` | Internal stage only |
| `dev` (`Dockerfile`, stage 2) | Adds dev deps (pytest, ruff, mypy, ripgrep, openpyxl, jsonschema…) | `backend` service in BOTH compose files |
| `runtime` (`Dockerfile`, stage 3) | Minimal prod image; runs as non-root `techscreen` user, tini entrypoint | T06 Cloud Run deploy (future) |
| `dev` (`Dockerfile.frontend`, stage 1) | Next.js dev server | `frontend` service in both compose files |
| `runtime` (`Dockerfile.frontend`, stage 2) | Next.js prod build | T06 Cloud Run frontend deploy (future) |

**Removed by T09**: `Dockerfile.vertex-mock` entirely.

---

## 4. Smoke-script exit-code contract (`scripts/smoke-docker-stack.sh`)

| Exit code | Meaning | Notes |
| --------- | ------- | ----- |
| `0` | Dev stack came up and answered HTTP requests within the budget | Standard success path |
| `1` | A service failed to reach 200 within the polling budget | Stderr names which service + last observed status |

**Pre-conditions**: Docker Desktop running; ports 8000, 3000, 5432 free on the host.

**Post-conditions**: `docker compose --profile db --profile web down` has been invoked (via EXIT trap), regardless of pass/fail. Containers cleaned; named volumes (`postgres-data`, `frontend-node-modules`) preserved unless the caller passes `-v` to `down` manually.

**Per-poll shape**:
- 2-second curl timeout per attempt
- 1-second sleep between attempts
- 30-attempt ceiling per service (≈ 90 seconds wall-clock per service)
- Overall budget: < 60 seconds typical, < 180 seconds worst case

---

## 5. Canonical diff between the two compose files

The §7 parity guarantee says the SAME image is built; differences are operational only. After T09, the documented allowed differences (in `docs/engineering/docker.md` § 4) are:

| Concern | dev compose | test compose | Rationale |
| ------- | ----------- | ------------ | --------- |
| Postgres storage | named volume `postgres-data` | `tmpfs` | Tests should not persist state across runs |
| Backend source mount | bind-mount of `./app/backend` for hot-reload | no bind-mount; image carries source | Tests use the built image (CI parity) |
| `APP_ENV` | `dev` | `test` | Selects the test-time settings overlay |
| `LOG_LEVEL` | `debug` | `info` | Reduce noise in CI logs |
| Optional `e2e` service | absent | present (profile `e2e`) | Playwright runs only in CI |
| Backend bind-mount of `alembic/`, `configs/`, `prompts/` | present | absent | Tests use the image; dev wants hot-reload of these too |

**Identical**: the `backend` service `build:` block (`context: .`, `dockerfile: Dockerfile`, `target: dev`); the postgres image (`pgvector/pgvector:pg17` in dev, the same in test post-T05); the `frontend` build context (`dev` target of `Dockerfile.frontend`).

A reviewer can verify: `diff <(grep -E "target:|image:" docker-compose.yml) <(grep -E "target:|image:" docker-compose.test.yml)` → outputs only the lines for `e2e`'s Playwright image (test-stack only) plus the postgres image lines (matching). Backend / frontend lines are identical.

---

## 6. Cross-reference to prior work

- **T04** (`app/backend/llm/_mock_backend.py`): the in-process Vertex mock that supersedes the HTTP mock. T09 updates its docstring (FR-009) to call this out.
- **T05** (Dockerfile `COPY scripts ./scripts`, `COPY docs/contracts ./docs/contracts`, `COPY docs/engineering ./docs/engineering`): the in-image carrying of scripts and docs. T09 inherits this — the new `scripts/smoke-docker-stack.sh` automatically lands in the image too, though its callers run on the host (not in the container).
- **T05a** (the `feature-flag-registered` pre-commit hook + the `sync-feature-flags.yml` workflow): T09 leaves both untouched.
- **T08** (the `rubric-schema` pre-commit hook): T09 leaves it untouched.
- **T10** (CI workflow + migration-approval gate): T09 ships the contract T10 binds to (the smoke script + the documented compose stack).
- **T11** (Tier-1 smoke gate): T11 invokes the smoke script as part of acceptance.
