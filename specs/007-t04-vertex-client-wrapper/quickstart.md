# Quickstart — Vertex AI Client Wrapper (T04)

A reviewer-facing walkthrough that validates the T04 PR end-to-end in **under 5 minutes**, on a fresh clone, **without** any GCP credential or `gcloud` installation. Mirrors SC-005 (60-second backend test run) and SC-007 (one trace record is enough to audit any historical call).

---

## Prerequisites

You need:

- The T04 branch checked out (`git checkout 007-t04-vertex-client-wrapper`).
- Docker Desktop running (or any Docker daemon — the project standard is `docker compose`).
- Nothing else. No Python, no `uv`, no GCP credentials, no `gcloud`. Constitution §7 says everything runs inside the same containers in dev / CI / prod.

---

## Step 1 — Run the full backend test suite (≈ 30–60 s)

```bash
docker compose -f docker-compose.test.yml run --rm backend pytest -v
```

You should see:

- All T02 tests (health, logging PII, OpenAPI regeneration) — green.
- All T04 tests under `app/backend/tests/llm/` and `app/backend/tests/test_settings.py` — green.
- Total wall time **< 60 seconds** (SC-005).
- The `pytest-asyncio` plugin reports `asyncio_mode = "auto"` in the header.

**If this fails**: stop and read the failure output. The test names in `app/backend/tests/llm/test_vertex_wrapper.py` are aligned 1-to-1 with the FR-017 matrix in [`contracts/wrapper-contract.md` §10](contracts/wrapper-contract.md). A failing test means a specific FR is not satisfied.

---

## Step 2 — Run the wrapper-only test slice (focused, ≈ 5 s)

```bash
docker compose -f docker-compose.test.yml run --rm backend \
  pytest app/backend/tests/llm/test_vertex_wrapper.py -v
```

Each line of output corresponds to a specific FR row in the wrapper-contract test matrix. Expected:

```
test_successful_call_with_schema_returns_parsed_json     PASSED
test_timeout_above_30s_rejected_at_construction          PASSED
test_max_tokens_above_4096_rejected_at_construction      PASSED
test_schema_miss_raises_immediately_with_raw_payload     PASSED
test_session_at_budget_raises_before_backend_call        PASSED
test_unknown_agent_raises_config_error                   PASSED
test_unknown_model_override_raises_config_error          PASSED
test_trace_sink_failure_raises_trace_write_error         PASSED
test_one_trace_per_invocation_in_every_scenario          PASSED
test_log_event_carries_no_prompt_text_no_pii             PASSED
```

This is the FR-017 matrix landing as 10 distinct, named, runnable assertions — the spec made promises, the test suite proves them.

---

## Step 3 — Verify the static guardrail (≈ 2 s)

The wrapper is the **single sanctioned doorway** for every model-provider SDK import. Verify the guardrail catches a bypass attempt:

```bash
# (a) Confirm the post-T04 tree passes the guardrail.
bash scripts/check-no-provider-sdk-imports.sh && echo "OK: tree clean"

# (b) Demonstrate the guardrail blocks a bypass (uses a temporary file).
mkdir -p app/backend/services
echo 'import vertexai' > app/backend/services/_demo_violation.py
bash scripts/check-no-provider-sdk-imports.sh
# Expected exit code: 1
# Expected stderr: "ERROR: model-provider SDK imported outside the canonical wrapper:
#                   ./app/backend/services/_demo_violation.py:1: import vertexai"
echo "Exit code: $?"
rm app/backend/services/_demo_violation.py
rmdir app/backend/services 2>/dev/null || true
```

The same script runs as a `.pre-commit-config.yaml` hook (`no-provider-sdk-imports`) and as a CI step — local pre-commit and CI parity is the T01/T02 convention. SC-003 is satisfied.

---

## Step 4 — Verify production-mode startup refusal (≈ 2 s)

The wrapper refuses to boot in production with the mock backend selected (FR-007 / SC-010). Verify directly:

```bash
docker compose -f docker-compose.test.yml run --rm \
  -e APP_ENV=prod \
  -e LLM_BACKEND=mock \
  backend python -c "from app.backend.settings import Settings; Settings().assert_safe_for_environment()"
```

Expected: process exits non-zero with:

```
RuntimeError: FR-007: LLM_BACKEND=mock is not allowed when APP_ENV=prod
```

Repeat with `LLM_BACKEND=vertex` and `LLM_BUDGET_PER_SESSION_USD=10.00`:

```bash
docker compose -f docker-compose.test.yml run --rm \
  -e APP_ENV=prod \
  -e LLM_BACKEND=vertex \
  -e LLM_BUDGET_PER_SESSION_USD=10.00 \
  backend python -c "from app.backend.settings import Settings; Settings().assert_safe_for_environment()"
```

Expected:

```
RuntimeError: constitution §12: LLM_BUDGET_PER_SESSION_USD must not exceed $5.00 in production
```

Both invariants are §12-derived and the runtime refuses to violate them.

---

## Step 5 — Inspect a trace record (≈ 1 min)

The whole point of the wrapper is that every call leaves an audit row. Run a one-off invocation and inspect the trace:

