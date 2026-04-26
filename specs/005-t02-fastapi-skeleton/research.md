# Phase 0 Research — T02 FastAPI Skeleton

**Feature**: [spec.md](./spec.md) · **Plan**: [plan.md](./plan.md)
**Date**: 2026-04-24

This document resolves the design-altitude decisions that sit below the spec but above `/speckit-tasks`. Every decision is rooted in an existing repo artefact (`Dockerfile`, `docker-compose.yml`, `pyproject.toml`, `.pre-commit-config.yaml`, constitution, ADRs) so the reviewer can verify without external searches.

---

## 1. FastAPI + uvicorn versions

**Decision**: Runtime deps — `fastapi>=0.115,<0.120` and `uvicorn[standard]>=0.32,<0.36` — added to `[project].dependencies` in repo-root `pyproject.toml`. Lockfile regenerated with `uv lock`.

**Rationale**:

- The `Dockerfile` runtime stage already hard-codes `CMD ["uvicorn", "app.backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]`. The T01 image expects these deps to exist at the image's virtualenv; T02 is the PR that satisfies that expectation.
- Version range is wide enough to absorb routine patch releases without churn, narrow enough to prevent a major-version silent upgrade (FastAPI 0.x still makes breaking changes at minor boundaries; pinning `<0.120` rather than `<2` is deliberate).
- `uvicorn[standard]` pulls `httptools` + `uvloop` + `watchfiles` — the same set the Dockerfile's single uvicorn CMD benefits from (faster loop, reload-on-edit in dev). No bespoke pin of those transitive packages; the `[standard]` extra is the documented way.
- FastAPI 0.115+ produces OpenAPI 3.1 documents by default, which is what the contract file commits to.

**Alternatives considered**:

- *Starlette directly + a hand-rolled router*: smaller dep surface, but gives up FastAPI's built-in OpenAPI schema export — which is the whole basis of the drift-check test (decision §3). Rejected.
- *Quart or Litestar*: neither matches the Dockerfile CMD. Switching would cascade to the Dockerfile, docker-compose, and T06 Cloud Run wiring. Rejected.
- *Granian or Hypercorn instead of uvicorn*: Dockerfile already pins uvicorn. No benefit at MVP scale. Rejected.

---

## 2. Deterministic OpenAPI serialisation

**Decision**: `generate_openapi.py` calls `app.openapi()` on the imported FastAPI app, passes the returned dict through `yaml.safe_dump(..., sort_keys=True, allow_unicode=True, default_flow_style=False)`, and writes the bytes to `app/backend/openapi.yaml`. A `--check` flag regenerates in memory and exits 1 (printing a short unified-diff head) if the bytes don't match the committed file.

**Rationale**:

- FastAPI produces the OpenAPI dict already; we do not handwrite the YAML.
- Python dicts preserve insertion order, but `yaml.safe_dump` does not guarantee stable ordering across runs unless `sort_keys=True`. Alphabetical key ordering gives us a byte-stable artefact that a drift test can compare directly — no "reformatted whitespace, same semantic content" ambiguity.
- `allow_unicode=True` keeps Ukrainian strings (when they eventually appear in request/response schemas via T18+) readable in the YAML rather than `\uXXXX`-escaped.
- `default_flow_style=False` forces block style, which diffs well in PR review.
- `PyYAML` is already a widely-available dep, small, and maintained. `ruamel.yaml` would preserve source ordering but that is the wrong goal here — we want deterministic ordering, not source-fidelity.

**Alternatives considered**:

- *JSON instead of YAML*: FastAPI's built-in `/openapi.json` already exists at runtime. But the implementation plan pins `openapi.yaml` (T02 description: `contract: app/backend/openapi.yaml`), so YAML is the committed artefact. The YAML form also lint-diffs better for human review.
- *`ruamel.yaml`*: preserves source ordering, which is the opposite of what we want. We need deterministic ordering that any contributor can reproduce without a pre-existing file to seed order from. Rejected.
- *Hand-write the YAML once and keep it manually*: drift-prone, violates FR-005 (regen command must reproduce committed bytes). Rejected outright.

---

## 3. Drift-detection surface

