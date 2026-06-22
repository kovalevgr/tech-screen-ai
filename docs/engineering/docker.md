# Docker

The canonical reference for the TechScreen Docker contract: dev stack, test stack, image targets, the §7 parity guarantee, the `LLM_BACKEND` switch, local-state reset, and troubleshooting. Open this file when something is wrong with your local stack — the answer should be inside.

## 0. Why this doc exists

Across Tier 1 (T01–T08) the Docker assets accreted incrementally: two compose files, two Dockerfiles, four profiles, and one dead service that referenced a non-existent path. T09 consolidated the lot. This page is the post-consolidation contract — what runs where, what each profile is for, and how to recover when things break. It supersedes the inline Docker explanations that used to live in `README.md`.

## 1. Dev stack — `docker-compose.yml`

The local dev environment. Backend + Postgres + frontend, each gated behind a profile so you only bring up what you need.

| Profile | Services | When to use |
| ------- | -------- | ----------- |
| *(none)* | `backend` | Bare backend with hot-reload. No DB, no frontend. Good for fiddling with a route. |
| `db` | `backend` + `postgres` | Anything that touches the DB. Postgres 17 + pgvector + pgcrypto, persisted in the `postgres-data` named volume. |
| `web` | `backend` + `frontend` | Frontend work. Hot-reload via bind-mount of `app/frontend/`. |
| `full` | `backend` + `postgres` + `frontend` | Everything (Tier-1 gate / T11 smoke target). |

Canonical bring-up commands:

```bash
# Backend only (fastest)
docker compose up --build

# Backend + DB (most backend work)
docker compose --profile db up --build

# Backend + frontend
docker compose --profile web up --build

# Everything (recommended for first-time setup)
docker compose --profile db --profile web up --build
# (equivalent to `docker compose --profile full up --build`)
```

Hot reload: the backend bind-mounts `app/backend`, `alembic/`, `alembic.ini`, `configs/`, `prompts/`; the frontend bind-mounts `app/frontend/` with a `frontend-node-modules` named volume preserved. Code edits trigger uvicorn / Next.js reload without restart.

Apply DB migrations:

```bash
docker compose --profile db run --rm backend alembic upgrade head
# Reset:
docker compose --profile db run --rm backend alembic downgrade base
```

Health endpoints:

- Backend: `http://localhost:8000/health` → `{"status":"ok", "service":"techscreen-backend", "version":"..."}`
- Frontend: `http://localhost:3000/` → 200 (admin shell)

## 2. Test stack — `docker-compose.test.yml`

The CI environment. Same backend image as dev (Dockerfile `dev` target), tmpfs-backed Postgres (data dies with the container), optional Playwright runner.

| Profile | Services | When to use |
| ------- | -------- | ----------- |
| *(none)* | `backend` + `frontend` | No-DB pytest run + frontend `pnpm test`. DB-touching tests skip themselves. |
| `db` | `backend` + `postgres` + `frontend` | Full backend integration suite (CI default). |
| `e2e` | `backend` + `postgres` + `frontend` + `e2e` | Playwright e2e tier (T03 ownership). |

Canonical CI command:

```bash
docker compose -f docker-compose.test.yml --profile db run --rm backend \
  sh -c "alembic upgrade head && pytest app/backend/tests"
```

No-DB skip path:

```bash
docker compose -f docker-compose.test.yml run --rm -e DATABASE_URL= backend \
  pytest app/backend/tests
# DB-touching tests skip cleanly; the rest pass.
```

Frontend tests run on the `frontend` service (the e2e service uses Playwright separately):

```bash
docker compose -f docker-compose.test.yml run --rm frontend pnpm test
docker compose -f docker-compose.test.yml run --rm frontend pnpm exec eslint .
docker compose -f docker-compose.test.yml run --rm frontend tsc --noEmit
```

## 3. Dockerfile targets

| File | Target | What it builds | Used by |
| ---- | ------ | -------------- | ------- |
| `Dockerfile` | `builder` | One-time deps via `uv sync --frozen --no-dev` | Internal stage only |
| `Dockerfile` | `dev` | Builder + dev tooling (pytest, ruff, mypy, ripgrep) | `backend` service in **both** compose files |
| `Dockerfile` | `runtime` | Minimal prod image; non-root user, tini entrypoint, runtime libs only | Cloud Run (T06) |
| `Dockerfile.frontend` | `dev` | Next.js dev server | `frontend` service in both compose files |
| `Dockerfile.frontend` | `runtime` | Next.js prod build (`output: standalone`) | Cloud Run (T06) |

## 4. The §7 parity guarantee

Constitution §7 says the same containers run in dev, in CI, and in prod. T09's consolidation is its enforcement.

The `backend` service in `docker-compose.yml` and the `backend` service in `docker-compose.test.yml` both build:

- `context: .`
- `dockerfile: Dockerfile`
- `target: dev`

