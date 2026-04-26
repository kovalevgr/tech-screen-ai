# Phase 1 Data Model — T02 FastAPI Skeleton

**Feature**: [spec.md](./spec.md) · **Plan**: [plan.md](./plan.md)
**Date**: 2026-04-24

T02 introduces no persistent data (no tables, no files storing candidate/session state). The "entities" below are the in-process objects the reviewer and every later backend task must be able to point at. Each row maps an entity to the file that realises it in the PR and to the validation rule(s) that protect its contract.

---

## Entities

### 1. `FastAPI` application instance

| Field              | Value                                                                                                                                                                        |
| ------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Definition         | The single module-level `app = FastAPI(...)` object that is the backend's composition root. Imported as `app.backend.main:app` — matches Dockerfile CMD verbatim.            |
| File               | `app/backend/main.py`                                                                                                                                                        |
| Routes at T02 close | `GET /health` only. No other public routes. No CORS middleware. No auth middleware.                                                                                         |
| Boot preconditions | None — no required env var, no DB handle, no outbound connection. FR-003 invariant.                                                                                          |
| Lifecycle          | Created at module import. Reused by uvicorn (prod), `TestClient` (tests), and the OpenAPI generator (`generate_openapi.py` imports the same module).                         |
| Validation         | `uvicorn app.backend.main:app` starts locally in < 5 s with no env vars set (FR-001, SC-001). `TestClient(app)` constructs without raising inside tests (FR-009 precondition). |
| Metadata           | `title="TechScreen Backend"`, `version=<pyproject version>`, `description` and contact fields left empty until a later task that needs them.                                  |

### 2. `HealthResponse` contract object

| Field         | Value                                                                                                                                                     |
| ------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Definition    | The JSON body shape returned by `GET /health`. Realised as a Pydantic `BaseModel` so FastAPI's OpenAPI export captures the schema in `openapi.yaml`.       |
| File          | `app/backend/main.py` (declared alongside the `app`).                                                                                                     |
| Schema        | `status: Literal["ok"]`, `service: Literal["techscreen-backend"]`, `version: str`.                                                                         |
| Validation    | The smoke test (`test_health.py`) asserts HTTP 200 and that `response.json()` matches the literal field values (with `version` matching `importlib.metadata.version("techscreen")` or the fallback documented in research §7). |
| Stability     | `contracts/backend-contract.md` classifies this as a **stable** contract. Changes require a new spec + ADR per §14/§17.                                    |

### 3. `PIIRedactionProcessor` (structlog processor)

| Field               | Value                                                                                                                                                                                                                   |
| ------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Definition          | A pure function `(logger, method_name, event_dict) -> event_dict` registered in the structlog processor pipeline. Replaces values in the PII field allow-list with `"<REDACTED>"` and strips email patterns from the `event`/`message` string with `"<REDACTED_EMAIL>"`. |
| File                | `app/backend/logging.py`                                                                                                                                                                                                |
| Allow-list at T02   | `{"candidate_email"}`. Extension procedure: a later task adds a field name to the allow-list AND adds a matching assertion to `test_logging_pii.py`. Both changes must land in the same PR.                              |
| Free-text patterns  | Email regex `[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}` (permissive subset — false-positives over false-negatives).                                                                                                  |
| Side effects        | None. Pure input → output transform. No logging, no I/O.                                                                                                                                                                |
| Validation          | `test_logging_pii.py` exercises both the structured-field redaction and the free-text redaction on a single log call; asserts neither `x@y.com` substring appears in the serialised output.                             |
| Constraint          | Must run **before** any renderer (JSON or console) in the processor pipeline. Order matters — redaction on a stringified log record is harder than redaction on the event dict.                                         |
| Stability           | Field allow-list is extension-only; a later task can **add** fields but cannot remove them. Removing a field would weaken §15 and requires an explicit ADR.                                                             |

### 4. `OpenAPIDocument` (serialised contract artefact)

| Field                   | Value                                                                                                                                                                         |
| ----------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Definition              | The committed YAML file describing every backend endpoint, generated deterministically from the `FastAPI` instance.                                                           |
| File                    | `app/backend/openapi.yaml` — this **is** the contract; no duplicate lives under `specs/005-t02-fastapi-skeleton/contracts/`.                                                  |
| Producer                | `app/backend/generate_openapi.py` — canonical invocation `docker compose -f docker-compose.test.yml run --rm backend python -m app.backend.generate_openapi` writes; `--check` exits non-zero on drift. (See research §8 for the Docker-first decision.) |
| Serialisation contract  | `yaml.safe_dump(..., sort_keys=True, allow_unicode=True, default_flow_style=False)`. Byte-deterministic across runs and machines.                                             |
| Contents at T02 close   | One path (`/health`), one operation (`GET`), one response schema (`HealthResponse`). Info block populated from the `FastAPI(title=..., version=...)` constructor.              |
| Validation              | `test_openapi_regeneration.py` regenerates in memory and asserts byte-equality with the committed file. Emits a unified-diff head on failure.                                  |
| Stability               | **Stable** — changes are additive and must be accompanied by a regenerated file in the same PR.                                                                               |

