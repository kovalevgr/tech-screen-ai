# Feature Specification: FastAPI Skeleton (T02)

**Feature Branch**: `005-t02-fastapi-skeleton`
**Created**: 2026-04-24
**Status**: Draft
**Input**: User description: "T02 — FastAPI skeleton" (from `docs/engineering/implementation-plan.md`, Tier 1 / W1–W2)

## User Scenarios & Testing *(mandatory)*

The "users" of this feature are the humans and AI sub-agents that build every later backend-touching or contract-consuming feature: `backend-engineer` (T04 Vertex wrapper, T05 DB schema, and every later endpoint), `frontend-engineer` (T03 needs the OpenAPI contract to plan its generated client), `infra-engineer` (T06 Cloud Run + Cloud SQL + Secret Manager, T06a deploy/rollback, T09 Docker stacks — all need a backend process that boots and a health endpoint to probe), and the `reviewer` agent that validates the smoke and PII tests. Until a bootable backend process with a health endpoint, a committed OpenAPI stub, and PII-safe logging exist, the whole right-hand side of the Tier-1 dependency graph is blocked.

### User Story 1 — The backend service boots and reports health (Priority: P1)

Every downstream task assumes a runnable backend service exists. Infra work (T06 Cloud Run, T06a deploy/rollback, T09 Docker stacks) cannot wire liveness/readiness probes without a stable endpoint returning 200. Operators cannot verify a deploy succeeded without it either.

**Why this priority**: Without a bootable service and a health endpoint, T06 cannot configure Cloud Run readiness probes, T09 cannot compose the local dev stack, and T11 (Tier-1 gate) cannot execute its smoke flow. This is the single largest backend unblocker in Tier 1.

**Independent Test**: A developer or sub-agent starts the backend service locally with the documented command, calls the documented health endpoint, and receives a successful response within seconds — without any database, secret, or cloud dependency being configured.

**Acceptance Scenarios**:

1. **Given** a fresh clone with only the documented developer prerequisites installed, **When** a developer starts the backend service locally, **Then** the process begins serving HTTP within 5 seconds and does not exit.
2. **Given** the backend service is running, **When** any client issues a request to the health endpoint, **Then** the response is an HTTP success with a structured body that at minimum identifies the service and reports a healthy state.
3. **Given** the backend service has never been configured with a database URL, a Vertex credential, or any other external dependency, **When** it is started, **Then** it still boots cleanly and the health endpoint still responds — the skeleton does not require any secret to run.

---

### User Story 2 — A committed OpenAPI contract unblocks parallel sub-agent work (Priority: P1)

Constitution §14 and ADR-014 require a committed contract before parallel fan-out across layers. The backend must publish an OpenAPI artefact in the repository so the frontend engineer (T03), the infra engineer, and future backend tasks can reference a single shared source of truth. The artefact must also be regenerable from code so the two cannot drift.

**Why this priority**: Co-equal P1 with User Story 1. Without a committed contract artefact, Tiers 2, 4, 5, 6, 7, and 9 cannot dispatch parallel sub-agent work. Regeneration-from-code is what keeps the contract honest over the entire 12-week plan.

**Independent Test**: A reviewer opens the contract artefact in the repo, confirms it is a syntactically valid OpenAPI document that at minimum describes the health endpoint, then runs the documented regeneration command on a clean tree and observes that the committed file is byte-identical to the regenerated one.

**Acceptance Scenarios**:

1. **Given** the T02 branch is checked out, **When** a reviewer looks under the canonical backend folder, **Then** a committed OpenAPI contract file exists and validates against the OpenAPI specification.
2. **Given** the contract file is committed, **When** a developer runs the documented regeneration command on a clean tree, **Then** the regenerated output is byte-identical to the committed file — the regeneration is deterministic and idempotent.
3. **Given** a later PR adds or changes an endpoint in code without regenerating the contract, **When** CI or a local guardrail runs, **Then** the drift is detected and surfaces as a failure before merge.

---

### User Story 3 — Candidate PII never leaks through application logs (Priority: P1)

