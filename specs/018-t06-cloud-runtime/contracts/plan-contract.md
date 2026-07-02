# Contract pointer — T06

Per the implementation plan, T06's `contract:` is the **`infra/terraform/` module layout** itself. The committed artefacts that downstream tasks bind to:

1. **`infra/terraform/modules/environment/`** — the per-environment interface (inputs/outputs table in [data-model.md](../data-model.md)). Consumers: T06a (`/deploy` targets the service names + Artifact Registry repo), T07 (adds Identity Platform against the same envs), T38 (monitoring over both envs).
2. **`.github/workflows/sync-feature-flags.yml` env block** — the WIF/Cloud-SQL binding values (table in data-model.md). Consumer: T16 adds the `sync-rubric` job to this same workflow reusing the same identity/proxy pattern.
3. **`scripts/cloud-db-grants.sql`** — the DB-privilege contract for CI identities. Consumer: T16 extends grants if the rubric sync needs more tables.
4. **`adr/023-dev-prod-environments.md` + constitution §8 (v1.1)** — the governance contract every later environment-touching task cites instead of ADR-009.

No OpenAPI/JSON-schema surface changes in T06 (`openapi.yaml` untouched; regen-diff stays zero).
