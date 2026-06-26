# Quickstart / Verification: Rubric snapshot (T15)

Docker test stack (§7 parity). No local `uv`.

## A. Apply the migration

```bash
docker compose -f docker-compose.test.yml --profile db up -d postgres
docker compose -f docker-compose.test.yml run --rm backend alembic upgrade head
# Expect: ... -> 0005_rubric_snapshot (head)
```

Confirm additive-only **upgrade** DDL (the T10 gate reads the rendered SQL):

```bash
docker compose -f docker-compose.test.yml run --rm --no-deps backend \
  alembic upgrade 0004_position_template:0005_rubric_snapshot --sql | \
  grep -iE 'DROP COLUMN|DROP TABLE|ALTER COLUMN .* TYPE' && echo "DESTRUCTIVE — FAIL" || echo "additive-only — OK"
```

## B. Run the T15 tests

```bash
docker compose -f docker-compose.test.yml --profile db run --rm backend \
  pytest -ra \
    app/backend/tests/db/test_rubric_snapshot_migration.py \
    app/backend/tests/services/test_rubric_snapshot.py \
    app/backend/tests/contracts/test_rubric_snapshot_contract.py
```

| Test | Covers | FR / SC |
| --- | --- | --- |
| migration: column NOT NULL + `'{}'` default; placeholder insert (no snapshot) still works | additive change, seed compatibility | FR-007, SC-004 |
| `snapshot_rubric` reproduces stack→block→competency→{topic,level} for a version | deep copy | FR-001, SC-001 |
| snapshot is self-contained (values present; no live join needed to read) | self-containment | FR-002, SC-003 |
| `snapshot_rubric` on an unknown version → `RubricSnapshotError` | guard | FR-005 |
| **§4**: freeze into a session; rename stack + add competency + new version; stored snapshot UNCHANGED | the invariant | FR-004, SC-002 |
| contract validates a good snapshot, rejects a malformed one | committed shape | FR-006, SC-005 |

## C. Full regression + lint/types

```bash
docker compose -f docker-compose.test.yml --profile db up --build \
  --exit-code-from backend postgres backend          # 171 baseline + new T15 tests
docker compose -f docker-compose.test.yml run --rm --no-deps backend sh -c '
  ruff check app/backend &&
  ruff format --check app/backend alembic scripts &&
  mypy --strict app/backend &&
  python -m app.backend.generate_openapi --check'     # openapi no-op (no routes in T15)
```

## Done when

- §A migration reaches `0005_rubric_snapshot (head)`, additive-only upgrade.
- §B all T15 tests pass — especially the §4 mutation test.
- §C full suite green; ruff/mypy clean; the JSON-schema contract committed at `docs/contracts/rubric-snapshot.schema.json`.
