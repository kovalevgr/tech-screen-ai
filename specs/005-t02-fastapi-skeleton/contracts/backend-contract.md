# Backend Contract — T02 FastAPI Skeleton

**Feature**: [../spec.md](../spec.md) · **Plan**: [../plan.md](../plan.md)
**Stable from**: T02 merge onwards.
**Consumers**: T03 (Next.js skeleton — generates/hand-writes the API client against `app/backend/openapi.yaml`), T04 (Vertex wrapper — depends on the logger being PII-safe), T05 (DB schema — extends the PII field allow-list when candidate fields arrive), T06 (Cloud Run readiness probe — hits `/health`), T07 (observability — consumes the structured logger), T09 (Docker stacks — runs the uvicorn CMD), T10 (CI — runs the backend test suite), `reviewer` sub-agent.

This is a single consolidated contract covering the four surfaces T02 commits to: the OpenAPI artefact, the `GET /health` shape, the PII-safe logging discipline, and the drift-detection mechanism. A later task may **extend** any of them additively; breaking changes (rename, remove, narrow exit semantics, remove field from the PII allow-list) require an ADR and a plan update referencing this file.

---

## Surface 1 — OpenAPI contract artefact

### Location

`app/backend/openapi.yaml` — committed. This is the canonical file. No duplicate lives in `specs/005-t02-fastapi-skeleton/contracts/` because that would create two sources of truth that the drift-check test could not reconcile.

### Producer

Constitution §7 requires every documented backend command to run inside the canonical container:

```bash
# Writes app/backend/openapi.yaml
docker compose -f docker-compose.test.yml run --rm backend \
    python -m app.backend.generate_openapi

# Dry-run; exits 1 on drift with a unified-diff head
docker compose -f docker-compose.test.yml run --rm backend \
    python -m app.backend.generate_openapi --check
```

The module entrypoint (`python -m app.backend.generate_openapi [--check]`) is the frozen contract — wrapping it in `docker compose run` is the canonical invocation, but a future task substituting a different runner (e.g. a Cloud Run job) keeps the same module path.

### Serialisation guarantees

- OpenAPI version: 3.1 (produced by FastAPI 0.115+).
- YAML form: `yaml.safe_dump(..., sort_keys=True, allow_unicode=True, default_flow_style=False)`.
- Byte-deterministic: same tree, same FastAPI version, same Python version → same bytes. The drift-check test (`test_openapi_regeneration.py`) asserts this.

### Contents at T02 close

- One path: `/health`.
- One operation: `GET /health`.
- One response schema: `HealthResponse` (see surface 2).
- Info block: `title = "TechScreen Backend"`, `version = <pyproject version>`.

### Stability

- Endpoint list is **extension-only**. Adding a path is additive and requires regenerating the file in the same PR.
- The generator command signature (`python -m app.backend.generate_openapi [--check]`) is **frozen**; renaming it requires an ADR.
- The serialisation options (sort_keys=True, allow_unicode=True, default_flow_style=False) are **frozen** — changing any of them churns the byte representation without semantic gain.

---

## Surface 2 — `GET /health` contract

### Request

```http
GET /health HTTP/1.1
```

- No authentication required.
- No headers required beyond standard HTTP.
- No query parameters.