```bash
docker compose -f docker-compose.test.yml run --rm backend python <<'PY'
import asyncio
from uuid import uuid4
from decimal import Decimal

from app.backend.llm import call_model, ModelCallRequest
from app.backend.llm.trace import InMemoryTraceSink
from app.backend.llm.cost_ledger import InMemoryCostLedger
from app.backend.settings import Settings

async def main():
    sink = InMemoryTraceSink()
    ledger = InMemoryCostLedger()
    settings = Settings()  # picks up LLM_BACKEND=mock from .env or default

    req = ModelCallRequest(
        agent="assessor",
        system_prompt="You are an assessor. Return JSON.",
        user_payload="Evaluate this answer: ...",
        json_schema={"type": "object", "required": ["concepts_covered"]},
        session_id=uuid4(),
    )
    result = await call_model(req, sink=sink, ledger=ledger, settings=settings)

    record = sink.records[0]
    print("trace_id:     ", record.id)
    print("agent:        ", record.agent)
    print("model:        ", record.model)
    print("model_version:", record.model_version)
    print("outcome:      ", record.outcome)
    print("attempts:     ", record.attempts)
    print("input_tokens: ", record.input_tokens)
    print("output_tokens:", record.output_tokens)
    print("cost_usd:     ", record.cost_usd)
    print("latency_ms:   ", record.latency_ms)
    print("prompt_sha:   ", record.prompt_sha256[:16] + "…")

asyncio.run(main())
PY
```

You should see one structured record covering every field in the FR-008 list. **Note**: prompt text and model output text appear NOWHERE in the record — only the SHA. Constitution §15 (PII containment) and FR-013 (no prompt content in logs/traces) verified by inspection.

---

## Step 6 — Add a fixture (optional, ≈ 2 min)

If the test in step 5 fails because no fixture matches the prompt SHA, the mock will write the unseen prompt under `app/backend/tests/fixtures/llm_responses/_unrecorded/<sha>.json`. To "promote" it into a real fixture:

```bash
# Inspect what was captured
ls app/backend/tests/fixtures/llm_responses/_unrecorded/

# Edit the captured file to set the desired response text + token counts
$EDITOR app/backend/tests/fixtures/llm_responses/_unrecorded/<sha>.json

# Move it into the agent's directory
mv app/backend/tests/fixtures/llm_responses/_unrecorded/<sha>.json \
   app/backend/tests/fixtures/llm_responses/assessor/<sha>.json

# Re-run the test
docker compose -f docker-compose.test.yml run --rm backend \
  pytest app/backend/tests/llm/test_vertex_wrapper.py::test_successful_call_with_schema_returns_parsed_json -v
```

This flow is documented in `app/backend/tests/fixtures/llm_responses/README.md`. Production never reaches this code (FR-007).

---

## Step 7 — Confirm OpenAPI is byte-identical (≈ 5 s)

T04 ships no HTTP route. The T02 OpenAPI regen-and-diff guardrail must continue to pass with zero diff (FR-018, SC-009):

```bash
docker compose -f docker-compose.test.yml run --rm backend python -m app.backend.generate_openapi
git diff --exit-code app/backend/openapi.yaml
echo "Exit code: $?"   # 0 means byte-identical
```

---

## Step 8 — Confirm the documentation-fix landed (≈ 30 s)

Per Clarifications 2026-04-26, T04 reconciles two older docs to the spec's clarified policies. Verify:

```bash
# implementation-plan.md T04 acceptance text — should NOT contain "schema miss retries"
grep -n "schema miss retries" docs/engineering/implementation-plan.md && echo "DOC FIX MISSING" || echo "OK: doc-fix landed"

# vertex-integration.md retry table — should describe a uniform 3-attempt budget
grep -nA3 "Retry policy" docs/engineering/vertex-integration.md | head -20
# Expected: a single uniform "3 attempts" table, no per-error-type rows; DeadlineExceeded explicitly excluded.
```

---

## Acceptance checklist for the reviewer

After steps 1–8, every box below should be checked:

- [ ] All backend tests pass in **< 60 s** without GCP credentials (SC-005).
- [ ] All 10 wrapper-test names in step 2 pass (FR-017 matrix complete).
- [ ] Static guardrail blocks a bypass attempt and is wired to pre-commit + CI (SC-003).
- [ ] Production-mode + mock-backend refuses to start (SC-010).
- [ ] Production-mode + budget-above-ceiling refuses to start (§12).
- [ ] One trace record per call with all FR-008 fields populated (SC-004, SC-007).
- [ ] Trace record contains no prompt text, no output text, no PII (FR-013, §15).
- [ ] `app/backend/openapi.yaml` is byte-identical (FR-018, SC-009).
- [ ] `docs/engineering/implementation-plan.md` and `docs/engineering/vertex-integration.md` reconciled with the spec (Clarifications 2026-04-26).
- [ ] `ruff check app/backend && mypy --strict app/backend/llm` exit zero (SC-008).
- [ ] No new secret in `.env.example` — only the three non-secret keys added by T04 (`LLM_BACKEND=mock`, `LLM_BUDGET_PER_SESSION_USD=5.00`, `LLM_FIXTURES_DIR=...`); `APP_ENV` is reused from T01.

If any box is unchecked, block the PR. The merge bar for T04 is high because this module is on the critical path of every later LLM-touching task — fixing it later is dramatically more expensive.
