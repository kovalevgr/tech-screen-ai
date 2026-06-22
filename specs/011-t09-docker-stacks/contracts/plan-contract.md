# Plan-time Contract Pointer: T09

Pointer document, not a contract. The actual artefacts at the repo root ARE the contract.

## Runtime contracts

| Contract | Path | Owner | Notes |
| -------- | ---- | ----- | ----- |
| **Dev stack** | `docker-compose.yml` | T09 (post-consolidation) | Profiles `db` / `web` / `full`; backend uses Dockerfile `dev` target. Source bind-mounted for hot-reload. |
| **Test stack** | `docker-compose.test.yml` | T09 (post-consolidation) | Same backend image (Dockerfile `dev` target); tmpfs-backed Postgres; optional `e2e` profile (T03's Playwright). |
| **Backend image** | `Dockerfile` (`builder` / `dev` / `runtime`) | T01–T05 (already in place); T09 confirms unchanged | Single Dockerfile, three stages, two consumers. |
| **Frontend image** | `Dockerfile.frontend` (`dev` / `runtime`) | T03; T09 confirms unchanged | Next.js dev server + prod build. |
| **Smoke script** | `scripts/smoke-docker-stack.sh` | T09 (new) | Bash + curl + docker compose; 0/1 exit-code contract; trap-cleanup. Used by T10 in CI and by T11 in the Tier-1 gate. |
| **Docker reference** | `docs/engineering/docker.md` | T09 (new) | The human-readable contract. 7 sections per spec FR-004. |
| **Vertex mock (in-process)** | `app/backend/llm/_mock_backend.py` | T04 (unchanged); T09 updates docstring only | The project's only Vertex mock; the HTTP layer was removed by T09. |

## What T09 removes

| Removed | Why |
| ------- | --- |
| `Dockerfile.vertex-mock` | References non-existent `tools/vertex-mock/`; no consumer; T04's in-process mock supersedes it. |
| `vertex-mock` service in `docker-compose.yml` + `docker-compose.test.yml` | No image to build; profile-gated `llm` had no real consumer. |
| `llm` profile in both compose files | Only inhabitant was `vertex-mock`. |
| `VERTEX_MOCK_URL` env var in `.env.example` + compose env blocks | `git grep VERTEX_MOCK_URL --include='*.py'` returns empty — zero Python consumers. |

## T10 / T11 boundary

T09 ships the smoke script + the documented compose contract. **T10** wires the script into `.github/workflows/ci.yml`. **T11** invokes the script as part of the Tier-1 smoke gate. Neither plumbing is in T09's scope.

## Verification contracts (referenced by `tasks.md`)

| Check | What it locks in | Spec ref |
| ----- | ---------------- | ------- |
| `git grep -nE "vertex-mock\|VERTEX_MOCK_URL\|tools/vertex-mock\|Dockerfile\.vertex-mock"` returns empty (excluding `specs/011-t09-docker-stacks/`) | Dead-infrastructure removal complete | SC-002 |
| Full backend test suite (138 passing post-T08) passes byte-identically in the test stack | §7 parity preserved + no regression | SC-004 / FR-007 |
| `scripts/smoke-docker-stack.sh` exits 0 against a healthy dev stack | The smoke contract works | SC-003 / FR-006 |
| `pre-commit run --all-files` clean on post-T09 tree | All existing hooks pass (T05a + T08 + others) | SC-006 / FR-011 |
| `python -m app.backend.generate_openapi --check` exits 0 | No HTTP route added; OpenAPI byte-identical | SC-007 |
| `docker compose config --profiles` lists `db`, `web`, `full` only | No `llm` profile remains | SC-002 / FR-001 |
