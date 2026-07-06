# Contract pointer — T16

Per the implementation plan, T16's `contract:` field is **"none (internal job)"** — no OpenAPI/JSON-schema surface changes (`openapi.yaml` untouched; `docs/contracts/rubric.schema.json` is consumed, not modified). The committed artefacts downstream work binds to:

1. **`.github/workflows/sync-configs.yml`** — the single §16 workflow. Job ids `sync-feature-flags` and `sync-rubric` (independent; matrix dev+prod). Consumer: any Phase 2 configs-as-code surface adds a *third job here*, reusing the same WIF identity, pinned-proxy step, and gate-before-cloud ordering.
2. **`scripts/sync_rubric_to_db.py` CLI** — `check`/`sync` subcommands with the exit-code table in [data-model.md](../data-model.md). Consumers: the workflow, the operator quickstart, and `app/backend/tests/contracts/test_rubric_sync_check.py` (which pins the taxonomy behaviourally).
3. **`scripts/cloud-db-grants.sql`** — the DB-privilege contract for the CI identity, now covering both surfaces. Consumer: the operator (re-runnable per instance); any future surface extends this file with its own justified block.
4. **Destructive-change taxonomy** (data-model.md table) — the policy vocabulary (`NODE_REMOVED` forbidden; `NODE_RETIRED`/`NODE_UNRETIRED`/`LEVEL_REMOVED`/`LEVEL_RETYPED` ADR-gated) that rubric maintainers and reviewers cite in PRs.

Upstream contracts consumed unchanged: `docs/contracts/rubric.schema.json` (T08), `RubricImporter.seed` semantics (specs/010 FR-006..FR-010), the T06 workflow env contract (`specs/018-t06-cloud-runtime/data-model.md`).
