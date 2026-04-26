# Anti-Patterns

Things we have explicitly decided not to do, with the reason. Each entry is short: what not to do, why, and what to do instead. When you see code or a design that matches one of these, flag it in review.

---

## Architecture

### Letting the LLM decide "what happens next"

**Don't.** Have the model pick the next state, next question, next agent, or the condition to exit a loop.

**Why.** Non-reproducible sessions, unbounded cost, impossible to calibrate, impossible to replay. See constitution §2 and ADR-005.

**Do instead.** Deterministic Python state machine owns flow. LLMs produce content inside states. Routing decisions use typed JSON fields (enums / booleans), not free text.

### Single monolithic agent

**Don't.** Ask one LLM call to do dialogue, question selection, and scoring in one go.

**Why.** Dialogue fluency and rubric-grounded scoring pull the model in opposite directions. You get weaker output and uncalibrated behaviour.

**Do instead.** Separate Interviewer, Assessor, and Pre-Interview Planner agents with focused prompts. See ADR-004.

### Many tiny specialised agents

**Don't.** Introduce a fourth or fifth runtime agent for a tangentially related subtask ("topic classifier", "tone checker", "summariser") without strong evidence.

**Why.** Each new agent doubles calibration work, adds latency, and multiplies failure modes. For our MVP scale the cost-benefit is negative.

**Do instead.** Extend an existing agent's prompt or add a deterministic post-processing step.

### Separate vector database

**Don't.** Introduce Pinecone / Qdrant / Weaviate at MVP scale.

**Why.** Another operational surface, billing, backup regime, consistency problem. See ADR-007.

**Do instead.** `pgvector` in the same Postgres. Revisit when recall or latency stops being good enough.

### Adding a service "because microservices"

**Don't.** Split a responsibility into a new service when a module would do.

**Why.** Cross-service boundaries add latency, complicate transactions, and increase ops burden. They are worth the cost when ownership boundaries, scaling profiles, or deployment independence demand it — and not otherwise.

**Do instead.** Start as a module inside `app/backend/`. Promote to a separate service when you can name the concrete reason.

---

## Data

### `UPDATE` or `DELETE` on audit tables

**Don't.** Mutate rows in `turn_trace`, `assessment`, `assessment_correction`, `turn_annotation`, `audit_log`, `session_decision`.

**Why.** Destroys audit history. See constitution §3 and ADR-019.

**Do instead.** Corrections are new rows. Effective values are computed via "latest correction wins" views.

### Mutating a rubric in place

**Don't.** Edit `rubric_node` rows of an existing `rubric_tree_version`.

**Why.** Breaks the immutable snapshot contract. Old sessions would silently gain new meanings. See ADR-018.

**Do instead.** Create a new `rubric_tree_version`. Existing sessions keep their `rubric_snapshot` and remain interpretable.

### Losing the `rubric_snapshot` link

**Don't.** Let `interview_session.rubric_snapshot` be nullable, optional, or lazily resolved from the live rubric.

**Why.** One missing snapshot and a future rubric edit corrupts the historical record.

**Do instead.** `NOT NULL`, enforced at DB level and in the code path that creates a session.

### Destructive DDL without an ADR

**Don't.** `DROP COLUMN`, `DROP TABLE`, narrowing `ALTER TYPE`, `TRUNCATE` on production data.

**Why.** Forward-only migrations (constitution §10). A destructive change is a separate class of decision.

**Do instead.** Multi-migration sequence (add → dual-write → backfill → remove reads → drop). Write an ADR even for the drop step.

### Mocking the database in tests

**Don't.** Replace the DB with in-memory mocks or SQLite stand-ins for integration tests.

**Why.** Mocks hide migration errors, constraint violations, concurrency bugs, and query-plan regressions that appear only against the real engine.

**Do instead.** Integration tests hit real Postgres in Docker. Unit tests mock only the LLM boundary.

---

## Secrets and credentials

### Committing `.env`

**Don't.** Commit `.env`, `credentials.json`, service-account keys, or any file containing real values.

**Why.** Git history is forever. A leaked key cannot be revoked retroactively from other clones. Constitution §5.

**Do instead.** `.env.example` with keys only. Real values in `.env` (gitignored) locally and Secret Manager in prod. `pre-commit` + `gitleaks` catch slips.

### Creating JSON service-account keys

**Don't.** Run `gcloud iam service-accounts keys create`.

**Why.** JSON keys are long-lived, high-blast-radius credentials with poor rotation ergonomics. Constitution §6 and ADR-013.

**Do instead.** Workload Identity Federation for CI → GCP. User OAuth for local developers. No JSON keys exist in this project.