Constitution §15 and GDPR compliance forbid candidate PII (name, email, CV text, transcript) from appearing in logs, metrics, or trace exports. Because this is a hard invariant that regresses silently if unguarded, the skeleton must ship PII-safe logging on day one — before any endpoint that handles candidate data exists. A later task adding a candidate endpoint must not also have to invent the logging contract.

**Why this priority**: Co-equal P1. Regulatory risk (GDPR, hiring regulations) and trust: a single PII leak is a reportable incident. The cheapest time to install the redaction layer is before any endpoint needs it; retrofitting later risks gaps.

**Independent Test**: A reviewer runs the committed smoke test that emits a log record containing a plausible candidate email in both a structured field and a free-text message, then inspects the captured log output and confirms the raw email value appears in neither location — instead, a redaction or hash stands in.

**Acceptance Scenarios**:

1. **Given** the application logger is configured, **When** a log record is emitted with a field conventionally carrying candidate PII (for example, a candidate email field) **and** a free-text message containing the same email value, **Then** both the structured field and the substring inside the free-text message are redacted or hashed in the serialised output.
2. **Given** PII redaction is in place, **When** an ordinary (non-PII) log record is emitted, **Then** the record is logged normally without mangling — redaction is scoped to the documented PII field allow-list and to recognised PII patterns in free text.
3. **Given** the redaction test is part of the backend test suite, **When** a future change weakens the redaction (for example, removes a field from the allow-list), **Then** the test fails and blocks merge.

---

### User Story 4 — A smoke test and a reviewable test convention are in place (Priority: P2)

Constitution §7 requires test coverage on new code. The skeleton establishes the convention for where backend tests live, how they are run, and what a "minimum viable test" looks like — so every later backend task can copy the pattern rather than invent it.

**Why this priority**: P2 because the functional value is delivered by User Stories 1–3; this story is about ensuring the next backend task (T04 Vertex wrapper, T05 DB schema) has an obvious, already-exercised place to put its tests. Without it, every task reinvents test wiring.

**Independent Test**: A developer runs the documented backend-test command on a clean tree and sees a green result. The test that exercises the health endpoint runs as part of that command. Adding a failing assertion to that test causes the documented command to fail.

**Acceptance Scenarios**:

1. **Given** a clean tree, **When** a developer runs the documented backend-test command, **Then** at least the health-endpoint smoke test and the PII-redaction test execute and pass.
2. **Given** the test suite exists, **When** a reviewer looks at the canonical backend tests folder, **Then** the tests are discoverable without reading CI configuration, and the location matches what any future backend task would reuse.

---

### Edge Cases

