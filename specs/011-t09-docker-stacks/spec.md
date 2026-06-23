# Feature Specification: Docker stacks — consolidate, document, kill dead infra (T09)

**Feature Branch**: `011-t09-docker-stacks`
**Created**: 2026-04-28
**Status**: Draft
**Input**: User description: T09 — Docker stacks (dev + test), per `docs/engineering/implementation-plan.md` Tier 1 / W1–W2

## User Scenarios & Testing *(mandatory)*

The "users" of this feature are everyone who reaches for the project's containers: a new contributor running the stack for the first time; an engineer who just ran `git pull` and needs the local DB to come up; the CI pipeline (T10) that runs the test stack on every PR; the `reviewer` sub-agent that needs the smoke to be reproducible; the operator who runs the Tier-1 smoke before promoting a Cloud Run revision (T11). T09 delivers no new behaviour — it ships **consolidation, deletion, and documentation** so every later contributor inherits a clean, predictable Docker contract that already passes constitution §7 parity.

### User Story 1 — A new contributor brings up the full dev stack from a clean clone (Priority: P1)

A new engineer clones the repository, has Docker Desktop running, and types one documented command. Backend + frontend + Postgres come up; the backend serves `/health` 200; the frontend renders the admin shell at `localhost:3000`. They never see a Docker build error pointing at a missing path (`tools/vertex-mock/`) or a profile that no longer exists.

**Why this priority**: P1 because this is the canonical "did I break Docker" check. Constitution §7 (parity dev → CI → prod) leans on the assumption that the dev stack and the test stack run identically; if either is broken at HEAD, every later contributor wastes time debugging local breakage before they can do real work. Cleaning the dead `vertex-mock` references is the part of §7 we owe the next person to clone.

**Independent Test**: From a clean clone (or `docker compose down -v`), running the documented bring-up command followed by a `curl localhost:8000/health` and a `curl localhost:3000` produces a 200 from each, in under five minutes (build included), with **zero** confusing error messages on stderr.

**Acceptance Scenarios**:

1. **Given** a clean clone with Docker running, **When** the contributor runs the documented dev bring-up command, **Then** the backend and frontend services reach the `healthy` state and `/health` returns `{"status":"ok",...}`.
2. **Given** the same clean clone, **When** any contributor inspects the compose files, **Then** they see no service named `vertex-mock` and no profile named `llm`, and `git grep -nE "vertex-mock|tools/vertex-mock|VERTEX_MOCK_URL"` returns zero hits.
3. **Given** a contributor whose Docker image cache is empty, **When** the bring-up runs `docker compose ... up --build`, **Then** every image required by the active profiles builds without referencing a non-existent path.

---

### User Story 2 — CI and engineers run the test stack with deterministic results (Priority: P1)

The same image that runs in dev runs in the test stack — same `dev` Dockerfile target, same Python version, same dependencies. CI (T10, future) invokes the test stack the same way an engineer does locally, and every test that passes locally passes in CI, byte for byte.

**Why this priority**: Co-equal P1. §7 dev-CI-prod parity is the project's main pre-prod defence (there is no staging — §8). If the test stack drifts from the dev image, every "passes on my machine, fails in CI" debugging session steals time from the actual work. T09 is the moment to enforce the parity by inspection — `git diff docker-compose.yml docker-compose.test.yml` should show only legitimate differences (read-only docs mount, tmpfs Postgres, no host volume bind for the backend in CI), not divergence.

**Independent Test**: Running the documented test-stack command — exactly the line printed in the new docs file — exercises the post-T08 test suite (currently 138 passing) inside the container, with `alembic upgrade head` applied first. Exit code is 0, all tests pass, no skipped tests are skipped *for the wrong reason* (e.g. a missing service).

**Acceptance Scenarios**:

1. **Given** a clean clone with Docker running, **When** the contributor runs the documented test-stack command, **Then** the full backend suite passes with the existing pass count (138 at T09 baseline) and zero unrelated failures.
2. **Given** the same clone, **When** the no-DB skip path is exercised (the test command without the `db` profile), **Then** the DB tests skip cleanly and the rest of the suite passes.
3. **Given** a reviewer reading both compose files side-by-side, **When** they look for "what differs between dev and test", **Then** the differences are only the small set documented in the new Docker reference (tmpfs storage, no source bind-mount in test, optional `e2e` service); the container image specification is byte-identical.

---

### User Story 3 — Dead infrastructure is cleaned up; the tree contains zero references to removed assets (Priority: P1)

