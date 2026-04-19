# Testing Strategy

How TechScreen earns confidence without a staging environment. We rely on multiple test layers, Docker parity with production, and a calibration loop that watches agent behaviour over time.

Related: [ADR-009](../adr/009-prod-only-topology.md), [ADR-010](../adr/010-docker-first-parity.md), [constitution §7, §13](../.specify/memory/constitution.md).

---

## Goals

- Every merge to `main` is safe to deploy.
- Local green CI reliably predicts production behaviour.
- LLM behaviour regressions are visible within 24 hours of a prompt or model change.
- Test time stays under 10 minutes on the critical path (unit + integration) so engineers do not skip it.

---

## Layers

### 1. Unit tests

**What.** Pure-function and class-level tests in Python and TypeScript.

**Scope.**
- Backend: `app/backend/**/tests/`, one file per source file.
- Frontend: co-located `*.test.tsx` next to the component.

**Rules.**
- No network. No DB. No Vertex.
- Mocks only at the LLM boundary (`llm/*` module) or at the HTTP client boundary on the frontend (`msw`).
- Fast: single test < 100ms. Full unit suite < 60s.

**Framework.** `pytest` + `pytest-asyncio`. `vitest` + `@testing-library/react`.

---

### 2. Integration tests

**What.** Tests that exercise real side-effecting collaborators — Postgres, the Vertex mock, the file system, the feature flag service.

**Scope.**
- Repository queries against a real Postgres schema (applied via `alembic upgrade head`).
- State-machine flows through multiple agents using `vertex-mock`.
- Feature-flag-gated code paths with both flag states.

**Rules.**
- Runs inside `docker-compose.test.yml`. Postgres, vertex-mock, and the backend under test all live in that compose network.
- Test isolation: each test either uses a transaction rolled back at teardown, or a dedicated schema created per test.
- No shared mutable fixtures across tests.

**Framework.** `pytest` with `testcontainers` OR compose-up-wait-run pattern. CI uses compose-up.

---

### 3. Contract tests

**What.** Tests that validate the OpenAPI spec matches backend behaviour AND that the frontend's generated client matches the OpenAPI spec.

**Scope.**
- Backend: for every endpoint, assert response conforms to the spec's schema (using `schemathesis` or equivalent).
- Frontend: the generated client is regenerated in CI; a diff means the frontend PR forgot to regenerate.

**Rules.**
- OpenAPI spec is committed at `app/backend/openapi.yaml` (generated from FastAPI in CI).
- Any PR that changes a route and forgets to update the spec fails the contract-drift check.

---

### 4. Agent regression tests

**What.** Tests that replay a fixed set of candidate turns through the current prompt version and assert that the Assessor output matches a known-good fixture within tolerance.

**Scope.**
- Small curated set (~20 turns initially) spanning: strong answers, weak answers, off-topic, factually wrong, code-switched.
- For each: the expected level ±1 and the expected red flags.

**Rules.**
- Does NOT call real Vertex. Uses `vertex-mock` with pre-recorded responses for each prompt hash.
- Fails only on material drift — exact match is not required because fixtures are sample outputs, not the canonical truth.
- Updating a fixture is a conscious PR act, not a rubber-stamp.

**When it runs.** On every prompt edit PR, and nightly on `main`.

---

### 5. End-to-end tests

**What.** Playwright tests that drive the frontend against a full dockerised backend, simulating real user flows: recruiter login, plan review, candidate join, session complete.

**Scope.** Smoke paths, not exhaustive coverage. Target 5–8 scenarios that cover the critical path from a recruiter creating a session through a candidate completing one.

**Rules.**
- Runs in `docker-compose.test.yml` with backend + frontend + Postgres + vertex-mock all live.
- Uses stable selectors (`data-testid`), not Tailwind classes or XPath.
- Screenshots captured on failure, attached to CI output.

**When it runs.** On every PR, and on every Cloud Run preview revision at 0% traffic (as the smoke test that gates `/promote 10`).

---

### 6. Calibration runs

**What.** Compare Assessor output on a labelled dataset against human ground-truth scores. Produces agreement metrics.

**Scope.**
- Dataset: ~50 labelled turns at MVP start, growing as reviewers produce corrections.
- Metrics per competency: exact match %, within-0.5 %, systematic bias (mean signed error).
- Metrics overall: rates of `FACTUALLY_WRONG` agreement, `RED_FLAG` precision/recall.

**Rules.**
- Warning only. Never blocks merge. Constitution §13.
- Report posted as a PR comment with trend vs previous run.
- Baseline is the previous version's metric, not an absolute target — regressions are relative.

**When it runs.** On every prompt or model change PR, and weekly on `main`.

**Tooling.** `calibration-run` skill (`.claude/skills/calibration-run/SKILL.md`).

---

### 7. Smoke tests (post-deploy)

**What.** A minimal suite that runs against a Cloud Run revision receiving 0% traffic, before any user sees it.

**Scope.**
- Authenticated health check.
- A single synthetic session start + one candidate turn + assessment produced.
- Feature flag table read. Secret Manager secret read.

**Rules.**
- Runs via `/deploy` after the new revision is up.
- Takes < 60s.
- Failure blocks `/promote 10`.

---

## CI pipeline

```
GitHub Actions (on every PR):

  lint/format        ← ruff, eslint, prettier, HCL fmt, shellcheck
  backend-unit       ← pytest -m "not integration"
  frontend-unit      ← vitest
  contract           ← openapi spec drift + client regen
  integration        ← docker-compose -f docker-compose.test.yml up
  agent-regression   ← pytest prompts/ replay
  e2e                ← Playwright against full compose stack
  calibration        ← calibration-run (warning-only, see §13)
  reviewer           ← reviewer sub-agent (constitution, secrets, tests, migrations)
```

The reviewer sub-agent is the last gate. It reads the PR diff and the full floor (constitution, ADRs) and raises blocking comments on violations.

---

## What does NOT run in CI

- Performance / load tests. We run those manually before pilot milestones and on demand.
- Security penetration tests. We run these pre-pilot and on major changes to auth or data model, not per-PR.
- A real Vertex call. Expensive, flaky, and — critically — `vertex-mock` is the contract the backend is written against anyway.

---

## Test data

- `tests/fixtures/` holds canonical test data by scope (repositories, services, agents).
- Candidate-PII-shaped fixtures use synthetic names (`Тестова Кандидатка`) and synthetic emails (`test+NN@example.com`).
- Rubric fixtures are small, hand-curated snapshots representative of real rubric shapes.

---

## Flakiness policy

A flaky test is a broken test. We do not tolerate "retry to make CI green".

If a test flakes:

1. First flake: mark it with `@pytest.mark.flaky` referencing an issue, and fix within one week.
2. Second flake from the same root cause: disable and escalate — we prefer lower coverage to lying CI.

CI retries are not configured. A failure is a failure.

---

## Test naming

- **Python:** `test_<subject>_<condition>_<expected>`. `test_assessor_returns_level_1_on_empty_answer`.
- **TypeScript:** `describe` with the component or function name; `it("returns X when Y")`.
- **Playwright:** `<user role> can <action>`.

---

## Responsibility

- **Author of a change** writes tests for the change.
- **Reviewer agent** blocks on missing tests in obvious places (new service function, new endpoint, new component with logic).
- **`testing-strategy.md`** is owned by the project — edits require a PR and review.
