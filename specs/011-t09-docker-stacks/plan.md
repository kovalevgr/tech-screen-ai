# Implementation Plan: Docker stacks — consolidate, document, kill dead infra (T09)

**Branch**: `011-t09-docker-stacks` | **Date**: 2026-04-28 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/011-t09-docker-stacks/spec.md`

## Summary

T09 is a consolidation PR. Five concrete deliverables, no new surface:

1. **Delete dead HTTP vertex-mock infrastructure.** `Dockerfile.vertex-mock` (which copies the non-existent `tools/vertex-mock/`), the `vertex-mock` service from both compose files, the `llm` profile, and `VERTEX_MOCK_URL` from `.env.example` + compose. T04's in-process `_mock_backend.py` has been the project's Vertex mock since its merge; the HTTP layer has zero Python consumers (`git grep VERTEX_MOCK_URL --include='*.py'` returns empty), and the existing Dockerfile already fails to build because of the missing source path. Removing it is enforcement of constitution §7 (one fewer service to keep in sync) and good hygiene (speculative infrastructure with no consumer is worse than missing infrastructure).
2. **`docs/engineering/docker.md`** — the canonical Docker reference. Seven sections covering dev stack, test stack, Dockerfile targets, §7 parity, the `LLM_BACKEND` switch, resetting local state, and troubleshooting. Replaces the ad-hoc Docker explanations currently scattered across `README.md` and compose-file comments.
3. **`scripts/smoke-docker-stack.sh`** — pure bash + curl + docker compose. Brings up the documented dev stack (db + web), polls `/health` and `localhost:3000` until 200 within a 60-second budget, and tears down on EXIT trap. Returns 0 on success, 1 with a precise stderr message on any failure. T10 will wire it into CI; today it's an operator's "did I break Docker" check.
4. **`README.md` trim**: remove the standalone Docker explanation block and point at `docs/engineering/docker.md` for the deep dive. The `Quickstart (local, Docker-first)` section stays but gets one-line entries instead of paragraphs.
5. **`app/backend/llm/_mock_backend.py` docstring update**: one paragraph calling out that this IS the project's only Vertex mock; the HTTP layer was removed by T09 because no consumer ever needed it.

No new Python code, no new HTTP routes, no new dependencies, no new Dockerfile targets, no new compose services, no Alembic migration. T09 is *cleanup + documentation*. Acceptance is structural (zero hits on `git grep` for removed names), behavioural (the 138 backend tests still pass byte-identically), and reviewer-facing (a new contributor brings the stack up from the new docs alone in <5 min).

Single committer — `agent: infra-engineer`, `parallel: false`. The PR is small enough to commit in two or three logical groups, not the four-or-more pattern T05/T05a/T08 used.

## Technical Context

**Language/Version**: N/A — T09 ships no Python code beyond a one-paragraph docstring update.

**Primary Dependencies**: No new dependency in `pyproject.toml` or `uv.lock`. The smoke script uses `bash`, `curl`, and `docker compose` — all present on any developer / CI machine that can run the rest of the project.

**Storage**: No DB change. The `feature_flag` and `rubric_tree_version` tables introduced in T05/T05a/T08 are untouched.

**Testing**: T09 is verified by:
- The existing 138-test backend suite, which MUST pass byte-identically inside the test stack post-T09 (FR-007 / SC-004). This is the de-facto regression test for the consolidation.
- The new smoke script, which exercises the dev stack end-to-end (FR-006 / SC-003).
- Static checks: `git grep -nE "vertex-mock|VERTEX_MOCK_URL|tools/vertex-mock|Dockerfile\.vertex-mock"` returns zero hits on the post-T09 tree (excluding `specs/011-t09-docker-stacks/`, which legitimately discusses the removal).
- `docker compose config --profiles` lists `db`, `web`, `full` only (no `llm`).
- The existing pre-commit hook chain (T05a + T08 + ruff + mypy + gitleaks + detect-secrets + actionlint) passes on the post-T09 tree.

**Target Platform**: Linux container (existing Dockerfile dev target). macOS host for the smoke script (which runs Docker Compose against the local Docker Desktop). CI runs the same in GitHub Actions Linux runners (T10).

**Project Type**: Infrastructure consolidation. No application slice.

**Performance Goals**:
- Smoke script wall time on a warm Docker cache: < 60 seconds total (FR-006 / SC-003).
- Dev stack cold bring-up on a clean clone: < 5 minutes including image build (SC-001).
- No regression in test-suite wall time (current ~10 seconds for the full backend suite).

**Constraints**:
- **§7 Docker parity** — the same image (Dockerfile `dev` target) is used by the backend service in both `docker-compose.yml` and `docker-compose.test.yml`; the consolidation must not break this. Documented in `docs/engineering/docker.md` § 4.
- **§5 No plaintext secrets** — no new secret. The `VERTEX_MOCK_URL` removal does not affect any secret material (it carried only the literal `http://vertex-mock:8080`).
- **§16 Configs as code** — `docker-compose.yml` and `docker-compose.test.yml` are themselves configs-as-code; the post-T09 state is their canonical truth.
- **§17 Specs precede implementation** — this spec is the trigger.
- **§18 Multi-agent orchestration is explicit** — single committer (`infra-engineer`), `parallel: false`. No sub-agent fan-out.
- **Existing pre-commit hooks** — must all pass on the post-T09 tree. `actionlint` runs on any `.github/workflows/*.yml`; we ship no workflow changes in T09, but the hook still runs.
- **OpenAPI diff is zero** — no backend route added; `python -m app.backend.generate_openapi --check` exits 0.
- **138 tests remain green** — non-negotiable acceptance criterion (FR-007 / SC-004).