**Decision**: Drift is detected by a pytest test (`app/backend/tests/test_openapi_regeneration.py`). The test imports the regeneration helper, produces YAML bytes in memory, and asserts they equal the bytes of the committed `app/backend/openapi.yaml`. No new pre-commit hook. No CI-only check at T02 (T10 will adopt the test suite into CI, inheriting this check for free).

**Rationale**:

- A pytest test fails every developer test-run locally and CI-run in T10 — same surface, same guarantee. Contributors get immediate feedback.
- Adding a bespoke pre-commit hook would require a bash shim that runs `uv run python -m app.backend.generate_openapi --check` and mixes tool layers inside `.pre-commit-config.yaml`. The T01 pre-commit config's header comment explicitly wants pre-commit to stay minimal and non-mutating; adding a Python-venv-dependent hook there is friction. The test pattern is simpler.
- A CI-only check (T10) is too late — a contributor can already have pushed a drift-broken commit before CI catches it. A test that runs locally via `uv run pytest` is first-line defence.
- The regen script also ships a `--check` flag so a contributor can invoke drift detection outside pytest (useful in a tight edit loop): `uv run python -m app.backend.generate_openapi --check`. The flag is also what T10 will invoke in CI if the team later wants a dedicated CI step.

**Alternatives considered**:

- *Pre-commit hook using `language: system` and `pass_filenames: false`*: workable, but imposes the "contributor must have the venv activated before `git commit`" gotcha. Rejected for UX; revisitable if test-based coverage turns out to miss cases.
- *Git pre-push hook only*: too late, runs per-push, doesn't help during local testing. Rejected.
- *CI-only drift check*: leaves a local-feedback gap. Rejected.

---

## 4. Logging framework + PII redaction design

**Decision**: `structlog` 24.x configured via `app/backend/logging.py`. Processor pipeline (order matters):

1. `structlog.contextvars.merge_contextvars` — for per-request context (request id etc., wired when T02 adds the first middleware; not required at T02 close).
2. `structlog.processors.add_log_level`.
3. `structlog.processors.TimeStamper(fmt="iso", utc=True)`.
4. **`pii_redaction_processor`** (new in T02, lives in `app/backend/logging.py`).
5. `structlog.processors.EventRenamer("message")` — renames the `event` key to `message` so the serialised log records match the conventional shape.
6. `structlog.processors.JSONRenderer()` when `LOG_FORMAT=json` (the default, also set in `Dockerfile` ENV); `structlog.dev.ConsoleRenderer(colors=True)` when `LOG_FORMAT=console`.

The **`pii_redaction_processor`** is a single callable `(logger, method_name, event_dict) -> event_dict` that:

- Replaces `event_dict[k]` with the literal string `"<REDACTED>"` for every `k` in the allow-list. Initial allow-list: `{"candidate_email"}`. Extension points documented in `contracts/backend-contract.md`.
- Scans the `event`/`message` string for matches of `r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"` and substitutes `"<REDACTED_EMAIL>"` for each match.
- Leaves every other field untouched.
- Does not log, does not raise; a pure transform.

**Rationale**:

- `structlog` is the most common Python structured-logging library; it emits JSON natively, composes via processors, and the PII redactor fits the processor abstraction exactly.
- Redaction (`<REDACTED>` / `<REDACTED_EMAIL>`) rather than hashing aligns with constitution §15's primary posture ("PII lives only in designated tables, not logs"). Hashed references are the right call in `audit_log` (which is a DB table owned by T05/T18), not in application logs — hashing in logs still allows re-identification against a leaked user table.
- The email regex is intentionally permissive (matches RFC 5322 subset, not the full grammar). False positives (over-redacting e.g. a commit hash containing `@`) are preferable to false negatives (under-redacting a real email). No TLD allow-list — `.co.uk`, `.xyz`, and `.internal` all redact.
- One processor handling both shapes keeps the test surface small: FR-010 can exercise both structured-field redaction and free-text redaction in a single invocation, matching the acceptance clause verbatim (`logger called with {"candidate_email": "x@y.com", "msg": "foo bar x@y.com"}`).

**Alternatives considered**:

- *stdlib `logging` + custom JSON formatter*: works, but writing a processor-chain equivalent by hand is more code and less composable for the per-request context bindings T04/T05/T18 will need. Rejected in favour of structlog.
- *`python-json-logger`*: another option but it doesn't ship a PII-redaction hook; we'd still write the redactor ourselves, then bolt it onto a lib that's less flexible than structlog's pipeline. Rejected.
- *Hashing rather than redacting*: preserves join-ability across log lines at the cost of GDPR ambiguity. Rejected for T02; auditable cross-reference is `audit_log`'s job.
- *Redact at the log-sink (Cloud Logging filter)*: §15 wants "redaction happens before logs leave the process". Sink-side filtering would break that invariant. Rejected.

---

## 5. Test framework and layout

**Decision**: `pytest` ≥ 8.3, < 9 with `fastapi.testclient.TestClient` (wraps `httpx`). Tests live under `app/backend/tests/` as a proper package (`__init__.py`), discovered by pytest via the default collection rules. A `conftest.py` provides two fixtures:

- `client`: a session-scoped `TestClient(app)` instance (the app is cheap to build; session scope is a marginal speedup).
- `captured_logs`: a function-scoped fixture that swaps `structlog`'s configuration to a capturing processor chain, yields a list that collects serialised records, and restores the original config on teardown. Used by `test_logging_pii.py`.

Three committed tests:

- `test_health.py` — request `GET /health` via `client`, assert `response.status_code == 200`, assert the JSON shape matches `contracts/backend-contract.md` (status field + service identifier).
- `test_logging_pii.py` — bind a structlog logger inside the fixture, call `.info("foo bar x@y.com", candidate_email="x@y.com")` (mirroring the implementation plan's acceptance clause exactly), assert the captured record contains neither `x@y.com` in any field nor `x@y.com` inside the free-text message; assert the redaction literals appear.
- `test_openapi_regeneration.py` — import the generator module, produce YAML bytes in memory, assert byte-equality with the file on disk. Emits a diff head on failure for quick diagnosis.

**Rationale**:

- pytest is universally known to sub-agents and the team; no learning-curve tax.
- `TestClient` is FastAPI's canonical request-level testing surface; matches FR-009's "exercise through the application's request/response pipeline".
- Package layout with `__init__.py` is needed because the pre-commit `no-print-statements` hook uses `^app/backend/.*\.py$` as its `files` regex and then excludes `^app/backend/tests/.*$`. The exclusion works correctly whether the path is a package or a flat folder — we use a package so `from app.backend.tests.conftest import ...` works cleanly if a later task needs it.
- The `captured_logs` fixture scope is a deliberate choice: tests that assert on log output must not leak log config between tests.

**Alternatives considered**:

- *unittest*: workable, but pytest's fixture model is already the project direction (T04/T05/T18 will lean on it heavily). No reason to straddle two frameworks.
- *Putting tests under `tests/` at repo root*: farther from the code, harder to collect with module-style imports (`from app.backend.main import app`). The implementation plan's T02 acceptance explicitly names `app/backend/tests/test_health.py`. Matching that path.
- *Separate `test_logging_pii_field.py` + `test_logging_pii_freetext.py`*: the acceptance clause is a single scenario that exercises both shapes in one call. One test, two assertions, matches the acceptance clause shape.

---

## 6. Health endpoint body shape

**Decision**: `GET /health` returns HTTP 200 with JSON body:

```json
{ "status": "ok", "service": "techscreen-backend", "version": "0.0.0" }
```

Fields:

- `status`: literal `"ok"` at T02. Later tasks (T05 DB-aware readiness, T04 Vertex-aware readiness) may introduce additional status values (`"degraded"`, `"unavailable"`) on dedicated endpoints (`/ready`, `/live`) rather than mutating `/health`'s contract.
- `service`: `"techscreen-backend"` — constant, identifies the service to operators / Cloud Run probes / alerting.
- `version`: the project version from `pyproject.toml` (read at import-time via `importlib.metadata.version("techscreen")` with a fallback to `"0.0.0"` if the package isn't installed, e.g. in a pure `PYTHONPATH=$(pwd)` dev context).

Endpoint is **unauthenticated** and **unrate-limited** so that Cloud Run readiness probes (added in T06) can hit it cheaply.

**Rationale**:

- Single constant status keyword is enough for T02's role. Cloud Run's HTTP probe only cares about the 2xx/non-2xx distinction; the JSON body is for humans and observability.
- `service` + `version` makes one endpoint useful as a smoke during deploy ("which revision am I talking to?") — Cloud Run revisions serve concurrently during traffic splits (§8, §19), and a caller who hits `/health` can tell them apart by `version` once we start tagging releases.
- Keeping `/health` as pure liveness (no DB reachability, no Vertex reachability) lets later tasks introduce a richer `/ready` without renegotiating the existing `/health` contract. This is ADR-style "narrow contract, widen via addition" discipline.

**Alternatives considered**:

- *Return just `{"status": "ok"}`*: minimally correct, but gives up the service/version observability with no real cost. Rejected.
- *Fold DB and Vertex reachability into `/health` now*: violates FR-003 (no external dependencies at T02). Rejected.
- *Use `/healthz` instead of `/health`*: the implementation plan's acceptance clause says `/health`; changing to `/healthz` would cascade to T06 Cloud Run probe config and every infra doc. Rejected.

---

## 7. Boot without secrets

**Decision**: T02's import and startup path reads zero environment variables with a required-value contract. Optional env vars (documented defaults):

- `LOG_FORMAT` — `"json"` (default, matches Dockerfile ENV) or `"console"` (dev convenience). Any other value falls back to `"json"` with a single non-PII warning log.
- `LOG_LEVEL` — `"INFO"` (default). Accepts any stdlib logging level string. Invalid values fall back to `"INFO"` with a warning.

No `DATABASE_URL`, no `VERTEX_PROJECT`, no `SECRET_KEY` lookups in T02's code path. Pydantic-settings is **not** introduced in this PR; it arrives in T04/T05 when config with required fields actually exists.

**Rationale**:

- FR-003 forbids boot-time secret loading. A hard failure on a missing env var at import is a boot-time secret dependency by another name.
- Pydantic-settings is a good abstraction but introducing it at T02 with zero required fields would be ceremony-without-payoff and a dep we'd need to justify. Deferred until the first task that actually has required config.
- Defaults for `LOG_FORMAT` and `LOG_LEVEL` mirror what the Dockerfile already sets (`LOG_FORMAT=json`), so running inside the prod image and running via `uvicorn` on a laptop behave identically unless the contributor opts in to `console` mode.

**Alternatives considered**:

- *Introduce `pydantic-settings` with an empty `Settings` model*: pure ceremony; rejected for MVP.
- *Require `APP_ENV` at boot*: the Dockerfile already sets `APP_ENV=prod`; a local contributor would be forced to set it too. Rejected to keep boot friction-free; later tasks introduce `APP_ENV` as optional.
- *Fail loudly on unknown `LOG_FORMAT`*: small risk of breaking the container on a typo in a later `env_file` edit. Warn-and-fallback is safer and matches the "boot without configuration" invariant.

---

## Summary of resolved decisions

| #   | Topic                      | Decision                                                                                                                                                      |
| --- | -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Framework + ASGI server    | FastAPI 0.115.x + uvicorn[standard] 0.32+ via `[project].dependencies`.                                                                                       |
| 2   | OpenAPI serialisation      | `yaml.safe_dump(..., sort_keys=True, allow_unicode=True, default_flow_style=False)` — byte-deterministic.                                                     |
| 3   | Drift-detection surface    | pytest test against the committed YAML; regen module also exposes `--check` for manual invocation. No new pre-commit hook.                                    |
| 4   | Logger + PII redaction     | `structlog` 24.x with a `pii_redaction_processor`. Field allow-list starts at `{"candidate_email"}`; free-text email regex scrubs `event`/`message`.          |
| 5   | Test framework             | pytest 8.x + `TestClient`. Package layout under `app/backend/tests/`. Three committed tests.                                                                  |
| 6   | `/health` body shape       | `{"status": "ok", "service": "techscreen-backend", "version": "<pyproject version>"}`, unauth, unrate-limited.                                                |
| 7   | Boot without secrets       | No required env vars; optional `LOG_FORMAT` / `LOG_LEVEL` with documented defaults and warn-and-fallback on invalid. No pydantic-settings yet.                |

No open `NEEDS CLARIFICATION` markers remain. Proceed to `data-model.md`, `contracts/backend-contract.md`, and `quickstart.md`.
