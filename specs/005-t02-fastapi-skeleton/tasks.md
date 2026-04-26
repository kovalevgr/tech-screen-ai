---
description: "Task list for T02 — FastAPI Skeleton"
---

# Tasks: FastAPI Skeleton (T02)

**Input**: Design documents from [`specs/005-t02-fastapi-skeleton/`](./)
**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/backend-contract.md](./contracts/backend-contract.md), [quickstart.md](./quickstart.md)

**Tests**: Generated. The spec's acceptance criteria pin three committed tests — the `/health` smoke (FR-009), the PII-redaction test (FR-010, validating constitution §15), and the OpenAPI regeneration drift check (FR-005). Tests are part of the T02 acceptance gate, not an optional TDD overlay.

**Agent ownership**: All tasks are owned by `agent: backend-engineer` with `parallel: false` at the sub-agent level, per [docs/engineering/implementation-plan.md](../../docs/engineering/implementation-plan.md) T02. The `[P]` marker inside this file means "different files, no intra-phase dependency" — the orchestrator may open these files in any order within a phase, not that they go to different sub-agents. Sub-agent fan-out (to T03, T04, T06, etc.) starts **after** T02 lands.

**Organization**: Tasks are grouped by user story. The implementation order is Setup → Foundational → US1 (boot + `/health`) → US2 (OpenAPI contract) → US3 (PII redactor) → US4 (smoke test + README) → Polish. US2/US3/US4 each depend on US1 (main.py exists) but can otherwise be reshuffled.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can edit/create in any order inside the same phase (different files, no in-phase dependency).
- **[Story]**: `US1`, `US2`, `US3`, `US4`. Setup, Foundational, and Polish tasks carry no story label.
- Paths are **relative to the repo root**.

## Path Conventions

- Runtime code: `app/backend/*.py` (package root `app/backend/`).
- Tests: `app/backend/tests/*.py` (package root `app/backend/tests/`).
- Committed contract artefact: `app/backend/openapi.yaml`.
- Repo-root config: `pyproject.toml`, `uv.lock`, `README.md`.
- No files outside these locations are touched (FR-011 scope fence).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Verify the workspace is ready to receive T02 changes. No source files created yet.

- [X] T001 Verify the current branch is `005-t02-fastapi-skeleton` with a clean working tree and `.specify/feature.json` points at `specs/005-t02-fastapi-skeleton` (run `git rev-parse --abbrev-ref HEAD`, `git status --short`, `cat .specify/feature.json`). If any check fails, stop and investigate before continuing.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Land the dependency updates, the test-package scaffolding, and the logging module stub. Every later phase imports or runs against these. No endpoint code, no PII processor yet.

**⚠️ CRITICAL**: Phases 3–6 cannot begin until this phase is complete — each user story assumes `fastapi`, `structlog`, and `pytest` are installed and that `app/backend/logging.py` exports `configure_logging()`.

