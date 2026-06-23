# Phase 0 Research: T09 — Docker stacks

10 implementation-altitude decisions. Most pre-resolved by the user input on this branch; reproduced here as the project's canonical record.

---

## §1 — HTTP vertex-mock: Option A (REMOVE) over Option B (IMPLEMENT)

**Decision**: REMOVE. Delete `Dockerfile.vertex-mock`, the `vertex-mock` service from both compose files, the `llm` profile, and `VERTEX_MOCK_URL` from `.env.example`.

**Rationale**:
- **Zero Python consumers.** `git grep VERTEX_MOCK_URL --include='*.py'` returns empty against the current tree. No backend code reads it; no test references it. The env var is a dangling string.
- **The Dockerfile is broken-by-default.** `Dockerfile.vertex-mock` copies `tools/vertex-mock` — a directory that does not exist in the repo. Any contributor running `docker compose --profile llm up` today gets a build error pointing at a non-existent path. The "infrastructure" doesn't run; it's a trip-wire.
- **T04 supersedes it.** `app/backend/llm/_mock_backend.py` (merged in T04) is the project's Vertex mock — an in-process, SHA-keyed, fixture-driven deterministic stub used by every test that touches the Vertex wrapper. The HTTP-level mock the dead Dockerfile was *trying* to be has no remaining purpose: the wrapper switches between `LLM_BACKEND=mock` (in-process) and `LLM_BACKEND=vertex` (real Vertex SDK); there is no `LLM_BACKEND=http_mock` selector.
- **§7 parity.** Every service in the dev stack must also be in the test stack (or vice versa, with a documented operational difference). Removing the unused service reduces the dev↔CI surface area; one fewer thing to keep in sync.
- **The "speculative infrastructure" principle.** Constitution §17 says specifications precede implementation. The HTTP mock has no consuming spec; the in-process mock has T04. Removing the HTTP layer is the correct §17-aligned move.
- **Reintroduction is cheap.** If a future task ever needs HTTP-level isolation from the wrapper (e.g. a T29 WebSocket-streaming test that wants to mock at the HTTP boundary), it ships the HTTP mock then — with a real consumer and a real spec. T09 takes the position that "we'll add it back when we need it" beats "we'll keep dead code around in case we need it".

**Alternatives considered**:
- *Option B (IMPLEMENT)*: ship `infra/vertex-mock/main.py` as a tiny FastAPI echo server (per the original implementation-plan T09 text). Fix the Dockerfile path. Adds a new service to keep in sync; no consumer; future maintenance burden for hypothetical future need. Rejected.
- *Keep the broken Dockerfile + dead env var but suppress the profile*: a half-measure that retains the trip-wire. Rejected.

---

## §2 — Smoke-script shape

**Decision**: Pure bash + `curl` + `docker compose`. Lives at `scripts/smoke-docker-stack.sh`, executable, `set -euo pipefail`, `trap` for tear-down on EXIT regardless of pass/fail.

**Flow**:
```text
1. docker compose --profile db --profile web up -d --build
2. poll http://localhost:8000/health → 200, max 30 attempts × 2s curl timeout × 1s sleep
3. poll http://localhost:3000/        → 200, same shape
4. (trap) docker compose --profile db --profile web down
5. exit 0 on success; exit 1 with the precise failure message on stderr
```

**Rationale**:
- Bash + curl are present on every Docker-capable host (dev macOS, CI Ubuntu, our Docker image). No Python on the host needed; the script runs OUTSIDE the container against the host's compose.
- `set -euo pipefail` makes errors loud and unambiguous.
- `trap … EXIT` ensures the dev stack always tears down — both on smoke pass (clean exit) and on smoke fail (so the next run starts clean).
- 60-second overall budget; per-service 30 polls × 1 s sleep + 2 s curl timeout = ~90 s ceiling per service in the worst case, which is enough headroom over the existing compose healthcheck timing (Postgres ready in ~10 s; backend `uvicorn` startup in <5 s).

**Alternatives considered**:
- *Python pytest test in `app/backend/tests/`* — would tie the smoke to the existing pytest harness but would need to spawn docker compose from inside a test, which is awkward (process-out-of-process). Rejected.
- *Compose `healthcheck` is enough; no script needed* — the healthcheck verifies the service comes up, not that the HTTP layer responds with 200 from the host. T11 (Tier-1 gate) needs the host-level check. Rejected.

---

## §3 — Smoke timing budget

**Decision**: 60-second overall budget per the user input.

**Rationale**:
- Postgres healthcheck (existing): 5 s interval × 10 retries = 50 s ceiling for "healthy".
- Backend healthcheck (existing): 10 s start_period + 5 s interval; typically reaches /health in <30 s on a warm cache, < 90 s on cold.
- Frontend Next.js dev start: <10 s on warm cache, <60 s on cold.
- The smoke script's 60 s budget per service is the polling budget AFTER `compose up -d` has returned (which itself takes 10–120 s depending on cache); the polling is the marginal wait for "ready to receive traffic".
- If a service genuinely doesn't come up in 60 s of polling, that's a real failure worth reporting — not a budget that needs raising.

**Alternatives considered**:
- *30 s budget*: tight on cold cache; would produce false-positive failures during fresh-image runs. Rejected.
- *300 s budget*: lax; would hide real slowness. Rejected.