### Response

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "status": "ok",
  "service": "techscreen-backend",
  "version": "<semver string>"
}
```

| Field     | Type                              | Invariant at T02                                                                           |
| --------- | --------------------------------- | ------------------------------------------------------------------------------------------ |
| `status`  | `Literal["ok"]`                   | Always `"ok"` at T02. New values (`"degraded"`, `"unavailable"`) belong to a future `/ready`, not here. |
| `service` | `Literal["techscreen-backend"]`   | Constant. Operators / Cloud Run probes rely on this to identify the image.                 |
| `version` | `string` (semver)                 | `importlib.metadata.version("techscreen")`; fallback `"0.0.0"` when the package is not installed. |

### Stability

- The three field names are **frozen**.
- Additional fields are **extension-allowed** (e.g. `revision_id` if a later deploy task wants it) — they MUST be optional from a client's perspective.
- Removing a field is a **breaking change** requiring an ADR.

### Non-goals

- `/health` is **not** a readiness probe that checks DB or Vertex reachability. Those are deferred to `/ready` (owned by whichever task first needs it — likely T05 or T06a).
- `/health` is **not** authenticated and MUST NOT become authenticated — Cloud Run probes hit it anonymously.

---

## Surface 3 — PII-safe logging contract

### Logger

- Library: `structlog` 24.x.
- Entry point: `app/backend/logging.py` exposes `configure_logging()` (called once from `main.py`) and a convention that every new module does `logger = structlog.get_logger(__name__)`.
- Renderer: JSON by default (`LOG_FORMAT=json` — matches Dockerfile ENV), `console` when `LOG_FORMAT=console` (dev convenience).

### Processor pipeline (order-sensitive)

1. `merge_contextvars` — per-request context.
2. `add_log_level`.
3. `TimeStamper(fmt="iso", utc=True)`.
4. **`pii_redaction_processor`** — redacts field values + free-text email patterns.
5. `EventRenamer("message")` — renames structlog's `event` key to the conventional `message`.
6. `JSONRenderer()` or `ConsoleRenderer(colors=True)`.

**Invariant**: the PII redactor MUST run before any renderer. A processor inserted after step 4 that re-introduces raw PII into a field is a contract violation.

### PII field allow-list

At T02 close:

```python
PII_FIELDS: frozenset[str] = frozenset({"candidate_email"})
```

**Extension procedure** (for every later task that introduces a new PII-carrying field):

1. Add the field name to `PII_FIELDS`.
2. Add an assertion to `test_logging_pii.py` that exercises the new field with a realistic value and confirms redaction.
3. Both changes MUST land in the same PR as the code that starts writing the field.

**Removal**: forbidden except via an ADR that supersedes constitution §15.

### Free-text redaction

- Applied to the `event`/`message` string of every log record.
- Pattern: `r"[\w.+%-]+@[\w.-]+\.[\w-]{2,}"` (Unicode-aware email regex).
- `\w` defaults to `re.UNICODE` for `str` patterns in Python 3, so the redactor catches Latin (`x@y.com`), Cyrillic IDN (`студент@приклад.укр`), and Punycode (`student@xn--p1ai`) variants alike.
- Replacement: the literal string `<REDACTED_EMAIL>`.
- False-positive posture: a commit hash or synthetic string that happens to match the email regex will be redacted. This is intentional — PII safety beats logging fidelity.

### Structured-field redaction

- Applied to any key present in `PII_FIELDS`.
- Replacement: the literal string `<REDACTED>`.
- The key itself is preserved (so that operators can still see the shape of the record); only the value is replaced.

### Test contract

`test_logging_pii.py` MUST:

1. Emit a record `logger.info("foo bar x@y.com", candidate_email="x@y.com")` (matching the acceptance clause from `docs/engineering/implementation-plan.md`, T02).
2. Assert the serialised record contains neither `x@y.com` nor `candidate_email="x@y.com"` (no matter how quoted / nested).
3. Assert `<REDACTED>` appears in place of the field value.
4. Assert `<REDACTED_EMAIL>` appears in place of the free-text substring.
5. Assert a non-PII record (e.g. `logger.info("app started", port=8000)`) is **not** mangled.

### Stability

- Library choice (structlog) is **stable**. Swapping it would cascade through every later backend module.
- The `configure_logging()` entry point name is **frozen**.
- The processor order is **frozen**.
- The allow-list is **extension-only**; see extension procedure above.

---

## Surface 4 — Drift detection

### Where drift is caught

`app/backend/tests/test_openapi_regeneration.py` — a pytest test that:

1. Imports the generator (`app.backend.generate_openapi.build_yaml_bytes()`).
2. Runs `build_yaml_bytes()` in memory.
3. Reads the committed `app/backend/openapi.yaml` from disk.
4. Asserts the two byte strings are equal.
5. Emits the first ~40 lines of `difflib.unified_diff(...)` on failure so the reviewer can diagnose without rerunning the generator.

### Why pytest, not pre-commit

Research §3 decision: keeping drift detection inside the test suite gives the same local + CI coverage without imposing a venv-activation precondition on pre-commit. T10 (CI) inherits this test for free.

### Manual check

```bash
docker compose -f docker-compose.test.yml run --rm backend \
    python -m app.backend.generate_openapi --check
```

Exits 1 with a unified-diff head if drift exists, 0 otherwise. Useful in a tight edit loop; not required in CI.

### Stability

- The test file path (`app/backend/tests/test_openapi_regeneration.py`) is **stable** — reviewer sub-agents look for it by name.
- The `--check` flag on the generator is **stable**.

---

## Invocation preconditions (all four surfaces)

1. Docker Engine 24.x or Docker Desktop installed and running (sole contributor prerequisite for the canonical loop).
2. `docker compose build backend` has run at least once (subsequent runs reuse cached layers).
3. Current working directory is the repo root so the bind-mounts in `docker-compose.yml` resolve to actual source.

Steps 1–3 are documented in the README "Backend dev loop (Docker-first)" subsection. Native `uv run` is intentionally not part of the contract — the dev container ships `uv`, pytest, ruff, and mypy, so any "I want to call X locally" use case has an exact in-container counterpart.

---

## Summary of frozen surfaces

| Surface                                     | Frozen symbol / path                                                      |
| ------------------------------------------- | ------------------------------------------------------------------------- |
| OpenAPI file location                       | `app/backend/openapi.yaml`                                                |
| OpenAPI generator command                   | `docker compose -f docker-compose.test.yml run --rm backend python -m app.backend.generate_openapi [--check]` |
| OpenAPI YAML serialisation options          | `sort_keys=True, allow_unicode=True, default_flow_style=False`            |
| Health endpoint path                        | `GET /health`                                                             |
| Health response field names                 | `status`, `service`, `version`                                            |
| Health response literal values              | `status="ok"`, `service="techscreen-backend"`                             |
| Logger library                              | `structlog` 24.x                                                          |
| Logger config entry point                   | `app.backend.logging.configure_logging()`                                 |
| Logger processor order                      | context → level → time → **PII redact** → rename → render                 |
| PII field replacement literal               | `<REDACTED>`                                                              |
| Free-text email replacement literal         | `<REDACTED_EMAIL>`                                                        |
| PII allow-list mutation policy              | extension-only (via PR that also updates `test_logging_pii.py`)           |
| Drift-check test path                       | `app/backend/tests/test_openapi_regeneration.py`                          |
