# Quickstart: Validate the T05 DB schema PR

Reviewer-facing walkthrough. Validates the whole feature in under 10 minutes, no cloud database required. Run from the repo root.

## 0. Prerequisites

Docker running. No GCP credentials needed. The test stack uses the `pgvector/pgvector:pg17` image (same as dev).

## 1. Bring up Postgres + apply the migration (SC-001, SC-006)

```bash
# Start the test DB (db profile) and run the migration inside the backend container
docker compose -f docker-compose.test.yml --profile db up -d postgres
docker compose -f docker-compose.test.yml run --rm backend alembic upgrade head
# Re-run to prove idempotency (SC-006) — must succeed, not error on existing roles/extensions
docker compose -f docker-compose.test.yml run --rm backend alembic upgrade head
```

Expect: both runs exit 0.

## 2. Inspect the objects (SC-001, SC-007)

```bash
docker compose -f docker-compose.test.yml exec postgres \
  psql -U techscreen -d techscreen_test -c "\dt"            # 16 tables
docker compose -f docker-compose.test.yml exec postgres \
  psql -U techscreen -d techscreen_test -c "SELECT extname FROM pg_extension;"   # vector, pgcrypto present
docker compose -f docker-compose.test.yml exec postgres \
  psql -U techscreen -d techscreen_test -c "SELECT rolname FROM pg_roles WHERE rolname LIKE 'techscreen_%';"  # techscreen_app, techscreen_migrator
```

## 3. Feel the append-only guarantee by hand (SC-003, US1)

```bash
docker compose -f docker-compose.test.yml exec postgres \
  psql -U techscreen -d techscreen_test <<'SQL'
-- Trigger layer: superuser is NOT migrator → trigger raises
INSERT INTO assessment (interview_session_id, competency_id, score, confidence)
  VALUES (NULL, NULL, 3, 0.900);            -- NULL FKs ok for this probe if nullable; else seed a session+competency first
UPDATE assessment SET score = 4;            -- EXPECT: ERROR  append-only: UPDATE not allowed on assessment

-- Revoke layer: become the app role → permission denied
SET ROLE techscreen_app;
UPDATE assessment SET score = 4;            -- EXPECT: ERROR  permission denied for table assessment
DELETE FROM assessment;                     -- EXPECT: ERROR  permission denied for table assessment
INSERT INTO assessment (interview_session_id, competency_id, score, confidence)
  VALUES (NULL, NULL, 2, 0.800);            -- EXPECT: success (append allowed)
RESET ROLE;

-- Migrator path: exemption lets migrations evolve audit data
SET ROLE techscreen_migrator;
UPDATE assessment SET score = 5;            -- EXPECT: success
RESET ROLE;
SQL
```

(If the FK columns are `NOT NULL`, seed a `stack→…→competency` chain and an `interview_session` first; the automated tests do this in fixtures.)

## 4. Run the automated suite (SC-003, SC-004)

```bash
docker compose -f docker-compose.test.yml --profile db run --rm backend \
  pytest app/backend/tests/db -v
```

Expect green, including:
- `test_baseline_migration.py` — up/down/up round-trip.
- `test_roles.py` — role existence + grant shape.
- `test_append_only.py` — 12 app-role rejection assertions + trigger-layer + migrator-path + INSERT-allowed.
- `test_rubric_tree.py` — FK relationships + insert/rollback.

## 5. Confirm the no-DB unit run still passes (regression / §7)

```bash
# No db profile → DB tests skip, everything else runs (must stay green)
docker compose -f docker-compose.test.yml run --rm backend pytest app/backend/tests
```

## 6. Confirm the downgrade empties the DB (SC-002)

```bash
docker compose -f docker-compose.test.yml run --rm backend alembic downgrade base
docker compose -f docker-compose.test.yml exec postgres \
  psql -U techscreen -d techscreen_test -c "\dt"   # EXPECT: "Did not find any relations."
```

## 7. Guardrails (no regressions)

```bash
docker compose -f docker-compose.test.yml run --rm backend ruff check app/backend
docker compose -f docker-compose.test.yml run --rm backend mypy --strict app/backend
docker compose -f docker-compose.test.yml run --rm backend python -m app.backend.generate_openapi --check   # byte-identical: no route added
pre-commit run --all-files
```

## 8. Teardown

```bash
docker compose -f docker-compose.test.yml --profile db down -v
```

## Success-criteria checklist

- [ ] SC-001 — one command brings empty DB to full schema (step 1–2)
- [ ] SC-002 — one command returns DB to empty (step 6)
- [ ] SC-003 — app-role UPDATE/DELETE rejected, INSERT/SELECT allowed (step 3–4)
- [ ] SC-004 — all six tables covered by invariant tests (step 4)
- [ ] SC-005 — reviewer confirms REVOKE+trigger coverage by reading `0001_baseline.py` (< 5 min)
- [ ] SC-006 — second upgrade succeeds (step 1)
- [ ] SC-007 — `vector` + `pgcrypto` enabled at baseline (step 2)