- **Missing secrets or configuration.** The skeleton must start without a database connection string, without Vertex credentials, and without any Secret Manager integration. Boot and health endpoint are unconditional; later tasks (T04, T05, T06) add the dependencies and their own readiness signalling.
- **No frontend or other caller yet.** T03 is the first consumer but is developed in parallel. The skeleton does not configure CORS or authentication in T02 — those arrive with the first candidate-facing or admin-facing endpoint. The health endpoint is intentionally unauthenticated so that infra probes can reach it.
- **Empty-but-valid OpenAPI.** The contract artefact starts nearly empty (only the health endpoint). Tooling that validates OpenAPI or generates clients must accept this minimal-but-valid state.
- **Drift between code and committed contract.** If a contributor changes a route without regenerating the OpenAPI file, the mismatch must surface at commit or CI time — not at runtime in production.
- **PII appearing in unexpected shapes.** Candidate email may arrive inside a free-text error message, inside a field named something other than the canonical field name, or nested in a dict. The redaction approach must cover at least the documented PII field names and the most common free-text patterns (email addresses) — completeness across every conceivable shape is explicitly deferred to later tasks and is not a T02 scope item.
- **Empty lint/type-check targets.** The T01 guardrails already exit zero on empty targets. After T02, those targets contain real code; the same commands must still exit zero (green) on it.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The repository MUST contain a runnable backend web application under the canonical backend folder established in T01. A single documented command MUST start the service locally and bind to a documented local port.
- **FR-002**: The backend service MUST expose an unauthenticated `GET /health` endpoint that returns an HTTP 200 with a structured JSON body. The body MUST at minimum identify the service (name) and report a healthy status indicator suitable for probe consumption.
- **FR-003**: The backend service MUST boot successfully with no external dependencies configured — no database URL, no Vertex credentials, no Secret Manager binding. Boot-time failures that require a secret MUST NOT be introduced in T02.
- **FR-004**: The repository MUST commit a canonical OpenAPI contract artefact at the path referenced by the implementation plan (`app/backend/openapi.yaml`). The artefact MUST be a syntactically valid OpenAPI document that at minimum describes the health endpoint from FR-002.
- **FR-005**: The repository MUST provide a single documented command that regenerates the OpenAPI contract from the running application code. Running this command on a clean tree MUST produce output byte-identical to the committed artefact; any divergence MUST be detectable by a guardrail (local pre-commit or CI) before merge.
- **FR-006**: The backend MUST emit structured log records. Any log record that carries a value in a documented PII-carrying field (at minimum: candidate email) MUST have that value redacted or hashed in the serialised output. Redacted log records MUST remain otherwise informative (level, timestamp, message context, non-PII fields preserved).
- **FR-007**: The redaction in FR-006 MUST also strip or hash recognised PII patterns (at minimum: email addresses) that appear inside the free-text `message` portion of a log record, not only inside structured fields. The test referenced in FR-010 validates both locations.
- **FR-008**: The backend test suite MUST live under a canonical tests folder inside the backend folder (establishing the convention for every later backend task). A single documented command MUST run the whole backend test suite locally.
- **FR-009**: At least one committed smoke test MUST exercise the `GET /health` endpoint through the application's request/response pipeline (not a unit test against a function in isolation) and assert a 200 response with the expected JSON shape.
- **FR-010**: At least one committed test MUST validate FR-006 + FR-007: given a log emission carrying a PII field **and** a PII-shaped substring inside the free-text message, the captured output MUST show both locations redacted or hashed. This test MUST fail if either guard regresses.
- **FR-011**: The T02 PR MUST NOT introduce any candidate-facing endpoint, any admin-facing endpoint, any database schema or migration, any Vertex or other LLM call, or any authentication middleware. Scope is strictly the skeleton: boot, `/health`, OpenAPI contract, PII-safe logging, test wiring.
- **FR-012**: The backend lint and type-check commands established in T01 MUST continue to exit zero on the post-T02 tree. No T01 guardrails are relaxed, disabled, or worked around by T02.
- **FR-013**: The OpenAPI contract artefact, the regeneration command, and the documented `GET /health` path MUST be discoverable from a single location in the repository (the developer-setup documentation or the canonical engineering reference), so downstream agents do not have to read CI workflows or source code to locate them.
- **FR-014**: Secrets, credentials, PII samples, and real candidate data MUST NOT be committed as part of the T02 PR. This is already enforced by the T01 guardrail hooks; T02 MUST NOT bypass or weaken them.

### Key Entities

- **Backend service.** The runnable Python web application under `app/backend/`. Post-T02 it serves only the health endpoint; later tasks add candidate, session, admin, and Planner endpoints on top.
- **OpenAPI contract.** The committed artefact at `app/backend/openapi.yaml` that describes every endpoint the backend exposes. It is the shared contract referenced by every parallel sub-agent task in Tiers 2, 4, 5, 6, 7, and 9.
- **PII-safe log record.** A structured log entry in which values from documented PII fields are redacted or hashed and in which recognised PII patterns inside the free-text message are stripped.
- **Smoke test.** A request-level test that exercises the application through its real routing and middleware stack, establishing the pattern every later backend task follows.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A new contributor, starting from a tree that already satisfies T01's bootstrap, can start the backend service and receive a healthy response from `GET /health` in under 2 minutes, following only the documented developer-setup instructions.
- **SC-002**: Running the full backend test suite on the post-T02 clean tree completes in under 30 seconds and reports 100% pass, including the health-endpoint smoke test and the PII-redaction test.
- **SC-003**: Running the OpenAPI regeneration command on a clean tree completes in under 10 seconds and produces output byte-identical to the committed artefact (zero diff).
- **SC-004**: 100% of log records emitted during the PII-redaction test that carry the documented PII field or the email pattern in free text show the PII redacted or hashed — zero raw PII values leak.
- **SC-005**: The committed OpenAPI artefact validates cleanly against the OpenAPI specification (zero structural or schema errors) and describes at minimum the health endpoint.
- **SC-006**: The backend lint command and type-check command from T01 exit zero on the post-T02 tree in under the time budgets established for T01.
- **SC-007**: A reviewer (human or sub-agent) can validate T02 acceptance using only the commands documented in FR-001, FR-005, and FR-008 — without reading the implementation diff.

