# Phase 0 Research: T05a — Feature-flag infrastructure

Ten implementation-altitude decisions. Each is grounded in a constitution clause, an existing repo artefact, or a load-bearing Postgres/asyncpg behaviour.

---

## §1 — JSON Schema validator library

**Decision**: `jsonschema >= 4.23, < 5` (the canonical pure-Python validator).

**Rationale**:
- The validator runs **at most twice** in a hot path: once on backend startup to validate `configs/feature-flags.yaml`, and once per pre-commit / CI run. Raw throughput is irrelevant; what matters is **error-message quality** (a developer must understand exactly which YAML line broke the schema).
- `jsonschema` has the best error story in the ecosystem: per-instance `ValidationError` with `json_path`, `absolute_path`, `schema_path`, `validator`, and a human-readable `message`. The hook script can surface "configs/feature-flags.yaml: $.flags[2].state must be one of [active, sunset]" verbatim.
- Pure Python, no native compile, no extra wheel — adds the package itself plus `attrs` and `jsonschema-specifications` to the lock; total install size < 2 MB.
- Draft 2020-12 supported (we need conditional `if/then/else` for the sunset-required-fields rule — research §9).

**Alternatives considered**:
- `fastjsonschema` — compiles the schema to a Python function; ~10× faster. Rejected: speed is irrelevant here, and its `JsonSchemaException` reports a single point of failure with a less precise location, hurting the "actionable error" requirement (FR-010 hook UX).
- `jschon` — modern, draft 2020-12 native, clean API. Rejected for smaller community and fewer Stack-Overflow-grade examples, which matters when a new contributor debugs a schema violation on a Friday afternoon.

---

## §2 — LISTEN/NOTIFY payload shape

**Decision**: Trigger emits `pg_notify('feature_flag_changed', COALESCE(NEW.name, OLD.name))`. Payload is the **single flag name**.

**Rationale**:
- Per-flag invalidation is strictly better than cache-wide flush: a hot flag flipping should not evict 50 unrelated entries.
- `COALESCE(NEW.name, OLD.name)` covers all three trigger ops uniformly — `INSERT` (NEW.name set), `UPDATE` (both set; NEW.name is the post-update name), `DELETE` (only OLD.name set).
- Postgres NOTIFY payload is limited to 8000 bytes; a flag name fits with vast headroom. No need for a JSON envelope.
- The listener side becomes trivial: `cache.pop(payload, None)`.

**Alternatives considered**:
- *Empty payload + full registry reload on any change* — simpler trigger, but evicts the entire cache on any flip and forces a full re-read from DB on next access. Rejected on UX grounds (a typo flip would re-warm every cache entry).
- *Row-JSON payload (`row_to_json(NEW)`)* — carries the new state directly, so the listener could update the cache without a DB re-read. Rejected: couples the listener tightly to the row shape; any future column change requires a coordinated update; the cache miss after invalidation reads only one row, which is < 10 ms.

---

## §3 — asyncpg LISTEN lifecycle

**Decision**: One **dedicated long-lived `asyncpg.Connection`** outside the engine pool. Owned by the `FeatureFlagService`. Created in the FastAPI `startup` hook; cancelled in `shutdown`. On listener loss, reconnect with exponential backoff (1s → 2s → 4s → 8s → 30s cap), logging each attempt at INFO. While disconnected, the cache silently degrades to the 60-second TTL (correctness preserved, freshness reduced — edge case noted in the spec).

**Rationale**:
- asyncpg's `connection.add_listener(channel, callback)` requires a connection dedicated to that role: the connection cannot be checked back into a pool while listening (any pool eviction or re-issuance breaks the subscription).
- Owning the connection in the service (not the engine) keeps the lifecycle explicit; the FastAPI lifespan hook makes startup/shutdown observable. Tests inject a service constructed against the test engine.
- Reconnect-with-backoff avoids a tight loop hammering the DB during an outage; the cap of 30 s bounds the worst-case freshness gap (when listener is dead the TTL is the SLO).
- On shutdown the listener task is cancelled cleanly so tmpfs-based tests don't leak sockets between runs.

