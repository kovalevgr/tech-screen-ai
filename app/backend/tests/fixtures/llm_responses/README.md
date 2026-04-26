# LLM response fixtures

Deterministic fixtures consumed by the `MockVertexBackend` in dev and CI.
Production never reaches this code: `Settings.assert_safe_for_environment()`
refuses to start a production worker with `LLM_BACKEND=mock`
(spec FR-007 / SC-010).

## Layout

```
fixtures/llm_responses/
├── interviewer/
│   └── <sha256-hex>.json
├── assessor/
│   ├── <sha256-hex-valid>.json
│   └── <sha256-hex-invalid>.json   # deliberately schema-invalid; used by T040
├── planner/
│   └── <sha256-hex>.json
└── _unrecorded/
    └── .gitkeep                    # contents .gitignored except .gitkeep
```

One JSON envelope per **canonical prompt SHA-256**. Filenames are the
full 64-hex-character SHA, no extension other than `.json`.

## SHA recipe (frozen at T04)

```python
canonical_prompt_payload = json.dumps(
    {
        "system_prompt": <str>,
        "user_payload": <str>,
        "json_schema": <dict | None>,
        "agent": <str>,
        "model": <str>,
    },
    sort_keys=True,
    ensure_ascii=False,
)
sha = hashlib.sha256(canonical_prompt_payload.encode("utf-8")).hexdigest()
```

Including `json_schema` and `model` in the SHA prevents stale-fixture
bugs: changing the agent's schema OR the resolved model produces a
different SHA, so the old fixture is **not** served against the new
contract. See `specs/007-t04-vertex-client-wrapper/research.md` §13 for
the rationale.

## Envelope shape

```json
{
  "text": "...",                      // raw response text; for JSON-mode this is JSON-encoded
  "input_tokens": 132,                // prompt-side token count Vertex would bill
  "output_tokens": 87,                // response-side token count Vertex would bill
  "model": "gemini-2.5-flash",        // resolved model id
  "model_version": "gemini-2.5-flash-001"  // specific model revision
}
```

The envelope mirrors the
`app.backend.llm._backend_protocol.RawBackendResult` Pydantic model.
The mock backend validates the parsed envelope at load time — a malformed
fixture file raises `RuntimeError` immediately so the cause is obvious.

For schema-validated calls (the common case), the `text` field contains
a JSON-encoded string that the wrapper parses and validates against the
agent's `json_schema`. The schema-INVALID fixture under
`assessor/5504391a4d...json` is intentionally missing the
`level_estimate` and `confidence` required fields so the wrapper's
Stage-2 validator raises `VertexSchemaError` (see test T040).

## `_unrecorded/` capture rule

When the mock backend is asked for a prompt whose SHA is not in the
fixture set:

1. The backend computes the canonical envelope:
   `{agent, model, system_prompt, user_payload, json_schema}`.
2. Writes `<fixtures_dir>/_unrecorded/<sha>.json` so a developer can see
   exactly what was asked.
3. Raises `RuntimeError("fixture missing for prompt SHA <hex>; see
   _unrecorded/<sha>.json")`.

The `_unrecorded/` directory is committed (with a `.gitkeep`) so the path
is always present; its contents are `.gitignore`d at the directory
level — only the `.gitkeep` is tracked.

## Promotion flow

When you add a test that calls a new prompt:

1. **Run the test once** — it fails with the missing-fixture
   `RuntimeError`. The error message includes the SHA and the
   `_unrecorded/<sha>.json` path.
2. **Inspect** `_unrecorded/<sha>.json` to confirm the captured envelope
   matches what your test intends to send. (If you spot prompt drift,
   fix it in the test's prompt source — usually
   `app/backend/tests/llm/_test_prompts.py` — and rerun step 1.)
3. **Hand-craft a response envelope** that satisfies the agent's schema
   for that prompt. (Or, in T17+ scope, replay against real Vertex via
   a one-off recording script — out of T04 scope.)
4. **Move** the file:
   ```bash
   mv app/backend/tests/fixtures/llm_responses/_unrecorded/<sha>.json \
      app/backend/tests/fixtures/llm_responses/<agent>/<sha>.json
   ```
5. **Edit** the moved file to set the `text`, `input_tokens`,
   `output_tokens`, `model`, and `model_version` fields.
6. **Re-run the test** — the fixture lookup hits, the test passes.

## When SHAs change

If the SHA constants in
`app/backend/tests/llm/_test_prompts.py` need to be updated (because a
test prompt changed), the simplest path is:

```bash
uv run python -c "from app.backend.tests.llm._test_prompts import \
  INTERVIEWER_SHA, ASSESSOR_SHA, ASSESSOR_BROKEN_SHA, PLANNER_SHA; \
  print(INTERVIEWER_SHA); print(ASSESSOR_SHA); \
  print(ASSESSOR_BROKEN_SHA); print(PLANNER_SHA)"
```

Then `mv` the existing fixture files to their new SHA-keyed names.

## Constitution invariants this convention preserves

- **§15 PII**: all committed test prompts are synthetic (no real
  candidate data); the `_unrecorded/` directory may contain whatever was
  asked but is not committed beyond the `.gitkeep`.
- **§16 Configs as code**: fixtures are tracked in Git, reviewed via PR.
- **FR-005 / FR-006**: dev and CI run without GCP credentials because
  the mock backend never reaches the network.
