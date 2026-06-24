# Quickstart / Verification: Position Template schema + contract (T12)

All commands run against the Docker test stack (§7 parity). No local `uv`.

## A. Apply the migration on a clean DB

```bash
docker compose -f docker-compose.test.yml --profile db up -d postgres
docker compose -f docker-compose.test.yml run --rm backend alembic upgrade head
# Expect: ... -> 0004_position_template (head)
```

Confirm additive-only DDL (the T10 destructive-DDL gate must read `needs_adr=false`):

```bash
docker compose -f docker-compose.test.yml run --rm --no-deps backend \
  alembic upgrade 0003_rubric_payload_hash:0004_position_template --sql | \
  grep -iE 'DROP COLUMN|DROP TABLE|ALTER COLUMN .* TYPE' && echo "DESTRUCTIVE — FAIL" || echo "additive-only — OK"
```

## B. Run the T12 test files

```bash
docker compose -f docker-compose.test.yml --profile db run --rm backend \
  pytest -ra \
    app/backend/tests/db/test_position_template_migration.py \
    app/backend/tests/schemas/test_position_template_schema.py \
    app/backend/tests/services/test_position_template_validate.py \
    app/backend/tests/contracts/test_position_template_contract.py
```

Each maps to an acceptance scenario:

| Test file | Covers | FR / SC |
| --- | --- | --- |
| `db/test_position_template_migration.py` | migration applies; new columns/tables present; soft-delete sets `archived_at` without row removal | FR-007, FR-010, SC-005 |
| `schemas/test_position_template_schema.py` | level enum rejects `Architect`; must-have ⊄ selected rejected; ≥1 competency; dedupe | FR-002/004/005, SC-002 |
| `services/test_position_template_validate.py` | unknown stack rejected; unknown competency rejected; competency-not-in-selected-stack rejected; valid passes | FR-003/006/011, SC-002 |
| `contracts/test_position_template_contract.py` | JSON schema validates a good example, rejects a bad-level example | FR-009, SC-003 |

## C. OpenAPI no-op (no routes in T12 — see plan §Key design decision)

```bash
docker compose -f docker-compose.test.yml run --rm --no-deps backend \
  python -m app.backend.generate_openapi --check
# Expect: clean (no drift) — T12 registers no routes, so openapi.yaml is unchanged.
```

## D. Full regression (baseline must stay green)

```bash
docker compose -f docker-compose.test.yml --profile db up --build \
  --exit-code-from backend postgres backend
# Expect: 138 prior tests + the new T12 tests all pass.
```

## E. Lint / types / contract (mirrors CI)

```bash
docker compose -f docker-compose.test.yml run --rm --no-deps backend sh -c '
  ruff check app/backend &&
  ruff format --check app/backend alembic scripts &&
  mypy --strict app/backend'
# JSON-schema contract itself parses + is a valid Draft 2020-12 schema:
docker compose -f docker-compose.test.yml run --rm --no-deps backend \
  python -c "import json,jsonschema; jsonschema.Draft202012Validator.check_schema(json.load(open('docs/contracts/position-template.schema.json'))); print('contract schema OK')"
```

## Done when

- §A migration reaches `0004_position_template (head)`, additive-only.
- §B all four T12 test files pass.
- §C `openapi --check` is clean (no-op).
- §D the full suite (138 + new) is green.
- §E ruff/mypy clean; the JSON-schema contract is a valid schema and is committed at `docs/contracts/position-template.schema.json`.
