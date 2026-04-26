# Phase 0 Research — Vertex AI Client Wrapper (T04)

15 implementation-altitude decisions resolved before Phase 1 design. Every entry follows the **Decision / Rationale / Alternatives Considered** structure. Where a decision is anchored in an existing repo artefact (constitution principle, ADR, prior task convention), the anchor is named explicitly so the reviewer can verify without external context.

---

## §1. Vertex SDK choice

**Decision**: Use `google-genai` (the unified Google generative SDK that covers Vertex AI and Gemini Developer API behind one client). Pin `>= 0.5, < 1`. Use Vertex mode (`google.genai.Client(vertexai=True, project=..., location="europe-west1")`).

**Rationale**:

- The `google-genai` SDK exposes a first-class async API (`client.aio.models.generate_content(...)`) that natively returns awaitable responses. Per the Clarifications 2026-04-26 the wrapper is async-first; using a SDK that requires `asyncio.to_thread` wrapping around a sync API would be a recurring source of cancellation / timeout bugs.
- It supports **structured output natively** via `response_mime_type="application/json"` + `response_schema=<dict>`, which is exactly what FR-011 needs. The wrapper passes the caller's `json_schema` straight through to the SDK and validates the parsed result with `pydantic.TypeAdapter` as a defence-in-depth (research §4).
- ADC-only authentication works the same way as the older SDK (`google.auth.default()` under the hood). ADR-013 / constitution §6 stay satisfied.
- Region pinning (`location="europe-west1"`) per ADR-015 is a constructor argument, not a per-call argument — exactly what we need for a single-region MVP.

**Alternatives considered**:

- `google-cloud-aiplatform` (the older SDK, named in `vertex-integration.md`'s narrative): mature but its async story is a thin wrapper over the sync gRPC client and the docs admit reduced parity. The newer SDK is Google's stated forward direction. Choosing the older one would lock us into a path Google is migrating *away* from.
- The native gRPC client (`google.cloud.aiplatform_v1.PredictionServiceAsyncClient`): too low-level — we'd reimplement structured-output parsing, retry classification, and pricing-table integration ourselves. Wrapper would balloon by ~300 LOC.
- Vertex REST API via `httpx`: rejected — credential plumbing (ADC → access token refresh) is exactly what an SDK exists for, and reimplementing it is a security hazard.

**Anchor**: ADR-002 (Vertex provider), ADR-003 (Gemini 2.5 Flash + Pro), ADR-015 (`europe-west1`), Clarifications 2026-04-26 (async-first).

---

## §2. Retry library

**Decision**: `tenacity >= 9.0, < 10`. Configure via the decorator-less `AsyncRetrying` API (it composes cleanly inside the wrapper's existing async flow).

**Rationale**:

- `docs/engineering/implementation-plan.md` T04 description explicitly names tenacity ("retry on 5xx / schema-miss with tenacity"). Choosing differently would violate the source-of-truth principle established in the spec's Assumptions section.
- `tenacity.AsyncRetrying` supports the four pieces we need: `retry=retry_if_exception_type(...)`, `wait=wait_exponential_jitter(...)`, `stop=stop_after_attempt(3)`, and `before_sleep` for tracing each retry decision.
- The library is small (one dep), well-typed (`mypy --strict` clean since 8.x), and battle-tested.

**Alternatives considered**:

- Hand-rolled retry with `asyncio.sleep` + `random`: 30 LOC of subtle logic (jitter math, exception classification, attempt counting) that's a known source of off-by-one bugs. We'd reinvent tenacity badly.
- `backoff` (the older library): unmaintained since 2022. `tenacity` is the current standard.

**Configuration shape** (committed in `vertex.py`):

```python
RETRY_BUDGET = AsyncRetrying(
    retry=retry_if_exception_type((
        google.api_core.exceptions.ServiceUnavailable,
        google.api_core.exceptions.InternalServerError,
        google.api_core.exceptions.ResourceExhausted,
        ConnectionError,
    )),
    stop=stop_after_attempt(3),                      # 1 initial + 2 retries
    wait=wait_exponential_jitter(initial=0.5, max=4.0),
    reraise=True,
)
```

`google.api_core.exceptions.DeadlineExceeded` is **deliberately excluded** per Clarifications 2026-04-26.

**Anchor**: implementation-plan T04 description, Clarifications 2026-04-26 (uniform 3-attempt budget).

---

## §3. Async test runner

**Decision**: `pytest-asyncio >= 0.23, < 1` with `asyncio_mode = "auto"`.

**Rationale**:

- `auto` mode lets every `async def test_*` run without a `@pytest.mark.asyncio` decorator. This makes the test files visually identical to T02's existing sync tests (just `async def` instead of `def`), which keeps the pattern intuitive for downstream backend tasks.
- Wider ecosystem adoption than the `anyio` plugin; troubleshooting answers are findable.
- Setup is two lines in `pyproject.toml`:

  ```toml
  [tool.pytest.ini_options]
  asyncio_mode = "auto"
  ```

**Alternatives considered**:

- `anyio` plugin (`pip install anyio`, set `pytest-anyio = true`): equally functional but adds a second async runtime concept (anyio backends — trio vs asyncio) the project doesn't need.
- `unittest.IsolatedAsyncioTestCase`: stdlib but verbose; loses pytest fixtures' composability.

**Anchor**: pytest documentation; T02's `[tool.pytest.ini_options]` is already present in `pyproject.toml`.

---

## §4. Schema validation strategy

**Decision**: Two-stage validation. Stage 1 — pass the caller's JSON schema directly to the SDK as `response_schema=<dict>` so Vertex returns structured JSON. Stage 2 — wrapper revalidates the parsed dict using `pydantic.TypeAdapter(dict).validate_python(...)` against the same schema (defence-in-depth).

Add **no** new dependency. Pydantic is already pulled in by FastAPI; `TypeAdapter` is part of pydantic v2.

**Rationale**:

- The SDK's structured-output mode is a *request*, not a *guarantee* — Gemini occasionally returns JSON that omits required fields when the system prompt and the schema disagree. The defence-in-depth Stage-2 check is what makes FR-011 honest.
- Using pydantic for Stage 2 keeps the codebase's validation idiom uniform (every other model in `app/backend/` is pydantic).
- A third dependency on `jsonschema` would add a runtime to learn (Draft 7 vs 2020-12 mode), and pydantic v2's JSON-schema support already covers the subset we'll use.

**Alternatives considered**:

- SDK-only validation (Stage 1, no Stage 2): trusts Vertex completely. We've seen schema drift in production at peer projects; defence-in-depth costs ~1 ms per call.
- `jsonschema` library: full JSON Schema standard support, but our schemas are simple object schemas — pydantic is sufficient and avoids a dependency.

**Anchor**: spec FR-011, vertex-integration.md "JSON mode" section.

---

## §5. Mock backend layout

**Decision**: One JSON file per (agent, prompt-SHA) pair, under `app/backend/tests/fixtures/llm_responses/<agent>/<sha256-hex>.json`. The mock backend computes the SHA from the canonicalised prompt, looks up the file, and returns its parsed contents wrapped in the `RawBackendResult` shape.

**Rationale**:

- One-file-per-fixture = clean `git diff` (every fixture change is a single-file change), easy code review, and easy promotion of an `_unrecorded/` capture into a real fixture (just `git mv`).
- The agent subdirectory adds a navigability cue (helpful when there are dozens of fixtures by mid-project) and lets a future task add per-agent fixture-validation rules.
- SHA-256 is collision-resistant for our scale and produces a 64-char filename (within every common filesystem limit).

**Alternatives considered**:

- A single `fixtures.yaml` with all fixtures: tempting at small scale but quickly becomes a multi-thousand-line file with merge conflicts; the YAML+SHA-key scheme also requires a parser to "promote" an unrecorded prompt.
- Hash-keyed directory without agent subdir: would work but loses the agent navigability cue and means a fixture for `assessor` could clash on filename with one for `interviewer` (cosmetic but confusing).

**Canonical-prompt-SHA recipe** (research §13 expands): SHA-256 of `json.dumps({system_prompt, user_payload, json_schema}, sort_keys=True, ensure_ascii=False).encode("utf-8")`. Including the schema in the SHA prevents stale fixtures when a schema changes.

**Anchor**: vertex-integration.md "Vertex mock" section; vertex-call skill mock description.

---

## §6. Cost arithmetic precision

**Decision**: `decimal.Decimal` throughout. The pricing table loads input/output prices as `Decimal`, the per-call cost is `Decimal`, the cost ledger sums in `Decimal`, the trace record's `cost_usd` field is `Decimal`. Pydantic v2 supports `Decimal` natively in models.

**Rationale**:

- LLM token prices are tiny (Gemini 2.5 Flash input is currently $0.000075 per 1k tokens). `float` arithmetic accumulates drift exactly where it hurts — comparing the running session total against a $5 ceiling.
- The constitution sets a per-session cost ceiling (§12). A floating-point drift that lets the ledger read $4.999999998 when the truth is $5.00 is a §12 violation. `Decimal` makes the comparison honest.
- Pydantic v2's `Decimal` field validation handles serialisation cleanly (string in JSON, `Decimal` in Python).

**Alternatives considered**:

- `float`: simpler arithmetic; rejected for the drift reason above.
- Integer micro-USD (`int` of millionths): cheap and exact, but obscures intent and forces division everywhere we display.

**Anchor**: constitution §12 (per-session ceiling).

---

## §7. Settings library

**Decision**: `pydantic-settings >= 2.6, < 3`. New file `app/backend/settings.py` with one `Settings` class (`BaseSettings` subclass) covering the four T04 keys. `app/backend/main.py` calls `Settings().assert_safe_for_environment()` once at module init (currently a no-op apart from the production+mock check).

**Rationale**:

- T02 deferred Settings to avoid scope creep ("the skeleton must boot without any external dependency configured" — FR-003). T04 actually *needs* env-driven config (`LLM_BACKEND` selection, `APP_ENV` for the production-mode refusal), so this is the right moment to introduce the abstraction. `APP_ENV` was already established by T01 (set by `Dockerfile` and every `docker-compose*.yml`) — `Settings` reads it rather than introducing a competing selector, which keeps a single source of truth for runtime environment per constitution §16.
- `pydantic-settings` is the canonical pydantic v2 path for env loading; it integrates cleanly with the existing pydantic models.
- The `assert_safe_for_environment` check is a one-liner that raises `RuntimeError` if `APP_ENV == "prod"` and `LLM_BACKEND == "mock"` — directly satisfies FR-007 and SC-010.

**Alternatives considered**:

- Continue with raw `os.environ.get(...)` calls in `vertex.py`: 5 LOC saved, 0 LOC of validation, no central place to test the production-mode refusal.
- `dynaconf` / `python-decouple`: more features than we need; pydantic-settings already covers the use case.

**Configuration shape** (`app/backend/settings.py`):

```python
class Settings(BaseSettings):
    llm_backend: Literal["mock", "vertex"] = "mock"
    app_env: Literal["dev", "test", "prod"] = "dev"
    llm_budget_per_session_usd: Decimal = Decimal("5.00")
    llm_fixtures_dir: Path = Path("app/backend/tests/fixtures/llm_responses")

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    def assert_safe_for_environment(self) -> None:
        if self.app_env == "prod" and self.llm_backend == "mock":
            raise RuntimeError("LLM_BACKEND=mock is not allowed when APP_ENV=prod")
        if self.llm_budget_per_session_usd > Decimal("5.00") and self.app_env == "prod":
            raise RuntimeError("LLM_BUDGET_PER_SESSION_USD must not exceed $5.00 in production")
```

**Anchor**: spec FR-007, FR-019, SC-010, ADR-022 (`.env.example` may carry non-secret defaults).

---

## §8. Static-guardrail mechanism

**Decision**: A ripgrep-backed shell script at `scripts/check-no-provider-sdk-imports.sh`. Pre-commit hook (`.pre-commit-config.yaml`) and CI step both invoke the same script. Mirrors T03's `app/frontend/scripts/check-visual-discipline.sh` pattern exactly.

**Rationale**:

- T03 already chose ripgrep for its visual-discipline guardrail — repeating the choice keeps two parallel guardrails operationally identical.
- Ripgrep is fast (< 100 ms on the post-T04 tree), zero-config, and produces error output a reviewer can read.
- A custom Python AST walker would be more "correct" (handles `import foo as bar`, `from x import y`, etc.) but the surface area is small (we control the few modules involved) and false-positive risk is low. Cost vs benefit doesn't justify Python.

**Script regex** (allowlist by file path):

```bash
#!/usr/bin/env bash
set -euo pipefail

PATTERN='^(import|from)\s+(vertexai|google\.genai|google\.cloud\.aiplatform|anthropic|openai)([. ]|$)'
ALLOWED_FILES=(
  "app/backend/llm/_real_backend.py"
  "app/backend/llm/_mock_backend.py"   # imports nothing real but reserved for future
)

VIOLATIONS=$(rg --line-number --no-heading "$PATTERN" -g '!app/frontend' -g '*.py' .)

if [ -z "$VIOLATIONS" ]; then exit 0; fi

# Filter out allowed files
FILTERED=$(echo "$VIOLATIONS" | while IFS=: read -r file rest; do
  is_allowed=false
  for allowed in "${ALLOWED_FILES[@]}"; do
    [ "$file" = "./$allowed" ] && is_allowed=true && break
  done
  [ "$is_allowed" = false ] && echo "$file:$rest"
done)

if [ -n "$FILTERED" ]; then
  echo "ERROR: model-provider SDK imported outside the canonical wrapper:" >&2
  echo "$FILTERED" >&2
  exit 1
fi
```

**Pre-commit hook entry** (added to `.pre-commit-config.yaml`):

```yaml
- id: no-provider-sdk-imports
  name: no provider SDK imports outside wrapper (backend)
  language: system
  pass_filenames: false
  files: ^app/backend/.*\.py$
  entry: bash scripts/check-no-provider-sdk-imports.sh
```

**Alternatives considered**:

- Custom Python AST walker (using `ast.parse` + `NodeVisitor`): more accurate but ~80 LOC of code we'd own forever; the regex covers the realistic violation modes.
- Forbidding via CI-only `grep`: violates the T01 pre-commit/CI parity convention — the local hook is what catches the violation before push.
- Pylint custom checker: too heavy a tool for one rule; we don't run pylint elsewhere.

**Anchor**: T03's `app/frontend/scripts/check-visual-discipline.sh` pattern; spec FR-014.

---

## §9. Trace sink and cost ledger interface shape

**Decision**: `typing.Protocol` for both interfaces. Concrete in-memory implementations are plain classes (no inheritance from the protocol — structural typing handles it). Protocols live in the same module as the in-memory implementation (`trace.py`, `cost_ledger.py`).

**Rationale**:

- `Protocol` (PEP 544) gives us structural typing — the future durable Postgres-backed implementations (T05) just need to expose the same methods, no inheritance required. This avoids the diamond-inheritance traps that `abc.ABC` invites.
- Zero runtime cost; the protocol is purely a `mypy --strict` artefact. Tests can pass any object that quacks right.
- Pydantic isn't a fit because these are *behaviours*, not *data shapes*.

**Trace sink protocol**:

```python
class TraceSink(Protocol):
    async def write(self, record: TraceRecord) -> None: ...
```

**Cost ledger protocol**:

```python
class CostLedger(Protocol):
    async def session_total(self, session_id: UUID) -> Decimal: ...
    async def add(self, session_id: UUID, cost_usd: Decimal) -> None: ...
```

Both methods are `async` even though the in-memory implementation is sync internally — keeps the call site uniform when T05's DB-backed implementation needs `await`.

**Alternatives considered**:

- `abc.ABC` with `@abstractmethod`: forces inheritance; in-memory implementation would have to subclass it; tests would have to subclass; everywhere becomes more verbose for no gain.
- Zero abstraction (concrete class only, swap via DI factory): fine until the second implementation arrives — at which point we'd refactor anyway. Better to commit the seam now.

**Anchor**: spec FR-009, FR-012; T05 will provide the durable implementations.

---

## §10. Fixture file format

**Decision**: JSON object with the following envelope:

```json
{
  "text": "...",
  "input_tokens": 132,
  "output_tokens": 87,
  "model": "gemini-2.5-flash",
  "model_version": "gemini-2.5-flash-001"
}
```

The `text` field is what Vertex would return (the parsed JSON-mode payload, or a string for non-JSON mode). The schema-INVALID fixture for the schema-miss test (`assessor/<sha-of-broken-prompt>.json`) sets `text` to a JSON string that's missing a required field of the schema — wrapper Stage-2 validation catches it.

**Rationale**:

- Mirrors what the wrapper actually needs from the backend protocol's `RawBackendResult` (text + token counts + model identity). No extra fields, no wasted bytes.
- JSON is the right format because the fixture file *is* the canned response (parsed JSON for JSON-mode calls). YAML would impose a transcode step.
- Keeping `model_version` distinct from `model` lets us simulate Vertex returning a specific revision pinned by the SDK — important for the trace record.

**Alternatives considered**:

- Richer envelope with `usage_metadata`, `safety_ratings`, etc.: those exist in Vertex responses but the wrapper doesn't surface them in `ModelCallResult` at T04. Adding them to the fixture risks fixtures becoming an unspoken second contract.
- A YAML envelope: requires every test fixture to round-trip through pyyaml; no benefit.

**Anchor**: spec FR-006, FR-008, FR-017.

---

## §11. `pricing.yaml` shape and units

**Decision**: Per-1k-tokens prices, USD, split between input and output. One top-level key per model identifier. Region fixed to `europe-west1` (the wrapper trusts the region pinned at SDK-construction time — per ADR-015 we are single-region until Phase 2).

```yaml
# app/backend/llm/pricing.yaml
gemini-2.5-flash:
  input_per_1k_tokens: "0.000075"
  output_per_1k_tokens: "0.000300"
gemini-2.5-pro:
  input_per_1k_tokens: "0.00125"
  output_per_1k_tokens: "0.00500"
```

Prices stored as **strings** in YAML; the loader parses them into `Decimal` (research §6). Storing as floats in YAML would defeat the `Decimal` precision choice on the very first hop.

**Rationale**:

- Per-1k-tokens is the unit Google publishes. Storing it as-published avoids unit-conversion bugs.
- Splitting input/output is mandatory — Gemini Pro's output is 4× the input price. A single price would silently double-bill the wrong direction.
- An unknown model identifier raises `ModelCallConfigError` at load time rather than computing a zero cost (FR-010).

**Alternatives considered**:

- Per-million-tokens: same data, different unit. Per-1k is what Google publishes.
- Region-keyed nested map (`model.region.input_per_1k_tokens`): premature — we're single-region.
- Embedding prices in `configs/models.yaml`: conflates two concerns (model selection vs cost calculation); changing a price would force a `configs/models.yaml` change.

**Anchor**: ADR-003 (model choice), ADR-015 (region), spec FR-010, constitution §16.

---

## §12. `configs/models.yaml` shape

**Decision**: Flat YAML, agent-keyed at the top level. One environment (constitution §8 = production-only topology, so no per-env nesting). `prompt_version` is a placeholder string `"v0001"` until T17 lands the actual prompt content under `prompts/<agent>/v0001/`.

```yaml
# configs/models.yaml
interviewer:
  model: gemini-2.5-flash
  prompt_version: "v0001"
  temperature: 0.4
  max_output_tokens: 2048
assessor:
  model: gemini-2.5-flash
  prompt_version: "v0001"
  temperature: 0.1
  max_output_tokens: 2048
planner:
  model: gemini-2.5-pro
  prompt_version: "v0001"
  temperature: 0.3
  max_output_tokens: 4096
```

Loader rejects: missing agents, unknown agents, `temperature` outside `[0.0, 2.0]`, `max_output_tokens` greater than 4096.

**Rationale**:

- Mirrors the example block in `.claude/skills/vertex-call/SKILL.md` exactly — that skill is the source of truth for how callers will use this file.
- Single environment per constitution §8 — there is no staging or dev override; the same `configs/models.yaml` ships to prod.
- The placeholder version `"v0001"` is **a string**, not a missing field, so the schema rejects an absent value but accepts the placeholder. T17 swaps the placeholder for a real version when it lands its prompt content.

**Alternatives considered**:

- Per-environment nesting (`local.interviewer.model`): violates §8.
- `prompt_version` defaulted by the loader: would silently mask T17's missing-content bug; explicit placeholder is better.

**Anchor**: constitution §8, §16; vertex-call skill `configs/models.yaml` example; Clarifications 2026-04-26 (Q5).

---

## §13. Canonical prompt SHA includes the schema

**Decision**: The SHA-256 input is the UTF-8 encoding of `json.dumps({"system_prompt": ..., "user_payload": ..., "json_schema": ..., "agent": ..., "model": ...}, sort_keys=True, ensure_ascii=False)`.

**Rationale**:

- A fixture cached against a *different schema* would be stale — the model's response shape depends on the schema. Ignoring the schema in the SHA would let a schema change silently reuse the old fixture and pass a test that should fail.
- Including `agent` and `model` is belt-and-braces — different agents calling the same model with the same prompt should not collide on a fixture.
- `sort_keys=True` makes the SHA deterministic regardless of dict-iteration order in Python 3.6+.
- `ensure_ascii=False` preserves Ukrainian characters in `user_payload` (relevant when the Interviewer's tests get added in T18).

**Alternatives considered**:

- SHA over `system_prompt + user_payload` only: vulnerable to the schema-staleness bug above.
- SHA over the full `ModelCallRequest` Pydantic dump: includes `session_id`, which is per-test-run and would never collide → every fixture would be `_unrecorded`. Bad.
- MD5 / SHA-1: collision-vulnerable; SHA-256 is the standard.

**Anchor**: spec FR-006, vertex-integration.md mock fixture design.

---

## §14. `/debug/vertex-ping` is explicitly out of T04 scope

**Decision**: T04 ships **no** HTTP route. The `/debug/vertex-ping` route mentioned in `docs/engineering/implementation-plan.md` T11 (Tier-1 deploy gate) is introduced *and removed* by T11; it imports `call_model` from this T04 wrapper.

**Rationale**:

- Spec FR-018 forbids T04 from changing `app/backend/openapi.yaml`. Adding a route would break the T02 regen-and-diff guardrail.
- T11's task description explicitly says the debug routes are removed before that PR closes — they are scaffolding, not product surface.
- Keeping the route out of T04 lets T11 own its own scope (deploy + smoke + cleanup) without T04 having to model debug-route lifecycle.

**Alternatives considered**:

- Ship a `/debug/vertex-ping` in T04 behind a feature flag: violates §9's "dark launch by default" only if the flag is on by default; even off, it's still in `openapi.yaml` and that's an FR-018 violation.

**Anchor**: spec FR-018, implementation-plan T11 description.

---

## §15. `structlog` event names and fields

**Decision**: One log event per call attempt's terminal state, name `llm_call`. Carries the following keys (and **only** these keys — no prompt text, no output text, no candidate PII):

```python
log.info(
    "llm_call",
    trace_id=trace_id,                # UUID string
    agent=req.agent,                  # "interviewer" | "assessor" | "planner"
    model=cfg.model,                  # "gemini-2.5-flash" etc.
    model_version=raw.model_version,  # "gemini-2.5-flash-001" etc.
    session_id=str(req.session_id),
    outcome=outcome,                  # "ok" | "schema_error" | "timeout" | ...
    attempts=attempts,
    latency_ms=latency_ms,
    cost_usd=str(cost_usd),           # Decimal → str for JSON friendliness
    input_tokens=raw.input_tokens,
    output_tokens=raw.output_tokens,
)
```

**Rationale**:

- The structlog pipeline configured in T02 already runs `pii_redaction_processor` (strips `candidate_email` and email-shaped substrings from the `event` message). Defence-in-depth.
- Constitution §15 forbids candidate text in logs. The wrapper *never* logs prompt or output text — operators look up the trace record by `trace_id` if they need the content.
- A single canonical event name (`llm_call`) is cheap to grep for and easy to alert on (FR-013).

**Alternatives considered**:

- One log event per attempt (including each retry) instead of one per terminal state: would 3× log volume on transient failures; the trace record's `attempts` field already captures the count.
- Log the prompt SHA: useful for debugging but redundant with the trace record. Skipping keeps the log line compact.

**Anchor**: constitution §15; T02 `app/backend/logging.py` `pii_redaction_processor`.

---

## Summary

All 15 decisions below spec altitude resolved. No NEEDS CLARIFICATION remains. The implementation now has:

- A specific SDK (`google-genai`) with a specific configuration shape.
- A specific retry library (`tenacity`) with a specific budget (3 attempts uniform).
- A specific test runner mode (`pytest-asyncio` auto).
- A specific schema-validation strategy (two-stage; pydantic Stage 2).
- A specific fixture layout (file-per-prompt-SHA, one JSON envelope).
- A specific cost arithmetic precision (`Decimal`).
- A specific Settings shape and a specific production-mode startup-refusal mechanism.
- A specific guardrail mechanism (ripgrep + script + pre-commit + CI).
- A specific interface shape (`Protocol`s, in-memory implementations, async methods).
- A specific pricing-table shape (per-1k tokens, USD, per-model).
- A specific models.yaml shape (flat, agent-keyed, placeholder version).
- A specific prompt-SHA recipe (system + user + schema + agent + model).
- A specific scope boundary (`/debug/vertex-ping` is T11, not T04).
- A specific log event (`llm_call`, fixed key set, no PII / prompt / output text).

`/speckit-tasks` can now break this into discrete, verifiable units of work.
