# Contract pointer — T06a

Per the implementation plan, T06a's `contract:` is **`.github/workflows/deploy.yml` + `.github/workflows/rollback.yml` + `docs/engineering/deploy-playbook.md`** (promote.yml joins as the third verb). The committed artefacts downstream tasks bind to:

1. **Workflow input contracts** (tables in [data-model.md](../data-model.md)) — `deploy(env, service, git_ref)`, `promote(env, service, percent)`, `rollback(env, service, revision?)`. Consumers: T11 (Tier-1 smoke deploys to `dev` via `/deploy` and pings from the deployed backend), every application task thereafter, and the playbook's operator instructions.
2. **Image tag scheme** — `<registry>/techscreen/{backend,frontend}:<full-sha>-<env>`. Consumers: the migration gate itself (parses the deployed baseline), T38 (dashboards keyed by revision/image), any future cleanup job.
3. **`techscreen-deployer@` role set** (matrix in data-model.md) — the IAM contract for CI-driven releases. Consumers: T07+ tasks that extend deploy-time behaviour must extend this SA (never the terraform SA) and justify each new role.
4. **`candidate` revision tag** — "the revision smoke ran against"; T11 and the playbook reference its URL shape.
5. **`scripts/cloud-sql-power.sh`** — the operator lever the deploy guard's error message names; the playbook's cost-idle section is its documentation.

No OpenAPI/JSON-schema surface changes in T06a (`openapi.yaml` untouched).