### Logging a secret

**Don't.** `logger.info(f"connecting with {api_key}")` — even in debug, even in a test fixture.

**Why.** Logs persist. Logs are exported. Logs are searched. One debug-level leak becomes a SIEM alert.

**Do instead.** Structured log with secret fields filtered by the formatter. Known keys (`password`, `api_key`, `token`, `secret`, `bearer`) are stripped automatically.

### Putting a secret in an LLM prompt

**Don't.** Include API keys, DB URLs, or other secrets in the content sent to Vertex. Even in a "helper" prompt.

**Why.** The request travels through a third party; tokens are visible in adapters, proxies, and observability stacks.

**Do instead.** Pass only what the model needs. Credentials are never what it needs.

---

## LLM usage

### Retrying until success

**Don't.** Wrap an LLM call in `while True: try: ... except: continue`.

**Why.** One bug and you burn $500 in 20 minutes. Observed in anger during development of earlier internal prototypes.

**Do instead.** Bounded retries defined in the adapter (ADR policy), per-session cost ceiling that halts the session on breach.

### Ignoring the JSON schema

**Don't.** Parse LLM output with ad-hoc regex or `json.loads` without validation.

**Why.** Models produce creative JSON under stress. Silent acceptance of malformed output corrupts downstream data.

**Do instead.** Vertex JSON mode + Pydantic schema validation in the wrapper. Schema failure raises `VertexSchemaError` immediately (per Clarifications 2026-04-26 the wrapper does not retry on schema failures; per-agent retry / fallback / escalation lives in the agent module).

### Embedding the full rubric in the Assessor prompt

**Don't.** Paste the entire rubric tree into the Assessor's system prompt template.

**Why.** Wastes tokens, drifts as the rubric grows, makes prompts hard to diff.

**Do instead.** Pass the relevant rubric subset as structured input (`rubric_snapshot`). The prompt references it, the builder injects it.

### Hard-coding model names in application code

**Don't.** `model = "gemini-2.5-flash"` inside a service function.

**Why.** A model swap is then a code change, not a config change — which means no easy A/B or fallback.

**Do instead.** Model name from `configs/models.yaml`, loaded via Pydantic settings.

### Prompt edits in place

**Don't.** Edit `prompts/assessor/v0003/system.md` after it was merged.

**Why.** Silent drift destroys calibration baselines. Nobody can tell which v0003 produced which metric.

**Do instead.** v0004. Even for a one-word fix. See `./prompt-engineering-playbook.md`.

---

## Testing

### Skipping failing tests

**Don't.** Add `@pytest.mark.skip` to a failing test without a linked issue and an owner.

**Why.** Skip decorators age into silent erosion of coverage.

**Do instead.** Fix the test or delete it with a commit message explaining why.

### Writing tests that assert implementation

**Don't.** Assert that a component renders a specific Tailwind class or that a service calls a specific repository function.

**Why.** Refactors break tests that were supposed to guarantee behaviour, not shape.

**Do instead.** Assert on observable behaviour: API responses, DOM text, state transitions.

### Test that passes because of a real side effect

**Don't.** Write a test that reads from the real Vertex endpoint, a real SendGrid account, or a real GCS bucket.

**Why.** Flaky, slow, expensive, and impossible to run offline.

**Do instead.** Mocks at the adapter boundary. `vertex-mock` service in dev and CI.

---

## Process

### Silently deviating from the constitution

**Don't.** Make a local decision that violates an invariant "just for this sprint".

**Why.** Invariants exist because the local reasoning is not the whole picture. Exceptions cascade.

**Do instead.** Either the constitution is wrong and gets a supersede-via-ADR, or the invariant holds. No third option.

### Writing code without a spec

**Don't.** Skip `/specify` → `/plan` → `/tasks` for anything non-trivial.

**Why.** Specs are the cheapest place to correct design. Code is the most expensive.

**Do instead.** Trivial-changes carve-out (typos, deps, formatting) skips the flow. Everything else goes through it.

### "Temporary" code with no owner

**Don't.** Leave `TODO` or `FIXME` without owner and ticket.

**Why.** Ghost code is never cleaned up. The original author leaves; the marker remains.

**Do instead.** `# TODO(@owner, #123): short description.` Or delete the comment and write the code properly now.

### Claude Code generating without reading

**Don't.** Let an AI write code without reading `CLAUDE.md`, the relevant ADRs, and the constitution.

**Why.** The resulting code does not know about our invariants, fails review, and wastes time.

**Do instead.** Agents read the floor before making non-trivial changes. This is enforced by reviewer sub-agent and by `CLAUDE.md` being loaded automatically.
