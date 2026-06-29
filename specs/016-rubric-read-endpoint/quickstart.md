# Quickstart / Verification: Rubric read endpoint

Docker test stack (§7). No migration (schema unchanged at `0005`).

## A. Regenerate the contract

```bash
docker compose -f docker-compose.test.yml run --rm --no-deps backend \
  python -m app.backend.generate_openapi            # write (adds /rubric/active + RubricSnapshot)
docker compose -f docker-compose.test.yml run --rm --no-deps backend \
  python -m app.backend.generate_openapi --check    # expect: clean
```

Commit the regenerated `app/backend/openapi.yaml` (§14).

## B. Endpoint tests

```bash
docker compose -f docker-compose.test.yml --profile db run --rm backend \
  pytest -ra app/backend/tests/api/test_rubric.py
```

| Scenario | FR / SC |
| --- | --- |
| active version seeded → 200 + full tree (matches snapshot shape) | FR-001/002, SC-001 |
| no active version → 404 | FR-003, SC-002 |
| recruiter/admin allowed; other role → 403; anonymous → 401 | FR-004, SC-002 |

## C. Full regression + lint/types

```bash
docker compose -f docker-compose.test.yml --profile db up --build \
  --exit-code-from backend postgres backend          # 181 baseline + new tests
docker compose -f docker-compose.test.yml run --rm --no-deps backend sh -c '
  ruff check app/backend &&
  ruff format --check app/backend alembic scripts &&
  mypy --strict app/backend &&
  python -m app.backend.generate_openapi --check'
```

## Done when

- §A `openapi.yaml` carries `/rubric/active`, committed, drift-check clean.
- §B endpoint tests pass.
- §C full suite green; ruff/mypy clean.