## Assumptions

- Python 3.12 is the backend runtime, matching the T01 baseline and the repo `Dockerfile`. Dependency management is `uv` + `uv.lock` at the repo root (per T01 Clarifications).
- FastAPI is the web framework and `uvicorn` is the ASGI server, per `docs/engineering/implementation-plan.md` T02 description and the broader architecture docs. OpenAPI is produced by the framework's built-in schema export — the regeneration command is a thin wrapper that serialises that schema to YAML deterministically.
- Structured JSON logging is used for backend log output. The redaction layer is a logging formatter or filter that runs inside the process; it is not a log-forwarder feature. This matches constitution §15 (redaction happens before logs leave the process).
- The PII field allow-list for T02 covers at minimum `candidate_email`. Additional PII field names (candidate name, CV text, transcript, user ids tied to identity) are added by the tasks that introduce those fields (T18, T20, etc.) and each such task extends the allow-list and the redaction test coverage. T02 establishes the pattern, not the full schema.
- Authentication and CORS are deliberately out of scope for T02: no endpoint requires auth yet, and no cross-origin caller exists yet (T03 is developed in parallel but the two are not wired together until T11 / later). Both are added by the first task whose endpoints require them.
- The `/health` endpoint is a simple liveness probe in T02 — service is alive and serving HTTP. Dependency-aware readiness (DB reachable, Vertex reachable) is not a T02 concern; it is added by the tasks that introduce those dependencies (T05 for DB, T04 for Vertex).
- The local developer port and any environment variables needed to run the service are documented in the developer-setup documentation. Defaults are chosen so no configuration is required to run locally.
- Constitution §15 (PII containment) is the only constitutional principle with a new test obligation in T02. §12 (LLM cost/latency caps) and §14 (contract-first) are relevant — the contract obligation is satisfied by FR-004/FR-005, and §12 has no T02 surface because no LLM call exists yet.
- No Alembic migrations, no database models, and no Vertex client code are introduced by T02. Those belong to T05 and T04 respectively and depend on T02 landing first.
- The `reviewer` sub-agent treats a passing backend-test run plus a clean OpenAPI regeneration diff as the minimum bar for T02 acceptance, alongside the existing T01 guardrails.

## Dependencies

- **Upstream (required)**: T01 (Monorepo layout + tooling baseline) — provides `app/backend/`, the backend lint/type-check commands, the pre-commit guardrails, and the Python dependency management story that T02 builds on. T02 does not re-litigate any T01 decision.
- **Downstream (blocked until T02 merges)**: T03 (Next.js skeleton — consumes the OpenAPI stub), T04 (Vertex wrapper — depends on the FastAPI app), T05 (DB schema + Alembic — depends on the FastAPI app for settings wiring), T06 (Cloud Run + Cloud SQL + Secret Manager — needs the `/health` endpoint for readiness probes), T06a (deploy/rollback), T07 (observability), T09 (Docker stacks — compose the FastAPI process), T10 (CI — runs the backend test suite), T11 (Tier-1 gate), and every later backend task.
- **External**: Public Python package registry (PyPI) must be reachable so FastAPI and its dependencies can be installed by the documented developer-setup flow. No private registry, no authenticated install step.