- [X] T002 Update `pyproject.toml` at the repo root to add runtime and dev dependencies. Under `[project].dependencies`: `"fastapi>=0.115,<0.120"`, `"uvicorn[standard]>=0.32,<0.36"`, `"structlog>=24.4,<25"`, `"pyyaml>=6.0,<7"`. Under `[dependency-groups].dev` (extend existing list): `"pytest>=8.3,<9"`, `"httpx>=0.27,<0.29"`. Keep every existing key (ruff, mypy, `[tool.ruff]`, `[tool.mypy]`) byte-identical. Reference: [research.md](./research.md) §1.
- [X] T003 Regenerate the Python lockfile by running `uv lock` at the repo root (after T002). Commit the updated `uv.lock` exactly as produced — this is what `Dockerfile` `uv sync --frozen --no-dev` consumes. No manual edits to the lockfile. Reference: [research.md](./research.md) §1.
- [X] T004 [P] Create `app/backend/tests/__init__.py` as a zero-byte file so pytest discovers tests as a proper package and the pre-commit `no-print-statements` exclusion path (`^app/backend/tests/.*$`) engages correctly.
- [X] T005 [P] Create `app/backend/tests/conftest.py` with two pytest fixtures: (a) `client` — session-scoped, lazily imports `app` from `app.backend.main` and returns a `fastapi.testclient.TestClient(app)` instance (lazy import so the fixture file is loadable before `main.py` exists); (b) `captured_logs` — function-scoped, saves the current `structlog.get_config()`, reconfigures structlog with the same processor chain **except** the terminal renderer is replaced with a processor that appends the `event_dict` (as a JSON string produced by `structlog.processors.JSONRenderer()`) to a list, yields the list to the test, and restores the original config on teardown. The fixture MUST preserve every upstream processor so the PII redactor (added in US3) still runs. Reference: [research.md](./research.md) §4–§5, [data-model.md](./data-model.md) entity 5.
- [X] T006 [P] Create `app/backend/logging.py` exposing `configure_logging(*, log_format: str | None = None, log_level: str | None = None) -> None`. At T02-Foundational close, the processor pipeline is: `merge_contextvars → add_log_level → TimeStamper(fmt="iso", utc=True) → EventRenamer("message") → JSONRenderer()` (when `LOG_FORMAT=json`, the default) or `ConsoleRenderer(colors=True)` (when `LOG_FORMAT=console`). `log_format` / `log_level` args default to the `LOG_FORMAT` / `LOG_LEVEL` env vars with fallback `"json"` / `"INFO"`. Unknown values warn-and-fallback (no hard failure at import). **Do not add the PII redactor yet — that is US3's task (T013).** Reference: [research.md](./research.md) §4, §7; [contracts/backend-contract.md](./contracts/backend-contract.md) surface 3.

**Checkpoint**: `uv sync --dev` installs the new deps; `uv run python -c "from app.backend.logging import configure_logging; configure_logging()"` exits 0 and emits a single structured log-config record (or nothing if no log statement runs). `app/backend/tests/` is importable as a package.

---

## Phase 3: User Story 1 — Service boots and reports health (Priority: P1) 🎯 MVP slice 1 of 4

**Goal**: `uvicorn app.backend.main:app` starts within 5 s with no external dependency configured; `GET /health` returns HTTP 200 with the contracted JSON body.

**Independent Test**: From the branch with Phase 2 complete, run `uv run uvicorn app.backend.main:app` in one shell and `curl -sS http://127.0.0.1:8000/health` in another; expect HTTP 200 and JSON matching [contracts/backend-contract.md](./contracts/backend-contract.md) surface 2 (`status`, `service`, `version` fields). Acceptance Scenarios 1–3 in [spec.md](./spec.md) US1.

### Implementation for User Story 1

- [X] T007 [US1] Create `app/backend/main.py` with: (a) import `configure_logging` from `app.backend.logging` and call it once at module level before constructing the app; (b) a Pydantic `HealthResponse(BaseModel)` with `status: Literal["ok"]`, `service: Literal["techscreen-backend"]`, `version: str`; (c) module-level `app = FastAPI(title="TechScreen Backend", version=_project_version())` where `_project_version()` reads `importlib.metadata.version("techscreen")` with a `PackageNotFoundError` fallback to `"0.0.0"`; (d) one route `@app.get("/health", response_model=HealthResponse)` returning `HealthResponse(status="ok", service="techscreen-backend", version=_project_version())`. No other routes, no middleware, no startup/shutdown handlers. Reference: [research.md](./research.md) §6, §7; [contracts/backend-contract.md](./contracts/backend-contract.md) surface 2; [data-model.md](./data-model.md) entities 1 and 2.
- [X] T008 [US1] Validate US1 acceptance manually: run `uv run uvicorn app.backend.main:app --port 8000` and confirm startup within 5 s. In a second shell, run `curl -sS -o /tmp/t02-health.json -w "%{http_code}\n" http://127.0.0.1:8000/health`, expect `200`. Inspect `/tmp/t02-health.json` and confirm the three contracted fields are present with the expected literal values. Stop the server. Do **not** commit the scratch file.