The current state contains broken references: a `Dockerfile.vertex-mock` that copies a non-existent `tools/vertex-mock/` directory, a `vertex-mock` compose service in two profiles (`llm`, `full`) that would fail to build if anyone activated them, and a `VERTEX_MOCK_URL` env var in `.env.example` that no Python code reads. After T09, none of these exist; every grep that asks "is there anything left from the dead HTTP mock?" returns empty.

**Why this priority**: P1 because dead infrastructure is worse than missing infrastructure. A missing thing fails loudly when someone tries to use it. A dead thing fails subtly when someone *almost* uses it (e.g. `docker compose --profile full up` would fail, but only after the user has built up an expectation). Constitution §17 (specs precede implementation) implies the inverse: implementations that no longer match any spec must be removed. The HTTP `vertex-mock` is in this category — superseded by T04's in-process `_mock_backend.py`.

**Independent Test**: After T09 merges, running `git grep -nE "vertex-mock|VERTEX_MOCK_URL|tools/vertex-mock|infra/vertex-mock"` against the post-T09 tree returns **zero** non-deletion hits (the only matches, if any, are in CHANGELOG-style historical references or the spec file itself).

**Acceptance Scenarios**:

1. **Given** the post-T09 tree, **When** a contributor greps for any of the four dead references, **Then** the result is empty.
2. **Given** the post-T09 compose files, **When** an engineer lists profiles (`docker compose config --profiles`), **Then** the result contains `db`, `web`, `full`, `e2e` (or whatever the documented set is) — but **not** `llm`.
3. **Given** the post-T09 `.env.example`, **When** an engineer searches for "MOCK", **Then** they find no reference to `VERTEX_MOCK_URL`. (References to `LLM_BACKEND=mock|vertex` legitimately remain — that selector lives at the wrapper layer, not in compose.)

---

### User Story 4 — A future contributor learns the Docker contract from one document (Priority: P2)

A contributor (human or AI sub-agent) joining the project on Day-1 reads one page and understands: what the dev stack does, what the test stack does, what every Dockerfile target is for, what every compose profile is for, what the `LLM_BACKEND` switch means, how to recover from a broken local image, and where the prod image specification lives. They never have to read seven READMEs or grep the compose comments to figure it out.

**Why this priority**: P2 because it is the long-tail value — every later contributor benefits a little; no single one is blocked without it. But the cost of NOT writing it now is everyone re-deriving the contract from the YAML.

**Independent Test**: A first-time contributor can open `docs/engineering/docker.md`, copy the documented dev command, paste it, and have the stack running in under five minutes, without consulting any other file in the repo and without asking another human a question.

**Acceptance Scenarios**:

1. **Given** the post-T09 tree, **When** a contributor opens `docs/engineering/docker.md`, **Then** they find a clear section per profile, per Dockerfile target, per compose file, plus a troubleshooting cheatsheet.
2. **Given** the README, **When** the contributor reaches the Docker-related sections, **Then** the README points at `docs/engineering/docker.md` for the deep dive instead of duplicating it.
3. **Given** the new contributor follows the docs end-to-end, **When** they get to the smoke-script step, **Then** they can run a single command that verifies the dev stack is alive (the smoke script T09 ships).

---

### Edge Cases