**Scale/Scope**: One PR, 1 file deleted, 5 files edited, 2 files created. ~150 net lines of new content (the doc + the script); the deletions are larger than the additions in absolute line count.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| §   | Principle                              | Applies to T09?                                                                                                                                                                | Status |
| --- | -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------ |
| 1   | Candidates and reviewers come first    | Indirect — a stable, reproducible Docker stack is a substrate for every later auditability claim (every later test that proves the audit invariants runs in this stack).        | Pass   |
| 2   | Deterministic orchestration            | N/A — no LLM in T09.                                                                                                                                                            | N/A    |
| 3   | Append-only audit trail                | N/A — no DB change.                                                                                                                                                             | N/A    |
| 4   | Immutable rubric snapshots             | N/A — no rubric change.                                                                                                                                                          | N/A    |
| 5   | No plaintext secrets                   | Yes — no secret added; removes a non-secret env var. `gitleaks` / `detect-secrets` pass on the diff.                                                                            | Pass   |
| 6   | Workload Identity Federation only      | N/A — no GCP auth change.                                                                                                                                                       | N/A    |
| 7   | Docker parity dev → CI → prod          | **Primary purpose of T09.** The consolidation is the §7 enforcement. The canonical diff between the two compose files is documented in `docs/engineering/docker.md` § 4.        | Pass   |
| 8   | Production-only topology               | Indirect — `docs/engineering/docker.md` § 5 (LLM_BACKEND switch) makes explicit that prod refuses `LLM_BACKEND=mock` at startup (T04's existing safeguard).                       | Pass   |
| 9   | Dark launch by default                 | N/A — no new behaviour to flag.                                                                                                                                                  | N/A    |
| 10  | Migration approval                     | N/A — no migration in T09.                                                                                                                                                       | N/A    |
| 11  | Hybrid language                        | Yes — the new docs and the smoke script are English; no candidate-facing text.                                                                                                  | Pass   |
| 12  | LLM cost and latency caps              | N/A — no LLM call.                                                                                                                                                               | N/A    |
| 13  | Calibration never blocks merge         | N/A.                                                                                                                                                                             | N/A    |
| 14  | Contract-first for parallel work       | Yes — the two compose files + the new docs file + the smoke script form the contract that T10 (CI) will bind to.                                                                | Pass   |
| 15  | PII containment                        | Yes — no PII added; the smoke script logs only HTTP status codes and service names.                                                                                              | Pass   |
| 16  | Configs as code                        | Yes — the post-T09 compose files are the canonical truth.                                                                                                                        | Pass   |
| 17  | Specifications precede implementation  | Yes — `speckit-specify` → this `speckit-plan`; implementation follows `speckit-tasks`.                                                                                          | Pass   |
| 18  | Multi-agent orchestration is explicit  | Yes — `agent: infra-engineer`, `parallel: false`.                                                                                                                                | Pass   |
| 19  | Rollback is a first-class operation    | Indirect — `git revert` of T09 cleanly restores the dead infrastructure (we'd not want it back, but it's reversible).                                                            | Pass   |
| 20  | Floor, not ceiling                     | Pass.                                                                                                                                                                            | Pass   |

**Gate result**: PASS. No violations. Complexity Tracking stays empty.

## Project Structure

### Documentation (this feature)

```text
specs/011-t09-docker-stacks/
├── spec.md                                # Feature spec (speckit-specify)
├── plan.md                                # This file
├── research.md                            # Phase 0 — 10 implementation-altitude decisions (most pre-resolved by user input)
├── data-model.md                          # Phase 1 — operational entities (no DB)
├── contracts/
│   └── plan-contract.md                   # Phase 1 — pointer to runtime artefacts at the repo root
├── quickstart.md                          # Phase 1 — reviewer validation walkthrough (<10 min)
├── checklists/
│   └── requirements.md                    # From speckit-specify (passed)
└── tasks.md                               # Created by speckit-tasks (NOT this command)
```

### Source Code / config (repository root, after T09 merges)

```text
.
├── Dockerfile                              # untouched
├── Dockerfile.frontend                     # untouched (T03 ownership)
├── Dockerfile.vertex-mock                  # DELETED — references non-existent tools/vertex-mock/; superseded by T04's in-process mock
├── docker-compose.yml                      # EDITED — remove vertex-mock service + llm profile + VERTEX_MOCK_URL; update profile docs in header
├── docker-compose.test.yml                 # EDITED — same removals
├── .env.example                            # EDITED — remove VERTEX_MOCK_URL entry
├── README.md                               # EDITED — trim Docker explanation; point at docs/engineering/docker.md
├── docs/
│   └── engineering/
│       └── docker.md                       # NEW — canonical Docker reference (7 sections per spec FR-004)
├── scripts/
│   └── smoke-docker-stack.sh               # NEW — bash smoke script (executable; FR-006)
└── app/
    └── backend/
        └── llm/
            └── _mock_backend.py            # EDITED — one-paragraph docstring update (FR-009)
```

**Structure Decision**: All edits are at the repo root or in pre-existing directories. No new directories. `docs/engineering/docker.md` joins its siblings (`feature-flags.md`, `cloud-setup.md`, `directory-map.md`, `anti-patterns.md`, `testing-strategy.md`, etc.). `scripts/smoke-docker-stack.sh` lives alongside `check-rubric-schema.py` and `check-feature-flag-registration.py` from T05a/T08 — already copied into the test image by the T05 Dockerfile fix (`COPY scripts ./scripts`).

### Task labelling (for §18 / `/speckit-tasks`)

| Task slice                                                                | Agent              | Parallel? | Depends on                            | Contract reference                |
| ------------------------------------------------------------------------ | ------------------ | --------- | ------------------------------------ | --------------------------------- |
| Delete `Dockerfile.vertex-mock`                                          | `infra-engineer`   | false     | spec committed                       | spec FR-002                       |
| Edit `docker-compose.yml` (remove service + profile + envvar)            | `infra-engineer`   | false     | spec committed                       | spec FR-001 / FR-003              |
| Edit `docker-compose.test.yml` (same)                                    | `infra-engineer`   | false     | spec committed                       | spec FR-001 / FR-003              |
| Edit `.env.example` (remove VERTEX_MOCK_URL)                             | `infra-engineer`   | false     | spec committed                       | spec FR-003                       |
| Edit `app/backend/llm/_mock_backend.py` (docstring update)               | `infra-engineer`   | false     | spec committed                       | spec FR-009                       |
| Create `docs/engineering/docker.md` (the canonical reference)            | `infra-engineer`   | false     | spec committed                       | spec FR-004                       |
| Edit `README.md` (trim Docker explanation; link to new doc)              | `infra-engineer`   | false     | docs/engineering/docker.md exists    | spec FR-005                       |
| Create `scripts/smoke-docker-stack.sh` (executable bash smoke)           | `infra-engineer`   | false     | post-edit compose files               | spec FR-006                       |
| Run guardrails + smoke + full test suite + static greps                   | `infra-engineer`   | false     | everything above                     | spec SC-001..SC-008               |

All T09 slices are sequential inside one PR; no sub-agent fan-out. The parallelism boundary is "T09 as a whole → afterwards, T10 (CI) can plug into the smoke script and the documented contract".

## Phase 0 — Outline & Research

Research output: [research.md](./research.md). 10 implementation-altitude decisions; most pre-resolved by the user input. Each carries Decision / Rationale / Alternatives Considered (or "Deferred — owned by Tx").

1. **Vertex-mock A vs B** — RESOLVED → **Option A (REMOVE)**. Zero Python consumers (verified via `git grep`); T04's in-process `_mock_backend.py` covers all test paths; §7 parity wins by simplification; speculative-infrastructure-with-no-consumer is worse than missing-infrastructure.
2. **Smoke-script shape** — RESOLVED → pure bash + curl + docker compose. Zero new dep beyond what's already on the host. `set -euo pipefail`; `trap` for cleanup; clear stderr on failure.
3. **Smoke timing budget** — RESOLVED → 60 s total (Postgres healthcheck is 5 s × 10 retries = 50 s ceiling; backend is 10 s × 10 retries = 100 s but typically reaches healthy in <30 s; frontend is fastest at <5 s). Per-poll: 2 s curl timeout; 1 s sleep; max 30 iterations per service.
4. **`docs/engineering/docker.md` location and structure** — RESOLVED → alongside `feature-flags.md` / `cloud-setup.md` / `directory-map.md`; 7 sections (per spec FR-004).
5. **e2e service in test compose** — RESOLVED → unchanged; T09 confirms it builds but does not modify (out of scope per Out-of-Scope §).
6. **`Dockerfile.frontend` references vertex-mock** — to verify with `git grep`; if empty (expected), no edit. RESOLVED → check then leave.
7. **`docker compose down -v` helper script** — RESOLVED → no; document the one-liner in `docker.md` § 6.
8. **Pre-commit hooks in container** — DEFERRED → T10 owns the workflow decision; T09 leaves host-based hooks unchanged.
9. **Workflow integration for the smoke script** — DEFERRED → T10 plumbing.
10. **Merging `Dockerfile.frontend` into the root `Dockerfile`** — DEFERRED → out of T09 scope; would require multi-context build changes.

## Phase 1 — Design & Contracts

**Prerequisites**: `research.md` complete.

### Data model

See [data-model.md](./data-model.md). T09 has no DB entities; data-model.md describes *operational* entities: the dev-stack profile set, the test-stack profile set, the Dockerfile-target matrix, the smoke-script exit-code contract, the canonical-diff line-set between the two compose files. This is the document a reviewer can grep against the post-T09 compose files to verify consolidation.

### Contracts

See [contracts/plan-contract.md](./contracts/plan-contract.md). T09's contract artefacts ARE the runtime artefacts at the repo root:
- `docker-compose.yml` + `docker-compose.test.yml` — the two compose contracts.
- `Dockerfile` (`builder` / `dev` / `runtime` targets) — the image contract.
- `scripts/smoke-docker-stack.sh` — the bash smoke contract (exit-code shape).
- `docs/engineering/docker.md` — the human-readable contract.

The spec-dir `contracts/plan-contract.md` is a pointer doc.

### Quickstart

See [quickstart.md](./quickstart.md) — reviewer-facing <10-min walkthrough: grep for dead refs (expect empty); bring up dev stack; `curl /health` and `curl :3000`; run `scripts/smoke-docker-stack.sh`; run full test suite (138 passed); run `pre-commit run --all-files` (clean); confirm `docker compose config --profiles` lists exactly the documented set.

### Agent context update

`CLAUDE.md` carries no `<!-- SPECKIT START/END -->` markers (verified earlier across T05/T05a/T08). No auto-generated block is reintroduced. **No `CLAUDE.md` edit in this step.**

### Re-evaluate Constitution Check (post-design)

Phase 0/1 commitments (Option A, bash smoke script, 60 s budget, docs location, 7-section structure) are all consistent with §5/§7/§11/§16/§17/§18. Gate remains **PASS**.

## Complexity Tracking

Not applicable — no Constitution Check violations.

| Violation | Why Needed | Simpler Alternative Rejected Because |
| --------- | ---------- | ------------------------------------ |
| *(none)*  | —          | —                                    |