---

## §4 — `docs/engineering/docker.md` location and structure

**Decision**: Lives at `docs/engineering/docker.md`, alongside `feature-flags.md`, `cloud-setup.md`, `directory-map.md`, `anti-patterns.md`, `testing-strategy.md`, `vertex-integration.md`. Seven sections per spec FR-004:

```text
0. Why this doc exists
1. Dev stack (docker-compose.yml)
   - Profiles: db / web / full
   - Bring-up commands (one per profile combination)
   - What each profile does
   - Hot-reload behaviour
2. Test stack (docker-compose.test.yml)
   - Bring-up commands
   - The `db` profile for full integration; no-DB skip path
   - Optional e2e service (Playwright)
3. Dockerfile targets
   - builder: dep install
   - dev: adds dev tooling (used by both compose files)
   - runtime: minimal prod image (deployed by T06 to Cloud Run)
4. §7 Docker parity guarantee
   - The same image (Dockerfile dev target) runs in dev and in CI/test
   - Canonical diff between the two compose files (3 documented lines)
5. The LLM_BACKEND switch
   - LLM_BACKEND=mock → T04's in-process `_mock_backend.py` (default in dev/test)
   - LLM_BACKEND=vertex → real Vertex SDK (prod requirement)
   - Production refuses LLM_BACKEND=mock at startup (T04's assert_safe_for_environment)
6. Resetting local state
   - docker compose down (preserves volumes)
   - docker compose down -v (nukes postgres-data + frontend-node-modules)
7. Troubleshooting
   - "I added a dep but it's not in the image" → --build
   - "The image is stale even with --build" → --no-cache or remove the cache layer
   - "Postgres won't start" → check port 5432 conflict, check volume permissions
```

**Rationale**: pattern-matches every other ops doc in `docs/engineering/`; same writing voice; same "one page per concern" discipline.

**Alternatives considered**:
- *Add to README.md inline*: README is the project overview; deep ops docs go in `docs/engineering/`. Rejected.
- *Split into two files (dev / test)*: artificial split; the dev and test stacks share most of their content. Rejected.

---

## §5 — e2e service in test compose

**Decision**: Unchanged. T09 confirms it builds; T09 does not modify it.

**Rationale**:
- T03 owns the e2e flow (Playwright + frontend dev server).
- The e2e service references `Dockerfile.frontend`, which is unchanged in T09.
- Touching it would expand T09's scope into frontend territory.

**Alternatives considered**:
- *Remove e2e from the test stack temporarily, restore in a future task*: would break T03 acceptance. Rejected.
- *Move e2e to a dedicated `docker-compose.e2e.yml`*: out of T09 scope.

---

## §6 — `Dockerfile.frontend` references vertex-mock?

**Decision**: Verify with `git grep -n vertex-mock Dockerfile.frontend`; if empty (expected), no edit. If non-empty, edit out the dead refs.

**Rationale**: defensive — the spec calls for zero references after T09; this is the last grep before merge.

**Verification at plan-time**: `git grep -n vertex-mock Dockerfile.frontend` returns empty. No edit needed.

---

## §7 — `docker compose down -v` helper script

**Decision**: No. Document the one-liner in `docs/engineering/docker.md` § 6.

**Rationale**: the command is short enough to type; wrapping it adds a script-to-maintain for marginal value. The bigger win is making the operation discoverable in the docs.

**Alternatives considered**:
- *`scripts/reset-local-state.sh`*: noise; the one-liner is more transparent. Rejected.

---

## §8 — Pre-commit hooks in container — DEFERRED

**Decision**: DEFERRED to T10. T09 leaves host-based hooks unchanged.

**Rationale**: T10 owns the CI workflow + the pre-commit-in-container decision. T09's contribution is the Docker image that T10 will pull; the orchestration call is T10's.

---

## §9 — Workflow integration for the smoke script — DEFERRED

**Decision**: DEFERRED to T10. T09 ships the script; T10 wires it into `.github/workflows/ci.yml`.

**Rationale**: separation of concerns. T09 is "make the smoke script exist and pass"; T10 is "wire it to CI".

---

## §10 — Merging `Dockerfile.frontend` into the root `Dockerfile` — DEFERRED

**Decision**: DEFERRED — out of T09 scope.

**Rationale**: would require multi-context build changes (the frontend has its own dependency manager — pnpm — and node base image); the benefit (one Dockerfile) is marginal next to the disruption.

---

## Summary of resolved decisions

| # | Decision |
| - | -------- |
| 1 | REMOVE the HTTP vertex-mock (Option A); zero consumers, broken Dockerfile, §7 parity wins. |
| 2 | Pure bash + curl + docker compose for the smoke script; `set -euo pipefail` + `trap`. |
| 3 | 60 s polling budget per service in the smoke script. |
| 4 | `docs/engineering/docker.md` alongside its siblings; 7 sections. |
| 5 | e2e service unchanged. |
| 6 | `Dockerfile.frontend` is clean — verified. |
| 7 | No `down -v` script; document the one-liner. |
| 8 | Pre-commit-in-container deferred to T10. |
| 9 | Smoke-script workflow integration deferred to T10. |
| 10 | Frontend Dockerfile merge deferred (out of T09 scope). |