- **`docker compose --profile full up` invoked against the post-T09 tree**: succeeds — the `full` profile contains backend + frontend + postgres (no `vertex-mock`); the `llm` profile no longer exists, so accidentally typing `--profile llm` produces a clear "profile not found" message rather than a confusing build failure.
- **A future task wants HTTP-level isolation from the Vertex wrapper**: that task brings the HTTP mock back as a new T09-style cleanup of its own, with a real consumer. T09 does not pre-emptively keep dead code waiting for hypothetical future use.
- **A contributor runs `docker compose down` without `-v`**: postgres-data volume survives; their local DB state persists across restarts. Documented.
- **A contributor runs `docker compose down -v`**: postgres-data volume is removed; the next `up` boots a fresh DB. Documented (this is the canonical "reset my local state" command).
- **A `pyproject.toml` change without a rebuild**: the next `docker compose up` runs the old image. The docs file calls this out + provides the `--build` flag remedy + when to use `--no-cache` for stubborn cases.
- **`docker compose --profile db up postgres` race condition** where backend starts before postgres healthcheck passes: existing `depends_on: { condition: service_healthy }` in compose already handles it; documented in the troubleshooting section.
- **Mock-vs-prod safety**: `LLM_BACKEND=mock` in `APP_ENV=prod` is rejected at backend startup by T04's `Settings.assert_safe_for_environment()` (already in place). T09's docs surface this as an explicit "you cannot accidentally run prod with the mock" guarantee.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST remove the `vertex-mock` service from both `docker-compose.yml` and `docker-compose.test.yml`, including the profile gates (`llm`, and `llm` membership in `full`).
- **FR-002**: System MUST delete `Dockerfile.vertex-mock` from the repository root; the file references a non-existent source path and serves no live image build.
- **FR-003**: System MUST remove the `VERTEX_MOCK_URL` line from `.env.example` and any compose environment block; it has no Python consumer.
- **FR-004**: System MUST ship a new `docs/engineering/docker.md` that, in one place, documents: how the dev stack runs and what each profile does; how the test stack runs; what each Dockerfile target (`builder` / `dev` / `runtime`) is for; the §7 parity guarantee; the `LLM_BACKEND` switch and which value is prod-required; the canonical "reset my local state" workflow; and a short troubleshooting cheatsheet.
- **FR-005**: System MUST update the `README.md` to point at `docs/engineering/docker.md` for the Docker deep dive, and to remove any standalone references to the HTTP `vertex-mock`.
- **FR-006**: System MUST ship a small smoke script (`scripts/smoke-docker-stack.sh` or equivalent) that brings the documented dev stack up, hits `/health` on the backend and the root URL on the frontend, asserts a 200 from each within a generous timeout, and tears down. Exit code is 0 on success, non-zero with a clear stderr message on any failure.
- **FR-007**: System MUST leave the existing 138 backend tests passing without modification. T09 ships no test changes; if a test in another suite needs to change because of a T09 deletion, that is a bug in T09's scope and must be fixed before merge.
- **FR-008**: System MUST preserve constitution §7 parity: the same image (Dockerfile `dev` target) is used by the backend service in both `docker-compose.yml` and `docker-compose.test.yml`; differences between the two compose files are limited to documented operational concerns (tmpfs storage in test, source bind-mount in dev, optional `e2e` service in test).
- **FR-009**: System MUST update the in-process `_mock_backend.py` docstring (one short paragraph) to make explicit that this is the project's only Vertex mock; the HTTP mock layer was removed by T09 because no consumer ever used it.
- **FR-010**: System MUST NOT introduce a new compose service, a new Dockerfile target, a new build argument, a new Python dependency, or a new HTTP endpoint. T09 is a *consolidation* PR, not a new-surface PR.
- **FR-011**: System MUST keep `pre-commit` and the existing CI gates (T05's hook, T05a's hook, T08's hook, `gitleaks`, `detect-secrets`, `ruff`, `mypy --strict`, `actionlint`, OpenAPI byte-identical regeneration) all passing on the post-T09 tree.

### Key Entities

- **Dev stack** (`docker-compose.yml`): the canonical local development environment. Backend (hot-reloaded), Postgres (with a persistent named volume), frontend (hot-reloaded). Profiles select the desired subset (`db`, `web`, `full`).
- **Test stack** (`docker-compose.test.yml`): the canonical CI environment. Same backend image (`dev` target), tmpfs-backed Postgres, optional Playwright `e2e` service. Profiles match the dev stack where they overlap.
- **Dockerfile targets**: `builder` (one-time dep install), `dev` (adds dev tooling; used by both compose files), `runtime` (minimal prod image; deployed by T06 to Cloud Run).
- **Smoke script**: a single-file shell test that exercises the dev stack end-to-end and returns a clean exit code. Future CI invokes the same script; T11 (Tier-1 gate) will too.
- **Docker reference document** (`docs/engineering/docker.md`): the single source of truth for the Docker contract — what runs where, how to operate it, how to debug it.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A new contributor can bring up the documented dev stack from a clean clone in **under 5 minutes**, including image build time on a typical broadband connection.
- **SC-002**: The post-T09 tree carries **zero** references to `tools/vertex-mock`, `VERTEX_MOCK_URL`, `Dockerfile.vertex-mock`, or a `vertex-mock` compose service — measurable by `git grep -nE "..."` returning empty (excluding the spec/docs files that legitimately discuss the removal).
- **SC-003**: `docker compose --profile db --profile web up --build` exits with all services healthy in **under 5 minutes** on a clean machine; the smoke script then asserts `/health` returns 200 in **under 5 seconds** after services are reported healthy.
- **SC-004**: The full backend test suite (currently 138 passing under T08) passes byte-identically inside the test stack: `docker compose -f docker-compose.test.yml --profile db run --rm backend sh -c "alembic upgrade head && pytest app/backend/tests"` → **138 passed**.
- **SC-005**: Reading `docs/engineering/docker.md` only, a first-time contributor can answer **all five** of the following in writing: (a) which command brings up dev with DB and frontend; (b) which command runs the test suite; (c) what `LLM_BACKEND=mock` means and why prod forbids it; (d) how to reset their local DB to empty; (e) why `docker compose --profile llm up` no longer exists.
- **SC-006**: After T09 merges, the existing pre-commit + CI gates (T05/T05a/T08 hooks + `gitleaks`, `detect-secrets`, `ruff`, `mypy --strict`, `actionlint`) all pass on the clean post-T09 tree — verified by `pre-commit run --all-files` exiting 0.
- **SC-007**: The OpenAPI regen-and-diff guardrail produces a byte-identical `openapi.yaml` after T09 — verified by `python -m app.backend.generate_openapi --check` exiting 0.
- **SC-008**: A `git diff` of `docker-compose.yml` against `docker-compose.test.yml` shows that the two files declare the **same backend image** (same Dockerfile target, same context); their only differences are operational (storage backing, port exposure, volumes, optional e2e service). This is verifiable by a reviewer at a glance — the documented section in `docs/engineering/docker.md` calls out exactly which lines should differ.

## Assumptions

- The HTTP `vertex-mock` service has no consumer at T09-time and will not gain one in a near-term task. If a real consumer appears, that task will reintroduce an HTTP mock with a clear specification — *not* T09's silently-broken version. This assumption is supported by the zero hits of `VERTEX_MOCK_URL` in Python code at the time of writing.
- The in-process `_mock_backend.py` from T04 is the de-facto Vertex mock and is unaffected by T09 except for one docstring update (FR-009).
- Constitution §7 parity is satisfied today between dev and test compose files; T09 verifies + documents this, not establishes it.
- Docker Compose v2+ (`docker compose`, space-separated) is the canonical CLI. The smoke script and docs target this CLI shape.
- The `e2e` service in `docker-compose.test.yml` (Playwright runner from T03) is out of scope; T09 confirms it still builds but does not modify it.
- Cloud-Run-specific concerns (image push, traffic split, secret injection) are owned by T06; T09 documents the `runtime` Dockerfile target's existence but does not deploy.
- The smoke script is operator-driven for the duration of T09; T10 will wire it into a workflow on every PR. T09 does not ship the workflow.
- The post-T09 tree continues to use the **`mock` LLM backend by default in dev/test** (per T04 spec): `LLM_BACKEND=mock` in `.env.example` and in both compose files. Production is the only environment that requires `LLM_BACKEND=vertex`, enforced by `Settings.assert_safe_for_environment()` at startup.

## Out of scope

- The CI workflow itself (`.github/workflows/ci.yml`, reviewer agent invocation, migration-approval gate) — owned by T10. T09 ships the smoke script T10 will call.
- Pre-commit hook orchestration inside a container — T10 decides whether to migrate from "host pre-commit" to "container pre-commit". T09 leaves the existing host-based hooks unchanged.
- Production Cloud Run deploy mechanics — owned by T06 (Cloud SQL + Cloud Run + Secret Manager + WIF binding).
- Any changes to the frontend Docker setup — T03 / T05a established the frontend Docker pattern; T09 confirms it still builds.
- New Dockerfile stages, new compose services, new build args — explicit non-goal.
- Reintroducing the HTTP `vertex-mock` — if a future need arises, a future task ships it with a clear consumer. T09 takes the position that "speculative infrastructure with no consumer is worse than missing infrastructure".

## Plan-phase research items (handle in `plan.md` / `research.md`)

- **Vertex-mock decision** — implement (Option B, original plan text) or remove (Option A, in-process T04 mock supersedes). Recommendation: A, with the rationale grounded in zero consumers, §7 parity (one fewer service to keep in sync), and the principle of removing speculative infrastructure. Final call lives in `plan.md`.
- **Smoke-script shape** — pure bash + `curl` + `docker compose` calls (no Python). The script must work in CI where Python may not be in the host image; bash is universally available.
- **`docs/engineering/docker.md` location and structure** — the `docs/engineering/` directory is the natural home (alongside `feature-flags.md`, `cloud-setup.md`, `directory-map.md`, `anti-patterns.md`); structure mirrors those neighbours.
- **README delta** — keep the `Quickstart (local, Docker-first)` section intact (it already lives in README) but trim the long-form Docker explanation to a single paragraph and point at the new doc.
- **e2e service** — leaves it untouched; confirm it builds from the existing `Dockerfile.frontend` `dev` target.
