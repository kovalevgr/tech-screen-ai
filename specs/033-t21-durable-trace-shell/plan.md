# Plan — T21 durable trace/cost + dev-session shell

**Branch** `033-t21-durable-trace-shell` · **Spec** [spec.md](./spec.md)

- **agent:** `backend-engineer` (model: opus, policy rev. 2)
- **parallel:** true — with `034-t22-dev-session-ui` (frontend). Shared files: NONE (this stream owns app/backend/**, alembic, configs, openapi.yaml; the UI stream owns app/frontend/** only). Contracts committed first per §14.
- **depends_on:** [T04, T05, T05a, T20]
- **contract:** `docs/contracts/turn-trace.schema.json` + `docs/contracts/dev-session-api.yaml` (both main-loop authored, committed verbatim as this branch's first commit)

## Phases

1. Contracts + spec kit (verbatim main-loop artifacts).
2. Migration: turn_trace rich columns + two flag-seed rows; `configs/llm-limits.yaml`.
3. `app/backend/llm/persistent_trace.py` (PostgresTraceSink) + `persistent_cost.py` (PostgresCostLedger) — new modules implementing the T04 protocols; no edits inside existing llm modules.
4. Shell: `services/dev_session.py` (command executor, ordering per 032-Clar.4) + `api/dev_sessions.py` (contract routes, flag+role gating) + openapi regen.
5. Tests: trace persistence (incl. §3 still enforced), ledger + ceiling matrix (flag off/on), shell e2e vs mock backend, ordering (persist-before-call), background assessor feedback loop, gating (flag off → 404; role enforcement).

## Gate plan

pytest (both DB modes, throwaway Postgres like T20 did — clean up containers), ruff ×2, mypy --strict, sdk-import guard, openapi regen check, live migration cycle.

## Risks

- Async plumbing (background assessor → transition) — mitigated by SC-3 e2e and the machine's own §6.9a guards.
- §3 regression — explicit UPDATE/DELETE test on the widened table.
