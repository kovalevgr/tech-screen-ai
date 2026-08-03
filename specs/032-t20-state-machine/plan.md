# Plan — T20 Interview Orchestrator State Machine

**Branch**: `032-t20-state-machine` · **Spec**: [spec.md](./spec.md) · **Contract**: `docs/contracts/state-machine.md` (v1.1)

- **agent:** `backend-engineer` (model: opus per CLAUDE.md §Sub-agent model policy rev. 2)
- **parallel:** false (T21/T22 fan out only after this merges)
- **depends_on:** [T18, T19]
- **contract:** `docs/contracts/state-machine.md` — committed as the branch's first substantive commit (§14); spec kit authored by the main loop, committed verbatim before implementation.

## Phases

1. **Policy prelude** (done by main loop, commit `687edaf`): CLAUDE.md v1.3 + agent frontmatter `model: opus`.
2. **Contract + spec kit** (verbatim from main loop): `docs/contracts/state-machine.md`, `specs/032-t20-state-machine/{spec,plan,tasks}.md`.
3. **Core**: `app/backend/orchestrator/{__init__,state_machine,plan,config}.py` + `configs/orchestrator.yaml`.
4. **Persistence**: `orchestrator/persistence.py`, alembic migration `interview_session.session_state JSONB NULL`, `InterviewSession` mapping.
5. **Tests**: `app/backend/tests/orchestrator/` — transition-table suite (21 named edges), adjudication matrix, determinism/round-trip, static purity guards, DB-gated persistence.

## Source tree (new)

```
app/backend/orchestrator/           __init__.py (docstring only), state_machine.py, plan.py, config.py, persistence.py
configs/orchestrator.yaml
alembic/versions/000?_add_session_state_column.py
app/backend/tests/orchestrator/     __init__.py (0 bytes), conftest.py, test files per plan §5
specs/032-t20-state-machine/        spec.md, plan.md, tasks.md
docs/contracts/state-machine.md
```

## Gate plan

pytest / ruff check / ruff format --check / mypy --strict / check-no-provider-sdk-imports.sh — all green before push. Real-Postgres migration cycle is run by the main loop if Docker is unavailable in the agent sandbox (SC-3).

## Risks

- Biggest logic surface of Tier 3 → mitigated by the normative transition table + per-edge named tests + reviewer §2 greps.
- State-schema evolution → `state_schema_version` inside the JSON; unknown version fails loudly on load (no silent migration).