**Checkpoint**: US1 is fully functional. `uvicorn` boots, `/health` returns the contracted body, no env var is required. US2/US3/US4 can now begin in parallel (or sequentially, per single-committer convention).

---

## Phase 4: User Story 2 — Committed OpenAPI contract (Priority: P1) 🎯 MVP slice 2 of 4

**Goal**: `app/backend/openapi.yaml` is committed, is regenerable by a single command, and any drift between the committed bytes and the regenerated bytes fails a pytest test before merge.

**Independent Test**: Run `uv run python -m app.backend.generate_openapi --check`; expect exit 0 with no output (or a no-drift note). Run `uv run pytest app/backend/tests/test_openapi_regeneration.py -v`; expect green in < 10 s. Acceptance Scenarios 1–3 in [spec.md](./spec.md) US2.

### Implementation for User Story 2

- [X] T009 [US2] Create `app/backend/generate_openapi.py` with: (a) a `build_yaml_bytes() -> bytes` helper that imports `app` from `app.backend.main`, calls `app.openapi()`, and returns `yaml.safe_dump(schema, sort_keys=True, allow_unicode=True, default_flow_style=False).encode("utf-8")`; (b) a `write_yaml(path: Path) -> None` helper that calls `build_yaml_bytes()` and writes the result to `path` using binary mode (no text-mode line-ending translation); (c) a `check_yaml(path: Path) -> int` helper that compares `build_yaml_bytes()` to `path.read_bytes()`, returns 0 on match or 1 on drift (and prints the first ~40 lines of `difflib.unified_diff(...)` with path labels `(committed)` and `(regenerated)`); (d) an `if __name__ == "__main__":` block that parses `argparse` with a single `--check` flag, resolves `path = Path(__file__).parent / "openapi.yaml"`, and dispatches to `write_yaml(path)` or `sys.exit(check_yaml(path))`. Reference: [research.md](./research.md) §2–§3; [contracts/backend-contract.md](./contracts/backend-contract.md) surface 1.
- [X] T010 [US2] Generate and commit `app/backend/openapi.yaml` by running `uv run python -m app.backend.generate_openapi` at the repo root (after T009). Commit the produced file exactly as written — no manual edits. Confirm the file is byte-stable by running the command twice and `diff`-ing the two outputs. Reference: [data-model.md](./data-model.md) entity 4.
- [X] T011 [US2] Create `app/backend/tests/test_openapi_regeneration.py` with a single test `test_committed_openapi_matches_regenerated_bytes` that imports `build_yaml_bytes` from `app.backend.generate_openapi`, reads `app/backend/openapi.yaml` via `pathlib.Path(__file__).resolve().parent.parent / "openapi.yaml"`, and `assert` byte-equality. On failure, include a `difflib.unified_diff` head (first ~40 lines) in the pytest assertion message so the reviewer can diagnose without re-running the generator. Reference: [contracts/backend-contract.md](./contracts/backend-contract.md) surface 4.
- [X] T012 [US2] Run `uv run pytest app/backend/tests/test_openapi_regeneration.py -v` and confirm green (< 10 s, SC-003). If drift is reported, inspect the diff head, regenerate via T010's command, recommit, and re-run.

**Checkpoint**: `openapi.yaml` is committed; the drift test is green; T03 (Next.js skeleton) can now plan its client against a stable contract.

---

## Phase 5: User Story 3 — Candidate PII never leaks through logs (Priority: P1) 🎯 MVP slice 3 of 4

**Goal**: The structlog pipeline redacts values in the PII field allow-list and scrubs email patterns from free-text `event`/`message` strings. The committed test proves both shapes redact on a single log call.

**Independent Test**: Run `uv run pytest app/backend/tests/test_logging_pii.py -v`; expect green in < 5 s. The test emits `logger.info("foo bar x@y.com", candidate_email="x@y.com")` (mirroring the T02 acceptance clause in [docs/engineering/implementation-plan.md](../../docs/engineering/implementation-plan.md) verbatim) and asserts neither occurrence of the raw email appears in the captured record. Acceptance Scenarios 1–3 in [spec.md](./spec.md) US3.

