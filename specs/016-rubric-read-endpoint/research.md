# Research: Rubric read endpoint

Phase 0 decisions (small task — concise).

## §1 — Reuse `snapshot_rubric` + `RubricSnapshot` as the response (no new shape)

- **Decision**: The endpoint returns `RubricSnapshot` (T15) produced by `snapshot_rubric(conn, active_version_id)`. The committed contract is the existing `docs/contracts/rubric-snapshot.schema.json`.
- **Rationale**: The active-rubric tree is structurally identical to a session's frozen snapshot; reusing the model + contract avoids a duplicate shape and means T14 consumes one rubric-tree type everywhere. Semantically a live read returns "the current snapshot of the active version" — accurate enough.
- **Alternatives**: a dedicated `RubricView` model — rejected (needless duplication of an identical shape).

## §2 — Active-version selection

- **Decision**: `SELECT id FROM rubric_tree_version WHERE is_active = true LIMIT 1`. If no row → return `None` → endpoint 404.
- **Rationale**: `is_active` is the app-maintained "current version" flag (T05/T08). At most one is active. `LIMIT 1` is defensive against an unexpected multi-active state (returns a deterministic one rather than erroring).

## §3 — No §9 feature flag

- **Decision**: No flag. Router-level dependency is just `require_roles("recruiter", "admin")`.
- **Rationale**: Read-only view of internal config — no candidate exposure, no data mutation, no Vertex cost. §9 targets risky features; this is not one. (Confirmed at the plan gate.)

## §4 — Auth seam reuse + session/connection

- **Decision**: Reuse the T13 seam: `get_current_user` + `require_roles("recruiter","admin")` (overridable in tests). The endpoint takes `SessionDep`, gets the connection via `await session.connection()`, and calls the snapshot helper. No new flag dependency.
- **Rationale**: Consistent with the position-template router; `snapshot_rubric` already takes an `AsyncConnection`.

## §5 — `get_active_rubric_snapshot` helper

- **Decision**: Add `get_active_rubric_snapshot(conn) -> RubricSnapshot | None` to `services/rubric_snapshot.py`: find the active version, return `snapshot_rubric(conn, id)` or `None`. The router maps `None` → 404.
- **Rationale**: Keeps the router thin and the resolve-active logic unit-testable next to `snapshot_rubric`.

## §6 — OpenAPI regenerate-then-check

- **Decision**: After the route lands, regenerate `openapi.yaml` (adds `/rubric/active` + the `RubricSnapshot` component family FastAPI derives from the response_model) and confirm `--check` + `test_openapi_regeneration` are green; commit it.
- **Rationale**: §14 — the committed contract is what T14's `openapi-typescript` client consumes.

## Open follow-ups (out of scope)

- `GET /rubric/{version_id}` for the Rubric Browser (screen 15) — future.
- Position Template admin UI — **T14** (next).
