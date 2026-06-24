# Research: Position Template CRUD endpoints (T13)

Phase 0 decisions.

## §1 — Persistence: AsyncSession + ORM; validator via `session.connection()`

- **Decision**: The `get_db` dependency yields an `AsyncSession` from the existing `db/session.py` `get_sessionmaker()`. Writes use the T12 ORM models (`PositionTemplate`, `PositionTemplateStack`, `PositionTemplateCompetency`). The T12 stateful validator is `validate_position_template(conn: AsyncConnection, ...)`; call it with `await session.connection()` so it runs inside the same transaction. Reads/list assemble the `PositionTemplateRead` shape with explicit `select()`s (template row + its stack/competency association rows) rather than ORM relationships.
- **Rationale**: `db/session.py` is built around `AsyncSession`, so that is the app-layer convention. The ORM models already exist (T12), making inserts of the parent + association rows clean and atomic within one session transaction. Calling the validator on `session.connection()` reuses T12's exact Core-SQL rules without duplicating them. Explicit selects for the read shape avoid async lazy-loading pitfalls and need no `relationship()` additions to the T12 models (no model change).
- **Alternatives considered**: (a) Core SQL / `AsyncConnection` throughout (matches T12 tests) — rejected: the app session factory yields `AsyncSession`, and ORM inserts of the association rows are cleaner. (b) Add `relationship()` to the models and lazy-load — rejected: async lazy-load requires `await`-aware access and selectin loading; explicit selects are simpler and more predictable for a 5-endpoint CRUD.

## §2 — Authorization seam (real SSO deferred to T07)

- **Decision**: Add `app/backend/api/deps.py` with:
  - a `Principal` model (`user_id: UUID | None`, `role: str`),
  - `get_current_user()` — the seam. Until T07 wires Identity Platform, the default implementation resolves no identity and raises **401**. It is a FastAPI dependency, so tests override it (`app.dependency_overrides`) to inject a recruiter / admin / other / anonymous principal.
  - `require_roles(*roles)` — depends on `get_current_user`; raises **403** if the principal's role is not in the allowed set.
- **Rationale**: T07 (real SSO + role claims) is blocked on a live GCP project. The seam lets T13 fully build and test the authorization *gate* (role enforcement, 401 vs 403) now, with T07 later swapping the identity source behind the same dependency. Default-401 means the surface is safely dark in any environment without auth wired — consistent with §9's dark-by-default posture.
- **Alternatives considered**: (a) skip authz entirely until T07 — rejected: the spec (FR-008) requires the gate, and retrofitting authz across endpoints later is error-prone. (b) trust a plaintext header for role in prod — rejected: insecure; the seam stays closed (401) until T07 provides a verified identity.

## §3 — Router + get_db wiring (first router in the app)

- **Decision**: New `app/backend/api/` package. `position_templates.py` defines an `APIRouter(prefix="/position-templates", tags=["position-templates"])`; `main.py` calls `app.include_router(...)`. `get_db` is an async generator dependency: open a session from the sessionmaker, `yield`, `commit` on success / `rollback` on exception, always `close`.
- **Rationale**: No router exists yet (only `/health` on the app). This establishes the convention the rest of Tier 2+ follows. Request-scoped session with commit/rollback is the standard FastAPI + SQLAlchemy-async pattern.
- **Alternatives considered**: registering routes directly on `app` (like `/health`) — rejected: doesn't scale; a router package is the right seam for T14+ and future endpoints.

## §4 — PATCH semantics: partial fields, wholesale selection replace

- **Decision**: A new `PositionTemplateUpdate` Pydantic model with **all fields optional**. Only provided fields are applied. If `stack_ids` and/or `competency_ids`/`must_have_competency_ids` are provided, the corresponding association set is **replaced wholesale** (delete existing association rows for the template, insert the new set) inside the transaction; then re-run validation on the resulting full state.
- **Rationale**: Element-level merge of selection lists is ambiguous (how to express "remove one"?). Replace-the-set is unambiguous and matches how the create body already expresses selections. Re-validating the resulting state keeps FR-003/006 invariants true after edits.
- **Alternatives considered**: JSON-Merge-Patch / per-element add-remove — rejected as over-complex for an admin CRUD MVP.

## §5 — Error → HTTP status mapping

- **Decision**:
  - Pydantic request validation failure → **422** (FastAPI default).
  - `PositionTemplateValidationError` (stateful: unknown stack, competency-not-in-stack) → **422** (mapped via an exception handler or in-router try/except).
  - Unknown id on read/patch/delete → **404**.
  - Unauthenticated → **401**; wrong role → **403** (from the auth seam).
  - Successful create → **201**; read/list/patch → **200**; archive (delete) → **200** (returns the archived template) or **204**; choose **200 + body** so the client sees the archived state.
- **Rationale**: Conventional REST semantics; keeps the contract predictable for T14.

## §6 — OpenAPI: regenerate-then-check (completes Variant A)

- **Decision**: After the router lands, run `python -m app.backend.generate_openapi` to **write** `openapi.yaml` (now containing the `/position-templates` paths + the component schemas FastAPI derives from `PositionTemplateCreate/Read/Update`), commit it, and ensure `python -m app.backend.generate_openapi --check` + `test_openapi_regeneration` pass.
- **Rationale**: T12 deferred the paths (Variant A); they materialise here because the routes now exist. The drift check guarantees the committed contract matches the implementation (§14) — this is the artefact T14's `openapi-typescript` client consumes.
- **Alternatives considered**: hand-editing `openapi.yaml` — rejected (generated + drift-checked).

## §7 — Feature flag `position_template_crud_enabled` (§9 dark-launch)

- **Decision**: Ship the endpoints behind a §9 feature flag, default `false`. Add `position_template_crud_enabled` to `configs/feature-flags.yaml` (state `active`, default `false`, owner) + an index row in `docs/engineering/feature-flags.md`. A `require_crud_enabled` FastAPI dependency calls `await is_enabled("position_template_crud_enabled")` and raises **404** when off (don't leak existence); it runs **before** the auth check. **No migration**: `FeatureFlagService._read_from_db` falls back to the YAML `default` (false) when the DB row is absent, so the flag is dark until an operator flips the row (T16 sync / emergency SQL).
- **Rationale**: The user opted to add the flag for a clean kill-switch independent of auth and strict §9 conformance. The pre-commit `feature-flag-registered` hook *requires* the YAML entry once an `is_enabled("...")` call site exists (and `is_enabled` raises `UnknownFeatureFlag` for an undeclared name), so the YAML + call site land together.
- **Testing**: `require_crud_enabled` is a FastAPI dependency, so the CRUD tests override it (flag "on") via `app.dependency_overrides` — same hermetic pattern as the auth seam — and one test asserts flag-off → 404. This avoids per-test asyncpg flag-row plumbing; the real `is_enabled` path is already covered by T05a's own tests.
- **Alternatives considered**: (a) no flag (low-risk + already dark via auth) — rejected per the user's "add it if there's any need"; (b) seed the DB row via a migration — rejected: unnecessary (YAML-default fallback) and would add a migration to an otherwise schema-free task.

## Open follow-ups (out of T13 scope)

- Real Identity Platform wiring behind `get_current_user` — **T07** (GCP-blocked).
- Admin UI consuming these endpoints — **T14**.
- Pagination / search on the list — deferred until volume warrants it.