### Implementation for User Story 3

- [X] T013 [US3] Extend `app/backend/logging.py` to add: (a) a module-level `PII_FIELDS: frozenset[str] = frozenset({"candidate_email"})` constant; (b) a module-level `_EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")`; (c) a `pii_redaction_processor(logger, method_name, event_dict)` function that replaces `event_dict[k]` with the literal string `"<REDACTED>"` for every `k` in `PII_FIELDS & event_dict.keys()`, then applies `_EMAIL_PATTERN.sub("<REDACTED_EMAIL>", event_dict["event"])` if the `event` value is a `str` (leave other types untouched); (d) splice `pii_redaction_processor` into the pipeline assembled by `configure_logging()` **between** `TimeStamper` and `EventRenamer` so it runs before the event key is renamed to `message`. The processor MUST be pure (no logging, no I/O, no exceptions) and MUST NOT mutate the input dict — return a new dict or mutate a copy. Reference: [research.md](./research.md) §4; [contracts/backend-contract.md](./contracts/backend-contract.md) surface 3; [data-model.md](./data-model.md) entity 3.
- [X] T014 [US3] Create `app/backend/tests/test_logging_pii.py` with a single test `test_candidate_email_redacted_in_field_and_freetext(captured_logs)` that: (a) imports and calls `configure_logging()` (idempotent — called during fixture setup too, safe to call again); (b) gets a logger via `structlog.get_logger("test_pii")`; (c) invokes `log.info("foo bar x@y.com", candidate_email="x@y.com")`; (d) asserts the captured list has exactly one record; (e) asserts the serialised record (join the list entries into one string) contains neither the substring `"x@y.com"` nor `'candidate_email": "x@y.com"'` nor `"candidate_email='x@y.com'"`; (f) asserts `"<REDACTED>"` appears in the record (structured-field redaction); (g) asserts `"<REDACTED_EMAIL>"` appears in the record (free-text redaction); (h) adds a second invocation `log.info("app started", port=8000)` and asserts neither `<REDACTED>` nor `<REDACTED_EMAIL>` appears in **that** record (non-PII records are not mangled — acceptance scenario 2). Reference: [contracts/backend-contract.md](./contracts/backend-contract.md) surface 3 "Test contract".
- [X] T015 [US3] Run `uv run pytest app/backend/tests/test_logging_pii.py -v` and confirm green. If it fails because `captured_logs` doesn't preserve the PII processor, fix the fixture in `conftest.py` (T005) — the fixture must snapshot `structlog.get_config()` **after** `configure_logging()` has installed the redactor, not before.

**Checkpoint**: Constitution §15 invariant has an automated test that blocks merge on regression. The PII allow-list is extension-ready for future tasks (T04, T05, T18, T20) per the extension procedure in [contracts/backend-contract.md](./contracts/backend-contract.md) surface 3.

---

## Phase 6: User Story 4 — Smoke test and test convention (Priority: P2)

**Goal**: A committed, request-level smoke test exercises `GET /health` through the real FastAPI routing stack and establishes the test-location convention every later backend task copies.

**Independent Test**: Run `uv run pytest app/backend/tests/test_health.py -v`; expect green in < 5 s. Acceptance Scenarios 1–2 in [spec.md](./spec.md) US4.

### Implementation for User Story 4

- [X] T016 [US4] Create `app/backend/tests/test_health.py` with a single test `test_health_returns_200_with_expected_shape(client)` that: (a) calls `response = client.get("/health")`; (b) asserts `response.status_code == 200`; (c) asserts `response.headers["content-type"].startswith("application/json")`; (d) reads `body = response.json()` and asserts `body["status"] == "ok"`, `body["service"] == "techscreen-backend"`, and `body["version"]` is a non-empty string. This exercises FastAPI routing, Pydantic serialisation, and the `client` fixture — the pattern every future backend endpoint test reuses. Reference: [contracts/backend-contract.md](./contracts/backend-contract.md) surface 2; [data-model.md](./data-model.md) entity 2.
- [X] T017 [US4] Run `uv run pytest app/backend/tests/test_health.py -v` and confirm green.