**Alternatives considered**:
- *Use a connection from the engine pool with `acquire()` for the listener's lifetime* — rejected: it removes one slot from the pool indefinitely; equivalent to "dedicated connection" with extra coupling.
- *Polling the DB on a fixed interval instead of LISTEN* — rejected: defeats SC-003 (1-second invalidation) and increases DB load proportional to flag count.

---

## §4 — Cache shape

**Decision**: `dict[str, tuple[bool, float]]` keyed by flag name, value `(enabled, expires_at_epoch)`. Per-flag TTL (60 s on each entry). Reads are **lock-free** (Python's GIL makes a `dict.get` atomic). Writes are serialised under a single `asyncio.Lock` to avoid thundering-herd DB hits on simultaneous cache misses for the same flag.

**Rationale**:
- The cache is read-mostly; lock-free reads are a 1-microsecond fast path (FR-003 / SC-003 leaves us no budget for lock contention in the common case).
- A single `asyncio.Lock` is enough because writes are rare (NOTIFY-driven, or 60-s TTL expiry). Per-flag locks would be overkill.
- TTL stored as absolute monotonic-like epoch (`time.time()`) so expiry checks are subtraction, no datetime arithmetic.
- No LRU: flag count is bounded (single-digit to low-tens) and entries don't grow.

**Alternatives considered**:
- *`functools.lru_cache`* — synchronous; doesn't compose with `async def`; no TTL. Rejected.
- *Async LRU library (`aiocache`)* — adds a dependency for a dict + lock + clock. Rejected as needlessly heavy.
- *Per-flag locks* — adds bookkeeping for no real contention reduction at this scale. Rejected as YAGNI.

---

## §5 — GHA workflow ↔ Cloud SQL via WIF

**Decision**: The workflow uses `google-github-actions/auth@v2` with `workload_identity_provider:` + `service_account:` (the WIF binding from T01a is assumed present). It then runs `gcloud sql connect` or uses the Cloud SQL Auth Proxy sidecar pattern to open a short-lived authenticated socket. **T05a ships the workflow file with documented placeholders** (`<TODO-T06: project>`, `<TODO-T06: region>`, `<TODO-T06: instance>`, `<TODO-T06: service-account>`) — T06 fills them when it provisions the Cloud SQL instance. The workflow's structure is complete; only the WIF/instance binding parameters are pending.

**Rationale**:
- Constitution §6 forbids JSON service-account keys; WIF is the project's chosen alternative (ADR-013). T01a established the OIDC trust binding between this repo and the GCP project.
- Calling out the T06 boundary in the workflow file (via the `<TODO-T06: …>` placeholders) prevents the workflow from accidentally running against a not-yet-provisioned DB and producing a confusing 404; CI marks it pending until T06 fills the placeholders. The workflow itself remains green in T05a's PR because the only path that exercises the live binding is the post-merge run, which is skipped by `if:` guards on missing inputs.
- The Cloud SQL Auth Proxy pattern is the canonical Google recipe and what T06 will document; T05a does not pre-decide between sidecar and direct-IAM-DB-auth (T06 owns that).

**Alternatives considered**:
- *Ship a JSON SA key for now and rotate later* — rejected outright (constitution §5/§6).
- *Defer the entire workflow file to T06* — rejected: the YAML, the schema validator wiring, and the upsert script are all T05a's responsibility per FR-007; the workflow file is the contract T06 binds to credentials. Splitting it means T06 has to author the workflow logic too.

---

## §6 — Hook script location & invocation

**Decision**: `scripts/check-feature-flag-registration.py` (Python, executable). Wired in two places:

1. **`.pre-commit-config.yaml`** — a new local hook (`id: feature-flag-registered`, `language: system`, `entry: python scripts/check-feature-flag-registration.py`, `files:` matching `app/backend/.*\.py$`, `configs/feature-flags\.yaml$`, `docs/engineering/feature-flags\.md$`, `docs/contracts/feature-flag\.schema\.json$`). Triggered by changes to any of the four files. Mirrors T04's `no-provider-sdk-imports` hook pattern.
2. **CI / test image** — the script is already in the image because T05 added `COPY scripts ./scripts` to the Dockerfile. The hook tests (`test_feature_flag_registration.py`) invoke the script as a subprocess against fixture trees, which is the de-facto in-container CI check until T10 ships.

**Rationale**:
- Python (not bash + grep) because the hook must parse YAML, walk Python source (regex is fine for `is_enabled\(["']([^"']+)["']\)` literals at MVP scale), and produce structured error messages — these are easier in Python.
- `language: system` keeps pre-commit fast (no isolated venv); the script imports only `jsonschema`, `pyyaml`, and stdlib, all available in the dev image.

**Alternatives considered**:
- *Bash + ripgrep + yq* — rejected: error formatting is poor, and the conditional sunset logic is fiddly in shell.
- *Bandit AST walk* — rejected as overkill; regex on `is_enabled("…")` literals catches every realistic call shape and is a fraction of the complexity.

---

## §7 — Sub-second invalidation testing without flakiness

**Decision**: The service test uses `asyncio.wait_for(loop_until_match(target_value), timeout=1.0)` with a 10-ms poll interval. The 1-second SLO has ~100× headroom over typical NOTIFY round-trip (< 10 ms locally), so the test is reliable across machines without being a tight bench.

**Rationale**:
- A flat sleep + single assert is flaky (NOTIFY may arrive in 1 ms or 50 ms depending on scheduler).
- Polling until the value matches (or the timeout fires) gives a sharp signal: either the value propagated in time (test passes promptly), or it didn't (test fails with the actual elapsed time, useful for diagnosing flakiness).
- The 10-ms poll interval is tight enough to make the test responsive but loose enough not to peg a CPU.

**Alternatives considered**:
- *Mock the listener entirely and only test the cache logic* — rejected: hides the integration we most want to verify.
- *A separate `pytest.mark.slow` test with a longer budget* — overkill; the existing budget is fine on every laptop and CI runner.

---

## §8 — Sunset detection algorithm

**Decision**: The hook works on the **post-state of the tree** (no git-diff awareness). Algorithm:

```text
yaml_entries = parse configs/feature-flags.yaml
call_sites   = regex-scan app/backend/**/*.py for is_enabled("…")
docs_entries = parse docs/engineering/feature-flags.md (Active + Sunset tables)

for entry in yaml_entries:
  if entry.state == "active":
    assert entry.name in call_sites          # FR-010b — orphan declaration
    assert entry.name in docs_entries.active  # FR-012 — index entry exists
  elif entry.state == "sunset":
    assert entry.sunset_pr and entry.sunset_date     # FR-011 — sunset metadata
    assert entry.name in docs_entries.sunset         # FR-011 — docs row exists

for call_name in call_sites:
  assert any(e.name == call_name and e.state == "active" for e in yaml_entries)  # FR-010a — typo

for docs_name in docs_entries.sunset:
  assert any(e.name == docs_name and e.state == "sunset" for e in yaml_entries)  # FR-011 — docs without YAML
```

**Rationale**:
- Post-state checking is **simpler and equally strict** than git-diff: the invariant we care about is "the tree is consistent right now", not "this PR introduced the inconsistency". Pre-commit runs on the staged tree, CI runs on the merged tree; either way, the post-state is the source of truth.
- A "removed last call" violation is naturally caught: after the PR is applied, an `state: active` YAML entry without a call site fails. The hook doesn't need to know what was removed — only that the result is inconsistent.
- Avoiding `git diff` parsing makes the hook reproducible (same exit code on the same tree, regardless of commit history) and easier to test.

**Alternatives considered**:
- *Git-diff aware* — would let the hook explain "you removed `is_enabled('legacy')` in this commit". Rejected for complexity; the post-state error message is "configs/feature-flags.yaml: 'legacy' is state=active but no call site in app/backend/ — flip to state=sunset or restore a call site", which is just as actionable.

---

## §9 — YAML entry schema

**Decision**: JSON Schema (draft 2020-12, conditional `if/then/else`):

```text
required:           [name, owner, default, description, state]
optional:           [default_value]
conditional:        if state == "sunset" → required: [sunset_pr, sunset_date]
name:               TEXT (matches ^[a-z][a-z0-9_]{2,63}$ — snake_case, 3-64 chars)
owner:              TEXT (≥ 1 char, free-form; recommended @-prefixed GH handle)
default:            BOOLEAN (the seed for `enabled` when the row is first created)
default_value:      JSON (mirrors the JSONB column; unused at MVP; reserved for future non-boolean flags)
description:        TEXT (one short paragraph)
state:              ENUM ["active", "sunset"]
sunset_pr:          TEXT (matches ^#\d+$ — GH PR back-reference)
sunset_date:        DATE (YYYY-MM-DD)
```

**Rationale**:
- The five required fields cover the spec's "every declared flag MUST have name/owner/default/description/state" (FR-001 + FR-011). `default_value` is reserved for the future non-boolean-payload case; today the column exists (`JSONB`) but is unused at MVP.
- The conditional `if/then/else` is the cleanest way to express "sunset requires the metadata" without splitting the schema into two `oneOf` branches; jsonschema 4.x supports it natively (draft 2020-12).
- `^[a-z][a-z0-9_]{2,63}$` for `name` forbids quirky characters that would break regex-scan or SQL identifiers; matches Python identifier conventions; max 64 chars matches Postgres NAMEDATALEN minus headroom.

**Alternatives considered**:
- *Make `default_value` required* — rejected: the column already has a default null; forcing it now adds noise to every entry.
- *Use a `oneOf` split (active vs sunset variants)* — rejected: `oneOf` produces less readable errors than `if/then/else`.

---

## §10 — Workflow target environments

**Decision**: The sync workflow runs **against production only** (constitution §8 — production is the only long-lived environment). Trigger conditions: `push` to `main` with a change to `configs/feature-flags.yaml`, **and** `workflow_dispatch` for manual reconciliation (operator can rerun without a YAML change to recover from a partial run).

**Rationale**:
- §8 is explicit: there is no staging or QA environment. Running the workflow against a non-existent dev DB would be a runtime error every time, which is noise.
- Local developers exercise the upsert logic by running the script directly against their local Postgres (the script accepts a `DATABASE_URL` env var), not by triggering the workflow.
- `workflow_dispatch` covers the recovery case where a workflow run was interrupted (e.g., transient DB outage) and an operator needs to retry without making another YAML change.

**Alternatives considered**:
- *Run against a dev DB on every PR* — rejected: no dev DB exists by §8; adding one for this case alone is scope creep.
- *Cron-driven reconciliation every hour* — rejected as YAGNI; the PR-driven path covers ~99% of flips, and `workflow_dispatch` handles the rest.

---

## Summary of resolved decisions

| # | Decision |
| - | -------- |
| 1 | `jsonschema >= 4.23` (error-message quality > speed). |
| 2 | NOTIFY payload = `COALESCE(NEW.name, OLD.name)` — per-flag invalidation. |
| 3 | Dedicated asyncpg `Connection` outside the pool; FastAPI startup/shutdown lifecycle; reconnect with exponential backoff to 30 s cap. |
| 4 | `dict[str, (value, expires_at)]` cache; lock-free reads; single `asyncio.Lock` around writes; per-flag 60-s TTL backstop. |
| 5 | WIF via `google-github-actions/auth@v2` + Cloud SQL Auth Proxy; live binding params are `<TODO-T06>` placeholders. |
| 6 | `scripts/check-feature-flag-registration.py` Python script; `language: system` pre-commit hook; in-CI via the test image (script already copied). |
| 7 | `asyncio.wait_for(loop_until_match, timeout=1.0)` with 10-ms poll for the invalidation test. |
| 8 | Post-state hook algorithm (no git-diff awareness); enforces all four FR-010/FR-011 invariants. |
| 9 | JSON Schema draft 2020-12 with `if/then/else` for the conditional sunset metadata; strict `name` regex. |
| 10 | Workflow runs prod-only (§8); `workflow_dispatch` for manual reconciliation; local devs invoke the upsert script directly. |