The compose files differ only in operational ways — none of them touches the image:

| Concern | dev compose | test compose | Why |
| ------- | ----------- | ------------ | --- |
| Postgres storage | named volume `postgres-data` | `tmpfs` | Tests should not persist state across runs. |
| Backend source mount | bind-mount of `./app/backend` etc. for hot-reload | no bind-mount | CI tests the image that ships, not your edits. |
| `APP_ENV` | `dev` | `test` | Selects the test-time settings overlay. |
| `LOG_LEVEL` | `debug` | `info` | Reduce noise in CI logs. |
| Magic-link / session-cookie secrets | absent (the relevant routes are not on yet) | placeholder strings | Tests load them via the env block. |
| Optional `e2e` service | absent | `--profile e2e` | Playwright runs only in CI. |

A reviewer can confirm parity with:

```bash
diff <(grep -E "target:|image:" docker-compose.yml) \
     <(grep -E "target:|image:" docker-compose.test.yml)
# Only Playwright image lines differ (test-only); backend / frontend / postgres image lines match.
```

Production deploys the `runtime` target (separate image), populated by T06's Cloud Run wiring.

## 5. The `LLM_BACKEND` switch

The backend ships two LLM backends, selected by env var:

| `LLM_BACKEND=` | What runs | When |
| -------------- | --------- | ---- |
| `mock` | The in-process fixture-keyed stub at `app/backend/llm/_mock_backend.py` (T04). Deterministic, offline, fast. | Dev and CI (default). |
| `vertex` | The real Google Vertex AI SDK via `app/backend/llm/_real_backend.py`. | Production. |

There is **no** HTTP mock service. Earlier scaffolding included a `vertex-mock` container at `http://vertex-mock:8080`, but it never gained a consumer. T09 removed it. If a future task needs HTTP-level isolation from the wrapper, it ships its own with a real consumer; we will not resurrect speculative infrastructure.

Production refuses to start with `LLM_BACKEND=mock`. The check lives in `app.backend.settings.Settings.assert_safe_for_environment()`; a `RuntimeError` is raised at module init when `APP_ENV=prod` is paired with `LLM_BACKEND=mock`. See `specs/007-t04-vertex-client-wrapper/` for the wrapper contract.

## 6. Resetting local state

```bash
# Stop the stack but keep the named volumes (postgres-data, frontend-node-modules).
docker compose --profile db --profile web down

# Stop the stack AND remove every named volume — the next `up` boots a fresh DB.
docker compose --profile db --profile web down -v

# Same for the test stack:
docker compose -f docker-compose.test.yml --profile db down -v
```

When in doubt, `down -v` is the universal "I want this clean" command.

## 7. Troubleshooting

**"I added a dep to `pyproject.toml` but the image doesn't have it."**
The image was cached. Rebuild:

```bash
docker compose --profile db --profile web up -d --build
# Stubborn case (rare):
docker compose --profile db --profile web build --no-cache backend
```

**"Postgres won't start; port 5432 is busy."**
Another Postgres (Homebrew, an old `docker-compose down` that didn't release the port) is bound. Find the culprit:

```bash
lsof -nP -iTCP:5432 -sTCP:LISTEN
```

Kill it or stop the conflicting service.

**"The dev stack is up but `/health` returns 502."**
The backend container is still booting (uvicorn hot-reload picks up file changes on startup). Wait 5–10 s and retry. If it doesn't resolve, check container logs:

```bash
docker compose logs backend --tail 40
```

**"Frontend says `Module not found` after a `pnpm` change."**
The named volume `frontend-node-modules` is out of sync. Nuke it:

```bash
docker compose --profile web down -v
docker compose --profile web up --build
```

**"The smoke script says backend or frontend did not return 200."**
Usually a build hiccup. Check the logs:

```bash
docker compose --profile db --profile web logs backend frontend --tail 60
```

If the build itself failed, the smoke script logs the error before the polling phase.

**"My DB tests skip — but I want them to run."**
The `DATABASE_URL` env var is empty or unreachable. With the `db` profile active you should see DB tests pick up; without it, they skip by design (see `app/backend/tests/conftest.py`'s `db_available` fixture).

**"`docker compose --profile llm up` says profile not found."**
Correct — T09 removed the `llm` profile (it only contained the unused HTTP `vertex-mock` service). Use `LLM_BACKEND=mock` to select the in-process mock instead. See `specs/011-t09-docker-stacks/` for the rationale.

## Smoke check

For an automated "is my dev stack healthy?" answer, run:

```bash
bash scripts/smoke-docker-stack.sh
```

Brings the dev stack up, polls `/health` and `localhost:3000`, tears down on EXIT. Exit 0 = healthy; non-zero = something failed (a precise message goes to stderr). T10 wires this into CI; T11 runs it in the Tier-1 gate.