**Checkpoint**: US4 is functional. `app/backend/tests/` now contains three committed tests — health smoke, PII redaction, OpenAPI drift — and establishes the location and fixture-usage convention every later backend task follows.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Developer-facing docs, full test run, guardrail sweep, diff audit. No new source files introduced by this phase beyond `README.md` edits.

- [X] T018 Edit `README.md` to extend the existing "Developer setup" section (added by T01) with three backend subsections, each containing a single code-fenced command block: **"Run the backend"** (`uv run uvicorn app.backend.main:app --reload`), **"Run the backend tests"** (`uv run pytest app/backend/tests/`), and **"Regenerate the OpenAPI contract"** (`uv run python -m app.backend.generate_openapi` plus a note about the `--check` flag and the drift-detection test). Do not modify any other part of `README.md` (FR-011 scope fence + FR-008 pre-existing-asset protection from T01). Reference: [quickstart.md](./quickstart.md) Steps 2–4; [contracts/backend-contract.md](./contracts/backend-contract.md) surface 1 "Producer".
- [X] T019 [P] Run the full backend test suite: `uv run pytest app/backend/tests/ -v`. Expect three tests collected and all green in < 30 s (SC-002). Record wall-clock time for inclusion in the PR description.
- [X] T020 [P] Run the T01 guardrail contract: `pre-commit run --all-files` AND `uv run ruff check app/backend` AND `uv run mypy app/backend`. All three MUST exit 0 on the post-T02 tree (SC-006, FR-012, FR-014). If `ruff-format` rewrites any T02-new file on first run, commit the rewrite and re-run to confirm idempotency.
- [X] T021 [P] Run [quickstart.md](./quickstart.md) Steps 2–6 end-to-end as the reviewer would (including the inline Python PII sanity check in Step 5). Any step that fails is a merge-blocker. Record the Step 2 boot wall-clock time for comparison against SC-001's 2-minute budget.
- [X] T022 Run the T02 diff audit: `git diff --stat origin/main..HEAD` and confirm the changed file set matches the "Expected files changed" list in [quickstart.md](./quickstart.md) Step 7. Any file outside that list (particularly: new route code, any `app/backend/llm/**`, any `app/backend/db/**`, any `alembic/**`, any `Dockerfile*`, any `docker-compose*.yml`, any `CLAUDE.md`, any `.pre-commit-config.yaml`, any ADR) is a FR-011 scope-fence violation and a merge-blocker. Document any intentional exception in the PR description.

**Checkpoint**: All four user stories land; all success criteria are satisfied (SC-001 through SC-007); the PR is ready for `reviewer` sub-agent handoff and then merge.

---

## Dependencies & Execution Order

### Phase dependencies

- **Phase 1 Setup** (T001): no dependencies.
- **Phase 2 Foundational** (T002–T006): depends on Setup. T002 blocks T003; T003 blocks T004–T006. T004, T005, T006 can be opened in any order relative to each other.
- **Phase 3 US1** (T007–T008): depends on Foundational (needs `configure_logging` from T006). T008 depends on T007.
- **Phase 4 US2** (T009–T012): depends on US1 (the generator imports `app.backend.main:app`). T010 depends on T009; T011 depends on T009 (imports `build_yaml_bytes`) and on T010 (reads the committed file); T012 depends on T011.
- **Phase 5 US3** (T013–T015): depends on Foundational (T006 created the base `configure_logging`). **Does not depend on US1** — the test uses the `captured_logs` fixture and never imports `main.py`. T014 depends on T013 (uses the redactor); T015 depends on T014.
- **Phase 6 US4** (T016–T017): depends on US1 (the `client` fixture imports `main.py`). T017 depends on T016.
- **Phase 7 Polish** (T018–T022): depends on every prior phase. T019–T021 are `[P]`; T022 is the final gate.

