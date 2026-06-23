---
description: "Task list for T09 — Docker stacks consolidation, dead-infra removal, documentation"
---

# Tasks: Docker stacks (T09)

**Input**: Design documents from `specs/011-t09-docker-stacks/`
**Prerequisites**: spec.md, plan.md, research.md, data-model.md, contracts/plan-contract.md, quickstart.md

**Tests**: NOT included as new pytest files — T09 ships no new Python code beyond a docstring. Verification is (a) the existing 138-test backend suite passing byte-identically inside the test stack, (b) the new bash smoke script, (c) static `git grep` checks for removed names. All three are tasks in the Polish phase.

**Agent / parallelism**: every task is `agent: infra-engineer`, executed sequentially in one PR. `[P]` marks tasks that touch *different files*; it does NOT authorise sub-agent fan-out (constitution §18 — `parallel: false` for T09 as a whole).

**Phase ordering rationale**: phase numbers below reflect EXECUTION ORDER (not user-story priority order), because the file-ordering invariant requires the dead-infra removal (US3) to land BEFORE the smoke script (US1) can assert services come up cleanly. Story labels still trace each task to its spec.md user story.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup

No setup needed. T09 ships no new Python dep; `pyproject.toml` and `uv.lock` are untouched.

---

## Phase 2: Foundational

No foundational phase. T09 has no blocking-prerequisite phase; every story task can execute directly once the previous phase's invariant holds.

---

## Phase 3: User Story 3 — Dead infrastructure removal (Priority: P1) 🎯 EXECUTION-FIRST

**Goal**: Delete every reference to the HTTP `vertex-mock` — the broken Dockerfile, the unused compose service, the dangling env var, the dead profile.

**Independent Test**: After Phase 3, `git grep -nE "vertex-mock|VERTEX_MOCK_URL|tools/vertex-mock|Dockerfile\.vertex-mock" -- ':!specs/011-t09-docker-stacks/'` returns empty (exit 1). `docker compose config --profiles | sort` returns `db / full / web` (no `llm`).

**Why execution-first (despite priority being equal to US1/US2)**: The smoke script (US1) and the test-stack regression (US2) both depend on the compose files being free of the dead `vertex-mock` service block (which would otherwise fail to build because `Dockerfile.vertex-mock` copies a non-existent path). US3 deletions are therefore a hard prerequisite for the verifications later in the PR.

### Implementation for User Story 3

- [x] T001 [US3] Delete `Dockerfile.vertex-mock` from the repository root. The file copies a non-existent `tools/vertex-mock/` directory and has no consumer (FR-002).
- [x] T002 [US3] Edit `docker-compose.yml`: remove the entire `vertex-mock:` service block; remove `vertex-mock` from the `llm`/`full` profile membership; remove the `llm` profile entirely; remove the `VERTEX_MOCK_URL: http://vertex-mock:8080` env line from the `backend:` service block; update the file-leading comment block to reflect the new profile set (`db`, `web`, `full` only — `db` adds Postgres; `web` adds frontend; `full` = `db` + `web`). (FR-001, FR-003)
- [x] T003 [US3] Edit `docker-compose.test.yml`: remove the entire `vertex-mock:` service block; remove `vertex-mock` from the `llm`/`full` profile membership; remove the `llm` profile entirely; remove `VERTEX_MOCK_URL: http://vertex-mock:8080` from the `backend:` service env; update the file-leading comment block to reflect the new profile set (`db`, `e2e`, `full`). (FR-001, FR-003)
- [x] T004 [P] [US3] Edit `.env.example`: remove the entire `VERTEX_MOCK_URL=http://vertex-mock:8080` block including any surrounding comments. (FR-003)
- [x] T005 [P] [US3] Update the docstring of `app/backend/llm/_mock_backend.py` (one paragraph at the top of the module): call out that this is the project's ONLY Vertex mock; the HTTP layer was removed by T09 because no consumer ever needed it; future HTTP isolation, if ever required, would land as a new task with a real consumer. (FR-009)
- [x] T006 [US3] Verify (interactive): `git grep -nE "vertex-mock|VERTEX_MOCK_URL|tools/vertex-mock|Dockerfile\.vertex-mock" -- ':!specs/011-t09-docker-stacks/'` returns no matches. If it does, finish the cleanup before moving on. (SC-002)

