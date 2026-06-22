# Quickstart: Validate the T08 matrix importer PR

Reviewer-facing walkthrough. Validates the whole feature in under 10 minutes; no real-world rubric content required. Run from the repo root.

## 0. Prerequisites

Docker running. No GCP credentials needed. The test stack uses the `pgvector/pgvector:pg17` image already in place from T05.

## 1. Apply the migration (SC-001 / SC-006 baseline)

```bash
docker compose -f docker-compose.test.yml --profile db up -d postgres
docker compose -f docker-compose.test.yml --profile db run --rm backend alembic upgrade head
```

Expect exit 0. Confirm the additive column:
```bash
docker compose -f docker-compose.test.yml exec postgres \
  psql -U techscreen -d techscreen_test \
  -c "\d rubric_tree_version" | grep payload_hash
# EXPECT: a payload_hash text NOT NULL row with a UNIQUE constraint reference.
```

## 2. Schema validates the example file shipped with the PR (SC-006)

```bash
docker compose -f docker-compose.test.yml run --rm backend python3 scripts/check-rubric-schema.py
echo $?  # EXPECT: 0
```

Then confirm five intentional defects are rejected (SC-007) by running the schema test suite directly:
```bash
docker compose -f docker-compose.test.yml run --rm backend \
  pytest app/backend/tests/contracts/test_rubric_schema.py app/backend/tests/contracts/test_rubric_schema_hook.py -v
# EXPECT all green; each of the 5 negative fixtures asserts a precise error message.
```

## 3. Convert a programmatic fixture xlsx → YAML (SC-002)

```bash
docker compose -f docker-compose.test.yml --profile db run --rm backend \
  pytest app/backend/tests/cli/test_import_matrix_convert.py -v
```

Expect green, including:
- `test_convert_writes_one_yaml_per_stack` — the fixture xlsx written by the test produces N YAMLs, all schema-valid.
- `test_convert_is_byte_identical_idempotent` — running convert twice on the same workbook produces zero diff.
- `test_duplicate_competency_id_rejected` — a deliberately-broken workbook is rejected non-zero with the offending id named.

## 4. Seed against the migrated DB (SC-003 / SC-004 / SC-008)

```bash
docker compose -f docker-compose.test.yml --profile db run --rm backend \
  pytest app/backend/tests/cli/test_import_matrix_seed.py -v
```

Expect green, including:
- `test_seed_creates_one_version_and_full_tree` — first seed inserts exactly one `rubric_tree_version` + one `stack` per file + the full child set.
- `test_repeat_seed_is_no_op` — second seed on unchanged YAML inserts 0 rows (idempotency, SC-003).
- `test_content_change_creates_new_version` — bumping `version` + editing a descriptor creates a new `rubric_tree_version` row and a fresh child set; **prior-version row hashes are byte-identical pre/post** (SC-004).
- `test_audit_row_per_new_version` — each new version inserts exactly one `audit_log` row with `action='rubric.versioned'` (SC-008).
- `test_rename_attempt_rejected` — a renamed stable id exits non-zero with the "retire + introduce" message and writes nothing (SC-005).

## 5. Run the convert + seed pipeline manually (smoke)

Build a tiny throwaway workbook with the CLI's `--dry-run` mode, then commit it through the pipeline:
```bash
# Step 1: see what the CLI thinks would change against the migrated DB without writing
docker compose -f docker-compose.test.yml --profile db run --rm backend \
  python -m app.backend.cli.import_matrix --dry-run --seed
# EXPECT: "no changes" against the example yaml; exit 0.

# Step 2: invoke the convert path against a programmatic fixture workbook (the test creates one).
# In practice we don't have a real .xlsx in the repo — the test suite is the canonical exerciser.
```

## 6. Confirm SC-009 (full suite < 90 s on `db` profile)

```bash
time docker compose -f docker-compose.test.yml --profile db run --rm backend \
  sh -c "alembic upgrade head >/dev/null 2>&1 && pytest app/backend/tests -q --no-header"
# EXPECT: all green, real time < 90 s.
```

## 7. Confirm no-DB skip path (existing T05 pattern)

```bash
docker compose -f docker-compose.test.yml run --rm -e DATABASE_URL= backend \
  pytest app/backend/tests/cli app/backend/tests/db -q --no-header
# EXPECT: CLI seed test + DB tests are skipped; CLI convert tests run (no DB needed).
```

## 8. Guardrails (no regressions)

```bash
docker compose -f docker-compose.test.yml run --rm backend ruff check app/backend
docker compose -f docker-compose.test.yml run --rm backend ruff format --check app/backend alembic scripts
docker compose -f docker-compose.test.yml run --rm backend mypy --strict app/backend
docker compose -f docker-compose.test.yml run --rm backend \
  python -m app.backend.generate_openapi --check   # byte-identical: no route added
```

## 9. Teardown

```bash
docker compose -f docker-compose.test.yml --profile db down -v
```

## Success-criteria checklist

- [ ] SC-001 — a new contributor can convert + validate + seed in < 10 min using the matrix-format + schema documents only (manual stopwatch).
- [ ] SC-002 — byte-identical idempotent convert (step 3).
- [ ] SC-003 — non-destructive idempotent seed (step 4).
- [ ] SC-004 — content change creates new version; pre-existing rows byte-identical (step 4).
- [ ] SC-005 — rename rejected non-zero (step 4).
- [ ] SC-006 — clean tree validates (step 2 + step 4).
- [ ] SC-007 — 5 fixture schema defects each fail with precise message (step 2).
- [ ] SC-008 — exactly one `audit_log` row per new version (step 4).
- [ ] SC-009 — full suite < 90 s (step 6).
- [ ] SC-010 — `gitleaks` / `detect-secrets` clean on the PR diff (step 8 pre-commit).