### User story dependencies

- **US1** and **US3** are independent — US3's test uses the structlog pipeline directly and does not traverse the FastAPI app.
- **US2** and **US4** both depend on US1 (both import `app.backend.main`).
- **US2**, **US3**, **US4** have no pairwise dependencies on each other — any order is valid.

### Within each phase

- `[P]`-marked tasks inside a phase may be opened in any order.
- Non-`[P]` tasks inside a phase are strictly sequential.

### Parallel opportunities within this task set

- **Phase 2 Foundational**: T004, T005, T006 are `[P]` — three independent files.
- **After US1 lands**: US2, US3, US4 can run in any order (single committer) or in parallel (if the team ever fans this out — not recommended for T02 per `parallel: false`).
- **Phase 7 Polish**: T019, T020, T021 are `[P]` — all are read-only validations that do not modify files.

**Constitution §18 reminder**: the `parallel: true` annotation in the implementation plan for T02 refers to T02 running concurrently with **other tasks** (T03, T04, T06 after T01 lands), not to sub-agent fan-out **inside** T02. Every task below is executed by one `backend-engineer` agent sequentially.

---

## Parallel Example: Phase 2 Foundational

Once T003 (`uv lock`) completes, the three remaining Foundational files are independent:

```bash
# Open any order — none depends on the others.
Task: "T004 — create app/backend/tests/__init__.py (empty)"
Task: "T005 — create app/backend/tests/conftest.py (client + captured_logs fixtures)"
Task: "T006 — create app/backend/logging.py (configure_logging, no PII processor yet)"
# Phase 3 (T007) can start only after all three land.
```

---

## Implementation Strategy

### Single-PR MVP (all four stories)

T02 is a single-PR task per the implementation plan. It does not ship incrementally — the acceptance clause requires `uvicorn start + /health 200 + openapi.yaml committed + regen command + PII test + health smoke test` as one set. Recommended order:

1. Complete Phase 1 Setup (T001).
2. Complete Phase 2 Foundational (T002–T006).
3. Complete Phase 3 US1 (T007–T008) — boot + `/health`.
4. Complete Phase 4 US2 (T009–T012) — OpenAPI contract + drift test.
5. Complete Phase 5 US3 (T013–T015) — PII redactor + test.
6. Complete Phase 6 US4 (T016–T017) — smoke test.
7. Complete Phase 7 Polish (T018–T022) — docs + end-to-end validation + diff audit.

Each story is still independently testable per its "Independent Test" in [spec.md](./spec.md) — a reviewer can run `pytest app/backend/tests/test_<story>.py` in isolation for any of the three test-bearing stories and get a clean pass/fail.

### Rollback posture

Every task in this list is a pure file edit or a deterministic re-runnable command (`uv lock`, `python -m app.backend.generate_openapi`, `pytest`). Reverting T02 is a single `git revert` of the T02 commit(s) — no data migration, no Cloud Run state change, no Vertex state change (§19 rollback as first-class).

### Handoff to `reviewer`

When Phase 7 is green, hand off to the `reviewer` sub-agent with: (a) `quickstart.md` as the validation script, (b) the Phase 7 T022 diff audit as the scope-fence check, (c) the T02 acceptance clause in `implementation-plan.md` as the external acceptance reference. No additional context needed.

---

## Notes

- Every `[P]` task in this file edits a different file; no task requires a sub-agent other than `backend-engineer`.
- File paths are relative to the repo root.
- Verify `quickstart.md` runs green before handing off for review.
- Commit cadence: one commit per phase is the default; larger PRs can be squashed at merge time. We commit manually (see [CLAUDE.md](../../CLAUDE.md) — `auto_commit: false`).
- Any task whose acceptance fails in a way not covered by the spec: surface the ambiguity to the user before working around it; do not silently broaden T02's scope (FR-011).