**Checkpoint**: dead infrastructure is gone; the compose files are buildable; the smoke script and the test-stack regression can now meaningfully run.

---

## Phase 4: User Story 1 — Clean-clone dev bring-up (Priority: P1)

**Goal**: A new contributor brings up the full dev stack with one documented command and observes 200 from backend `/health` and frontend root. A bash smoke script (FR-006) automates the same check.

**Independent Test**: `docker compose --profile db --profile web up -d --build` succeeds; `curl localhost:8000/health` returns 200; `curl localhost:3000/` returns 200; `scripts/smoke-docker-stack.sh` exits 0.

### Implementation for User Story 1

- [x] T007 [US1] Create `scripts/smoke-docker-stack.sh` (executable, `chmod +x`). Pure bash + `curl` + `docker compose`; `set -euo pipefail`; `trap` for tear-down. Flow per research §2: bring up `--profile db --profile web` with `--build`; poll `localhost:8000/health` until 200 (max 30 × 2s curl + 1s sleep); poll `localhost:3000/` similarly; tear down on EXIT; clear stderr message + exit 1 on failure; exit 0 on success. (FR-006, SC-003)

### Tests for User Story 1

- [x] T008 [US1] Run `bash scripts/smoke-docker-stack.sh` against the local Docker; verify exit 0; verify the dev stack was torn down at the end (no lingering `techscreen-dev-*` containers). (SC-003)

**Checkpoint**: dev stack works end-to-end; the smoke script proves it programmatically.

---

## Phase 5: User Story 4 — Single docs source (Priority: P2)

**Goal**: A new contributor reads one file (`docs/engineering/docker.md`) and can answer five concrete questions about the Docker contract without consulting other files (SC-005). README is trimmed to a single short paragraph that points at the new doc.

**Independent Test**: A reviewer opens `docs/engineering/docker.md` and finds the seven documented sections, and the README's Docker section is one paragraph long with a link.

### Implementation for User Story 4

- [x] T009 [US4] Create `docs/engineering/docker.md` per plan §Phase 1 / data-model.md §3 / spec FR-004. Seven sections: (0) Why this doc exists; (1) Dev stack (profiles, commands, hot-reload); (2) Test stack (commands, no-DB skip path, e2e); (3) Dockerfile targets (builder/dev/runtime); (4) §7 parity guarantee + the canonical-diff table from data-model.md §5; (5) `LLM_BACKEND` switch (mock/vertex + the prod-refuse-mock startup check from T04); (6) Resetting local state (`down` vs `down -v`); (7) Troubleshooting (rebuild after pyproject change; postgres-data volume; port conflicts). Cross-link to `specs/011-t09-docker-stacks/` for the T09 history. (FR-004)
- [x] T010 [US4] Edit `README.md`: replace the Docker explanation paragraphs (anywhere they appear — likely in the `Stack` and `Quickstart (local, Docker-first)` sections) with a single short paragraph that lists the canonical bring-up command and links to `docs/engineering/docker.md` for the deep dive. Remove any remaining `vertex-mock` references. (FR-005)

**Checkpoint**: a new contributor has exactly one place to learn the Docker contract.

---

## Phase 6: User Story 2 — Dev ↔ CI parity (Priority: P1)

**Goal**: The same image runs in dev and in the test stack; the 138-test backend suite passes byte-identically inside the test stack after the consolidation (FR-007, SC-004).

**Independent Test**: `docker compose -f docker-compose.test.yml --profile db run --rm backend sh -c "alembic upgrade head && pytest app/backend/tests"` → 138 passed; the no-DB skip path still skips cleanly.

### Tests for User Story 2

- [x] T011 [US2] Run the full backend test suite inside the test stack (with `db` profile): `docker compose -f docker-compose.test.yml --profile db run --rm backend sh -c "alembic upgrade head && pytest app/backend/tests -v"`. Assert: 138 passed (or higher if newer tests were added on `main` between branch creation and now). (SC-004 / FR-007)
- [x] T012 [US2] Run the no-DB skip path: `docker compose -f docker-compose.test.yml run --rm -e DATABASE_URL= backend pytest app/backend/tests/cli app/backend/tests/db app/backend/tests/services -q --no-header`. Assert: skips that should skip do skip; passes that don't need DB pass.

