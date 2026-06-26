# Quickstart / Verification: Position Template CRUD (T13)

Docker test stack (§7 parity). No local `uv`. Schema is already at
`0004_position_template` (T12) — no migration in T13.

## A. Regenerate the OpenAPI contract (paths land here)

```bash
# Write openapi.yaml with the new /position-templates paths, then verify no drift.
docker compose -f docker-compose.test.yml run --rm --no-deps backend \
  python -m app.backend.generate_openapi
docker compose -f docker-compose.test.yml run --rm --no-deps backend \
  python -m app.backend.generate_openapi --check   # expect: clean
```

Commit the regenerated `app/backend/openapi.yaml` in the same PR (§14).

## B. Run the endpoint integration tests

```bash
docker compose -f docker-compose.test.yml --profile db run --rm backend \
  pytest -ra app/backend/tests/api/test_position_templates.py
```

Coverage (maps to acceptance / SC):

| Scenario | FR / SC |
| --- | --- |
| POST valid → 201, round-trips | FR-001/002, SC-001 |
| POST invalid (bad level / unknown stack / competency-not-in-stack / must-have⊄selected) → 422, nothing stored | FR-003, SC-002 |
| GET list excludes archived by default; `?include_archived=true` includes | FR-005, SC-003 |
| GET one → 200; unknown id → 404 | FR-004 |
| PATCH updates fields + replaces selections; invalid edit → 422, unchanged | FR-006 |
| DELETE → archived (archived_at set), row still present, absent from default list | FR-007, SC-003 |
| recruiter/admin allowed; other role → 403; anonymous → 401 | FR-008, SC-004 |
| flag `position_template_crud_enabled` off → 404 (before auth) | §9, FR-009 |
| create is atomic (mid-write failure → no partial template) | FR-010 |

## C. Full regression + lint/types

```bash
docker compose -f docker-compose.test.yml --profile db up --build \
  --exit-code-from backend postgres backend          # 159 baseline + new T13 tests
docker compose -f docker-compose.test.yml run --rm --no-deps backend sh -c '
  ruff check app/backend &&
  ruff format --check app/backend alembic scripts &&
  mypy --strict app/backend &&
  python -m app.backend.generate_openapi --check'
```

## Done when

- §A `openapi.yaml` regenerated with `/position-templates` paths, committed, drift-check clean.
- §B all endpoint tests pass (5 verbs, archived filter, 422/403/401/404, atomicity).
- §C full suite green; ruff/mypy clean.