### 5. `LoggingConfiguration` (imperative init, not an entity per se)

| Field                 | Value                                                                                                                                                         |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Definition            | The `structlog.configure(...)` call made once at import time from `app/backend/logging.py`, wired up by `app/backend/main.py` before `FastAPI()` constructs.   |
| Inputs (env)          | `LOG_FORMAT` (default `"json"`), `LOG_LEVEL` (default `"INFO"`). Unknown values warn-and-fallback (research §7).                                               |
| Processor pipeline    | `merge_contextvars → add_log_level → TimeStamper(iso, utc) → pii_redaction_processor → EventRenamer("message") → JSONRenderer() | ConsoleRenderer()`.        |
| Validation            | `test_logging_pii.py` uses the `captured_logs` fixture to swap the renderer for a list-appender while keeping every upstream processor — so the redaction processor is the exact one prod uses. |
| Constraint            | Called exactly once. Tests do not mutate the global config; the `captured_logs` fixture swaps config on `yield`, restores on teardown.                         |
| Stability             | **Semi-stable** — processor **order** is stable (§15 risk if redactor moves after the renderer). Adding a processor before the redactor is a reviewer concern. |

---

## Relationships

```text
FastAPI app ──uses──► LoggingConfiguration ──contains──► PIIRedactionProcessor
            └─declares──► HealthResponse ──described-in──► OpenAPIDocument
            └─produces (via generator) ──► OpenAPIDocument

OpenAPIDocument ──validated-by──► test_openapi_regeneration (byte-equal to file on disk)
HealthResponse ──exercised-by──► test_health (request → 200 + shape)
PIIRedactionProcessor ──exercised-by──► test_logging_pii (redaction both shapes)

pyproject.toml [project].dependencies ──consumed-by──► Dockerfile `runtime` stage (`uv sync --frozen --no-dev`)
                                      └─consumed-by──► Dockerfile `dev` stage (`uv sync --frozen` — adds dev group)
```

---

## Validation rules (collected)

All validation runs inside the Dockerfile `dev` stage (constitution §7; research §8).

1. `docker compose up backend` reaches `Application startup complete` within 5 s and `GET /health` returns 200 (FR-001, FR-002, FR-003, SC-001).
2. `GET /health` body matches the `HealthResponse` schema (FR-002, FR-009).
3. `docker compose -f docker-compose.test.yml run --rm backend python -m app.backend.generate_openapi --check` exits 0 on the committed tree (FR-005, SC-003).
4. A log call `logger.info("foo bar x@y.com", candidate_email="x@y.com")` produces a serialised record in which neither `x@y.com` nor `candidate_email="x@y.com"` appears; `"<REDACTED>"` appears in place of the field value; `"<REDACTED_EMAIL>"` appears in place of the free-text substring (FR-006, FR-007, FR-010, SC-004). The same redaction holds for Cyrillic IDN emails (`студент@приклад.укр`) — see `test_cyrillic_idn_email_redacted_in_freetext`.
5. `docker compose -f docker-compose.test.yml run --rm backend pytest app/backend/tests/` exits 0 in under 30 s on a clean tree (FR-008, FR-009, FR-010, SC-002).
6. `docker compose -f docker-compose.test.yml run --rm backend sh -c "ruff check app/backend && mypy app/backend"` exits 0 on every T02-introduced file (FR-012, SC-006).
7. `pre-commit run --all-files` exits 0 on host — pre-commit operates around `git commit`, not inside the container (FR-014).
8. No T02 file contains a secret value, a credential, or a real PII sample (FR-014; enforced by `gitleaks` + `detect-secrets`).
9. T02 introduces no new endpoint besides `/health`, no migration, no Vertex call, no auth middleware, no CORS (FR-011; reviewer diff check). Dockerfile and compose edits are in scope per research §8.

No other data-model concerns — T02 has no persistence, no migrations, no LLM inputs/outputs, no rubric references. Those arrive in T04, T05, T08, T15, and later.
