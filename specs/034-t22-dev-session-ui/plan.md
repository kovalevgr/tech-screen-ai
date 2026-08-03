# Plan — T22 dev conversation UI

**Branch** `034-t22-dev-session-ui` · **Spec** [spec.md](./spec.md)

- **agent:** `frontend-engineer` (model: opus, policy rev. 2)
- **parallel:** true — with `033-t21-durable-trace-shell` (backend). Shared files: NONE (this stream = app/frontend/** + specs/034 only). Contract committed on the 033 branch; this branch VENDORS a read-only copy at `specs/034-t22-dev-session-ui/contract-snapshot.yaml` for reference without cross-branch dependency.
- **depends_on:** [T20] (+ runtime dependency on 033's routes, satisfied post-merge)
- **contract:** `docs/contracts/dev-session-api.yaml` (main-loop authored; canonical copy lands via 033)

## Phases

1. Spec kit + contract snapshot (verbatim main-loop artifacts).
2. API client module + types transcribed from the contract.
3. Page + components (chat thread, plan form, header, trace side panel).
4. jest tests; eslint/tsc/format gates.

## Gate plan

Frontend CI trio (eslint + tsc + jest) locally before push; no backend gates apply. No docker needed.

## Risks

- Contract drift between streams → mitigated: both artifacts authored by the same main loop in the same sitting; reviewer cross-checks the snapshot against 033's canonical copy at gate time.
