# Quickstart: Validate the T09 Docker-stack consolidation PR

Reviewer-facing walkthrough. Validates the whole feature in under 10 minutes. Run from the repo root.

## 0. Prerequisites

Docker Desktop running. Ports 8000, 3000, 5432 free on the host.

## 1. Confirm dead infrastructure is gone (SC-002)

```bash
git grep -nE "vertex-mock|VERTEX_MOCK_URL|tools/vertex-mock|Dockerfile\.vertex-mock" \
  -- ':!specs/011-t09-docker-stacks/' ':!CHANGELOG*'
# EXPECT: empty output, exit 1
```

```bash
ls Dockerfile.vertex-mock 2>&1
# EXPECT: "No such file or directory"
```

```bash
docker compose config --profiles | sort
# EXPECT: db / full / web (no `llm`)
```

```bash
docker compose -f docker-compose.test.yml config --profiles | sort
# EXPECT: db / e2e / full (no `llm`)
```

## 2. Bring up the dev stack (SC-001 / SC-003)

```bash
docker compose --profile db --profile web up -d --build
# wait for healthy (compose prints status); should be < 5 min on cold cache, < 30 s on warm cache.
```

Probe the endpoints by hand:

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/health   # EXPECT: 200
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3000/         # EXPECT: 200
curl -s http://localhost:8000/health                                     # EXPECT: {"status":"ok",...}
```

Tear down:

```bash
docker compose --profile db --profile web down
```

## 3. Run the smoke script (SC-003 / FR-006)

```bash
bash scripts/smoke-docker-stack.sh
echo "exit: $?"
# EXPECT: exit 0; "backend OK"-style lines on stdout; no errors on stderr; stack torn down at exit.
```

Confirm cleanup happened even on failure (run the script with a mocked failure if you want; not required for the gate).

## 4. Run the full test suite in the test stack (SC-004)

```bash
docker compose -f docker-compose.test.yml --profile db up -d postgres
docker compose -f docker-compose.test.yml --profile db run --rm backend \
  sh -c "alembic upgrade head && pytest app/backend/tests -q --no-header"
# EXPECT: 138 passed in N seconds (or higher count if newer tests were added; the point is "no regression").
```

## 5. Confirm the no-DB skip path still works (SC-004 / FR-007)

```bash
docker compose -f docker-compose.test.yml run --rm -e DATABASE_URL= backend \
  pytest app/backend/tests/cli app/backend/tests/db app/backend/tests/services -q --no-header
# EXPECT: tests that need DB skip cleanly; convert/schema/hook tests that don't need DB pass.
```

## 6. Read the new docs (SC-005)

Open `docs/engineering/docker.md`. Confirm you can answer in writing, from the doc alone:

1. Which command brings up dev with DB + frontend? *(Section 1.)*
2. Which command runs the test suite? *(Section 2.)*
3. What does `LLM_BACKEND=mock` mean and why does prod forbid it? *(Section 5.)*
4. How do I reset my local DB to empty? *(Section 6.)*
5. Why does `docker compose --profile llm up` no longer exist? *(Section 0 + Section 5; pointer to `specs/011-t09-docker-stacks/`.)*

## 7. Confirm pre-commit gates clean (SC-006)

```bash
pre-commit run --all-files
# EXPECT: every hook passes; exit 0.
```

## 8. Confirm OpenAPI byte-identical (SC-007)

```bash
docker compose -f docker-compose.test.yml run --rm backend python -m app.backend.generate_openapi --check
echo "exit: $?"
# EXPECT: 0
```

## 9. Confirm §7 parity at a glance (SC-008)

```bash
diff <(grep -E "target:|image:" docker-compose.yml) \
     <(grep -E "target:|image:" docker-compose.test.yml)
# EXPECT: the only differences are documented in docs/engineering/docker.md § 4 — the e2e service's Playwright image (test-only), and any operational-difference rows from the matrix. Backend / frontend / postgres image lines match.
```

## 10. Teardown

```bash
docker compose -f docker-compose.test.yml --profile db down -v
docker compose --profile db --profile web down -v
```

## Success-criteria checklist

- [ ] SC-001 — clean-clone dev bring-up < 5 min (step 2)
- [ ] SC-002 — `git grep` returns empty for dead refs (step 1)
- [ ] SC-003 — smoke script exits 0 with stack reachable (step 3)
- [ ] SC-004 — full test suite passes in the test stack (step 4)
- [ ] SC-005 — new contributor can answer all 5 questions from the docs alone (step 6)
- [ ] SC-006 — `pre-commit run --all-files` clean (step 7)
- [ ] SC-007 — OpenAPI byte-identical (step 8)
- [ ] SC-008 — `docker compose` diff shows only documented operational differences (step 9)
