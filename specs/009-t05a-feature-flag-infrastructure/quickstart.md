# Quickstart: Validate the T05a feature-flag infrastructure PR

Reviewer-facing walkthrough. Validates the whole feature in under 10 minutes, no cloud database required. Run from the repo root.

## 0. Prerequisites

Docker running; the dev image is built (`docker compose -f docker-compose.test.yml build backend` if not). No GCP credentials needed (T05a uses WIF only in the post-merge workflow; local validation runs against Docker Postgres).

## 1. Apply the migration & confirm the §3 carve-out (SC-009)

```bash
docker compose -f docker-compose.test.yml --profile db up -d postgres
docker compose -f docker-compose.test.yml --profile db run --rm backend alembic upgrade head
```

Expect: exit 0; `feature_flag` table created; no error mentioning `reject_audit_mutation` or `REVOKE` (the new migration deliberately omits both — FR-013).

Confirm the carve-out by hand:

```bash
docker compose -f docker-compose.test.yml exec postgres \
  psql -U techscreen -d techscreen_test <<'SQL'
-- 1) The table exists, with no audit trigger:
SELECT trigger_name FROM information_schema.triggers WHERE event_object_table = 'feature_flag';
-- EXPECT: only the notify trigger (e.g., feature_flag_notify) and an updated_at trigger; NO reject_audit_mutation.

-- 2) The app role has full DML (unlike the six §3 tables):
SELECT has_table_privilege('techscreen_app', 'feature_flag', 'UPDATE');  -- EXPECT: t
SELECT has_table_privilege('techscreen_app', 'feature_flag', 'DELETE');  -- EXPECT: t

-- 3) UPDATE from the app role works (SC-009 — would fail on any audit table):
SET ROLE "techscreen_app";
INSERT INTO feature_flag (name, owner) VALUES ('quickstart_demo', '@reviewer');
UPDATE feature_flag SET enabled = true WHERE name = 'quickstart_demo';  -- EXPECT: UPDATE 1
DELETE FROM feature_flag WHERE name = 'quickstart_demo';                -- EXPECT: DELETE 1
RESET ROLE;
SQL
```

## 2. Run the automated DB + service suites

```bash
docker compose -f docker-compose.test.yml --profile db run --rm backend \
  pytest app/backend/tests/db/test_feature_flag_table.py app/backend/tests/services -v
```

Expect green, including:
- `test_feature_flag_table.py` — §3 carve-out (no audit trigger, no REVOKE, UPDATE/DELETE allowed) — proves SC-009.
- `test_feature_flags.py::test_unknown_flag_raises` — `UnknownFeatureFlag` raised (FR-004).
- `test_feature_flags.py::test_update_propagates_under_one_second` — UPDATE → cache invalidation in < 1 s (SC-003).
- `test_feature_flags.py::test_listener_reconnects_after_drop` — forced disconnect followed by recovery.

## 3. Run the registration hook against fixture failure trees (SC-006)

```bash
docker compose -f docker-compose.test.yml run --rm backend \
  pytest app/backend/tests/contracts/test_feature_flag_registration.py -v
```

Expect green — each fixture exits non-zero with the expected error message:
- **undeclared name**: `is_enabled("typo")` without YAML entry → `'typo' is referenced in code but not declared in configs/feature-flags.yaml`.
- **removed last call without sunset**: YAML `state: active` but no call site → `'orphan' is state=active but no call site in app/backend/ — flip to state=sunset or restore a call site`.
- **sunset entry missing docs row**: YAML `state: sunset` without docs Sunset row → `'retired' is state=sunset but missing from docs/engineering/feature-flags.md`.
- **YAML schema violation**: malformed entry → `configs/feature-flags.yaml: $.flags[0].state must be one of [active, sunset]` (or similar precise message).
- **orphan docs row**: docs Sunset row without matching YAML entry → `'ghost' appears in docs but not in configs/feature-flags.yaml`.

## 4. Run the hook on the clean tree (must be zero exit)

```bash
docker compose -f docker-compose.test.yml run --rm backend \
  python scripts/check-feature-flag-registration.py
echo $?  # EXPECT: 0
```

## 5. Confirm the workflow file is structurally valid

The workflow ships with `<TODO-T06: …>` placeholders (the live WIF / Cloud SQL parameters land in T06). It must still parse cleanly:

```bash
docker compose -f docker-compose.test.yml run --rm backend \
  python -c "import yaml; yaml.safe_load(open('.github/workflows/sync-feature-flags.yml'))"  # EXPECT: no error
docker compose -f docker-compose.test.yml run --rm backend \
  actionlint .github/workflows/sync-feature-flags.yml || true   # EXPECT: zero issues
```

The workflow's runtime path stays inert in T05a (the upsert step is guarded by an `if:` that requires resolved placeholders). T06 lands the bindings; we re-verify the workflow then.

## 6. Demonstrate sub-second propagation by hand (SC-003)

In one terminal, run a tiny watcher script (the service):

```bash
docker compose -f docker-compose.test.yml --profile db run --rm backend python -c "
import asyncio
from app.backend.services.feature_flags import FeatureFlagService

async def main():
    svc = await FeatureFlagService.create_with_listener()
    while True:
        print('quickstart_demo:', await svc.is_enabled('quickstart_demo'))
        await asyncio.sleep(0.5)

asyncio.run(main())
"
```

In another terminal, flip the flag via SQL:

```bash
docker compose -f docker-compose.test.yml exec postgres \
  psql -U techscreen -d techscreen_test \
  -c "UPDATE feature_flag SET enabled = true WHERE name = 'quickstart_demo';"
```

Expect: the watcher prints `True` within one 500 ms tick — typically the very next line — proving the NOTIFY path.

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

- [ ] SC-001 — adding a flag end-to-end is < 10 min following `docs/engineering/feature-flags.md` (manual; have a stopwatch).
- [ ] SC-002 — sync workflow design fits in < 5 min (validated by inspection of the workflow file; live timing happens after T06 binds it).
- [ ] SC-003 — UPDATE → `is_enabled` reflects new value in < 1 s (step 2 automated; step 6 by hand).
- [ ] SC-004 — clean tree: hook exit 0 (step 4).
- [ ] SC-005 — every `state: sunset` YAML entry has a docs row with `sunset_pr`/`sunset_date` (hook enforces; step 4 + step 3).
- [ ] SC-006 — five fixture failures all blocked at the hook (step 3).
- [ ] SC-007 — emergency disable < 60 s (steps 1 + 6 jointly).
- [ ] SC-008 — `gitleaks`/`detect-secrets` clean on the diff (step 7).
- [ ] SC-009 — `UPDATE feature_flag` from `techscreen_app` succeeds (step 1 + step 2).
