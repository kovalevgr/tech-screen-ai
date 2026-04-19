---
name: vertex-call
description: Canonical wrapper for calling Vertex AI (Gemini) from backend code. Enforces the 30 s timeout, 4096 max output tokens, retry-with-backoff, per-session cost accounting, and secret-safe logging. Use when you are adding or modifying any code under app/backend/llm/** or writing a one-off script that needs a model call.
---

# vertex-call

You are about to call a Vertex AI model. This skill is the **only** sanctioned path. If you are tempted to `import vertexai.generative_models` directly from a service or a script, stop — you are violating §12 and ADR-003.

The wrapper lives at `app/backend/llm/vertex.py`. It exists so that every model call in the system looks the same, respects the caps, and produces a trace row that the reviewer can audit years later.

## When to use this skill

- Adding a new agent call (Interviewer, Assessor, Planner, or a new agent type).
- Changing retry, timeout, or cost behaviour for an existing agent call.
- Writing an ad-hoc calibration or evaluation script that needs to talk to a model.
- Swapping a mock call to a real call (or back) during local development.

## When NOT to use this skill

- Non-LLM work (pure Python, DB, HTTP). Skill does not apply.
- Editing prompt content — that is the `agent-prompt-edit` skill.
- Changing the active prompt version — that is a PR to `configs/models.yaml`, not a code change.

## The contract

Every call through `vertex.py` looks like this:

```python
from app.backend.llm.vertex import call_model, ModelCallRequest

result = await call_model(
    ModelCallRequest(
        agent="interviewer",         # one of: interviewer, assessor, planner
        session_id=session.id,       # required; propagated to trace + cost ledger
        prompt_version="v0001",      # resolved from configs/models.yaml by the caller
        system_prompt=system_text,   # string; built by app/backend/llm/agents/*
        user_payload=user_text,      # string or JSON-encoded dict
        json_schema=schema_dict,     # dict if structured output; None otherwise
        temperature=0.3,             # per-agent default from configs/models.yaml
        max_output_tokens=4096,      # HARD CAP; wrapper refuses larger
        timeout_s=30,                # HARD CAP; wrapper refuses larger
    )
)

# result: ModelCallResult
# - result.text:    raw string
# - result.parsed:  dict if json_schema was passed and parse succeeded; else None
# - result.usage:   {prompt_tokens, output_tokens, total_cost_usd}
# - result.trace_id: UUID of the turn_trace row created by the wrapper
```

Nothing else. No bare `GenerativeModel(...)`. No custom retry. No log writes from the call site (the wrapper logs).

## Invariants the wrapper enforces (so you don't have to)

- **Timeout ≤ 30 s.** Wrapper raises `ModelCallConfigError` if you pass more. Constitution §12.
- **Max output tokens ≤ 4096.** Same error class.
- **Retry policy.** Exponential backoff, max 3 attempts, only on transient errors (429, 503, timeout). Not on schema-validation failures — those bubble up.
- **Cost ledger.** Every attempt (not just the final) adds a row to `llm_cost` keyed by `session_id`. If running session total crosses $5, wrapper raises `SessionBudgetExceeded` before the call, not after.
- **Schema validation.** If `json_schema` is set, Vertex is asked for structured output **and** the wrapper validates the parsed JSON against the schema. A mismatch raises `SchemaValidationError` with the offending field.
- **Trace row.** Every call writes one row to `turn_trace` with: agent, session_id, prompt_version, prompt_hash, input tokens, output tokens, latency, cost, attempts, outcome (`ok` / `schema_error` / `timeout` / `budget_exceeded`).
- **Secret stripping.** Logging formatter drops fields named `api_key`, `token`, `bearer`, `password`, `secret` before emitting. Do not bypass. Do not format prompts into log lines yourself — log the `trace_id` and look it up.

## Model selection

You do not pick the model at the call site. The wrapper reads `configs/models.yaml`:

```yaml
# configs/models.yaml
interviewer:
  model: gemini-2.5-flash
  prompt_version: v0001
  temperature: 0.4
  max_output_tokens: 2048
assessor:
  model: gemini-2.5-flash
  prompt_version: v0001
  temperature: 0.1
  max_output_tokens: 2048
planner:
  model: gemini-2.5-pro
  prompt_version: v0001
  temperature: 0.3
  max_output_tokens: 4096
```

If you need to change the active prompt version, change this file — do **not** hardcode in Python.

## Dev / CI vs prod

- Local dev + CI default to `LLM_BACKEND=mock`. The wrapper routes to `vertex-mock` service (see `docker-compose.yml`). Same interface, deterministic canned responses keyed by prompt hash.
- Prod refuses `LLM_BACKEND=mock` at startup (`ConfigError` raised in `app/backend/main.py` bootstrap). Constitution §17, ADR-010.
- The mock returns the same `ModelCallResult` shape so call sites don't branch on environment.

## How to add a new agent call

1. Add an entry to `configs/models.yaml` under the agent key (model, prompt_version, temperature, max_output_tokens).
2. Add a prompt version folder under `prompts/<agent>/v0001/` with `system.md`, `schema.json` (if structured), `notes.md`. Use the `agent-prompt-edit` skill.
3. Add a builder in `app/backend/llm/agents/<agent>.py`. Its job: take domain objects, return `ModelCallRequest`. Builders never call the model directly — they return a request that the service passes to `call_model`.
4. Add a service method in `app/backend/services/<agent>_service.py` that invokes the builder, calls `call_model`, handles domain-level errors (schema mismatch → manual-review flag, timeout → retry at the orchestrator layer, etc.).
5. Add unit tests that mock `call_model` (not Vertex). Add one integration test that goes through `vertex-mock`.

## Testing

- **Unit tests.** Patch `app.backend.llm.vertex.call_model`. Assert the builder produces the right `ModelCallRequest`. Assert the service reacts correctly to each `ModelCallResult` shape.
- **Integration tests.** Run against `vertex-mock` via `docker-compose.test.yml`. Canned responses live in `app/backend/tests/fixtures/vertex-mock/`.
- **Load shape tests.** A dedicated test asserts the wrapper refuses `timeout_s=31` and `max_output_tokens=4097`.

## Common mistakes the reviewer will block

- `timeout_s=60` or `max_output_tokens=8000` — wrapper rejects at runtime; still, do not ship the code.
- A service that imports `vertexai.*` directly. The reviewer greps for `^from vertexai` and `^import vertexai` outside `app/backend/llm/vertex.py`.
- Logging the prompt text at `INFO`. Prompts can contain candidate answers that we do not want sprayed across logs. Log the `trace_id` and look it up in `turn_trace`.
- Catching `SessionBudgetExceeded` at the call site and continuing. If the budget tripped, the orchestrator decides (halt the session, escalate to recruiter). Don't swallow.
- Calling the model from a repository. `repositories/**` does not import from `llm/**`. Only services do.

## Before you hand off

- `ruff` clean. `mypy --strict` clean.
- New entry in `configs/models.yaml` if a new agent was added.
- Unit tests cover the success path, the schema-mismatch path, and the budget path.
- The integration test runs via `docker-compose.test.yml` without pulling real Vertex credentials.
- No `# type: ignore` on the call site unless annotated with a reason.

## References

- `app/backend/llm/vertex.py` — the wrapper.
- `docs/engineering/vertex-integration.md` — conceptual overview.
- Constitution §12, §17.
- ADR-003 (Model Garden), ADR-010 (Docker parity), ADR-013 (no JSON SA keys; WIF only).