**Checkpoint**: §7 parity is empirically proven on the post-T09 tree.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [x] T013 [P] Run guardrails: `docker compose -f docker-compose.test.yml run --rm backend ruff check app/backend` + `ruff format --check app/backend alembic scripts` + `mypy --strict app/backend`. Run `docker compose -f docker-compose.test.yml run --rm backend python -m app.backend.generate_openapi --check` (byte-identical — no route added, SC-007). Run `pre-commit run --all-files` on the host (all existing hooks pass, SC-006).
- [x] T014 Walk through `quickstart.md` § 1–§ 10 end-to-end; tick each SC-001..SC-008 box in the checklist at the bottom of the quickstart. If any step diverges from expected, fix before proceeding to commit.

---

## Dependencies & Execution Order

### Phase dependencies
- **Setup (P1)** → empty for T09.
- **Foundational (P2)** → empty for T09.
- **US3 deletions (P3)** → must execute first (T001 → T006). T002 / T003 / T004 / T005 touch different files (T004 and T005 are `[P]`); T006 (grep verification) must come last in the phase.
- **US1 smoke (P4)** → depends on US3 (compose files no longer reference a non-existent build path).
- **US4 docs (P5)** → T010 (README edit) depends on T009 (docker.md exists); the docs phase can run in parallel with US1 / US2 in principle, but we serialise for review clarity.
- **US2 regression (P6)** → depends on US3 (compose edits are settled).
- **Polish (P7)** → after every story.

### Story independence
- US3 (deletions) is the prerequisite root.
- US1 / US2 / US4 can be reordered freely after US3, but the chosen order minimises rework: US1 (smoke) proves dev works; US4 (docs) documents the contract once it's stable; US2 (regression) is the final no-regression gate.

### Parallel opportunities (file-level, single committer)
- T004 ∥ T005 (different files; both within US3).
- T009 ∥ T013 in principle, but T013 should run last after every file edit to catch lint regressions.
- Never parallel: any two edits to the same compose file (T002 alone, T003 alone); the docs+README pair (T009 → T010 strictly sequential since T010 links to T009).

---

## Implementation Strategy

### MVP first (Phase 3 deletions)
1. Phase 3 — every dead reference removed; `git grep` empty; the broken `Dockerfile.vertex-mock` deleted.
2. **STOP and VALIDATE**: re-run the dev stack manually (`docker compose --profile db --profile web up -d --build`) and confirm it still comes up.

### Incremental delivery
1. Phase 3 — deletions land first. Compose files now buildable end-to-end.
2. Phase 4 — smoke script exists and exits 0. Dev bring-up is provably automatic.
3. Phase 5 — docs land. New contributors can self-serve.
4. Phase 6 — regression suite passes inside the test stack (no T04/T05/T05a/T08 test was harmed by the consolidation).
5. Phase 7 — guardrails + quickstart sweep.

### Suggested commit grouping (manual commits, our norm)
- `chore(T09): remove dead HTTP vertex-mock infrastructure` (T001–T006)
- `feat(T09): bash smoke script + docs/engineering/docker.md` (T007, T009, T010)
- `docs(T09): _mock_backend.py docstring + README trim + tasks complete` (T005 docstring + T010 README done above; this commit only marks tasks.md done)
- `test(T09): full backend suite passes in the test stack; guardrails green` (T011–T014 — actually these are verifications, no commits required; document the results in the gate report)

---

## Notes
- `[P]` = different files, no ordering hazard; NOT sub-agent fan-out (§18).
- T09 ships **no new Python code** (only a docstring update on `_mock_backend.py`). The 138-test suite is the regression gate.
- The smoke script (T007) is the only new file beyond docs. T10 (CI workflow) will wire it into `.github/workflows/ci.yml` later.
- Phase numbering reflects execution dependency order, not user-story priority order (US3 deletions execute before US1's smoke verification by necessity).
